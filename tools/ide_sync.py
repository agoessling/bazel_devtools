"""Synchronize editor project models from a Bazel target graph."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import cast

from tools.bazel_support import (
    bazel_options,
    bazel_workspace,
    main_repo_source_path,
    run_bazel,
)
from tools.bazel_wrapper import write_bazel_wrapper

PY_TARGETS = 'kind("py_(library|binary|test) rule", //...) except attr("tags", "no-ide", //...)'
PY_MATERIALIZATION_TARGETS = (
    'kind("py_(binary|test) rule", //...) except attr("tags", "no-ide", //...)'
)
PYTHON_EXTENSIONS = {".py", ".pyi"}


def _run_recursive_bazel_tool(workspace: Path, *arguments: str) -> str:
    """Run a Bazel tool whose executable may itself invoke `bazel`."""
    bazel = shutil.which("bazel")
    if bazel is None:
        msg = "bazel was not found on PATH"
        raise RuntimeError(msg)
    startup, command = bazel_options()
    with tempfile.TemporaryDirectory(prefix="bazel-devtools-") as temporary:
        wrapper = Path(temporary) / "bazel"
        write_bazel_wrapper(wrapper, bazel, startup, command)
        path = temporary + os.pathsep + os.environ.get("PATH", "")
        return run_bazel(workspace, "run", "--run_env=PATH=" + path, *arguments)


def _has_targets(workspace: Path, kind_pattern: str) -> bool:
    output = run_bazel(
        workspace,
        "query",
        "--noshow_progress",
        f'kind("{kind_pattern}", //...)',
    )
    return bool(output.strip())


def _label_package(label: str) -> Path:
    match = re.match(r"^//([^:]*):", label)
    return Path(match.group(1)) if match and match.group(1) else Path()


def _python_owned_sources(workspace: Path) -> list[Path]:
    output = run_bazel(
        workspace,
        "query",
        "--noshow_progress",
        "--output=label",
        f'kind("source file", labels(srcs, ({PY_TARGETS})))',
    )
    sources: set[Path] = set()
    for label in output.splitlines():
        relative = main_repo_source_path(label.strip())
        if relative is None or relative.suffix not in PYTHON_EXTENSIONS:
            continue
        absolute = (workspace / relative).resolve()
        try:
            absolute.relative_to(workspace)
        except ValueError as error:
            msg = f"Python source escaped the workspace: {relative}"
            raise RuntimeError(msg) from error
        if absolute.is_file():
            sources.add(relative)
    return sorted(sources)


def _python_import_paths(workspace: Path) -> list[Path]:
    xml = run_bazel(workspace, "query", "--output=xml", PY_TARGETS)
    root = ET.fromstring(xml)
    paths: set[Path] = {workspace}
    for rule in root.findall("rule"):
        package = _label_package(rule.attrib["name"])
        for value in rule.findall("list[@name='imports']/string"):
            path = (workspace / package / value.attrib["value"]).resolve()
            if path.exists():
                paths.add(path)
    return sorted(paths)


def _python_dependency_names(workspace: Path) -> list[str]:
    output = run_bazel(workspace, "query", f"deps({PY_TARGETS})")
    names: set[str] = set()
    for label in output.splitlines():
        match = re.match(r"^@pypi//([^:]+):", label)
        if match and not match.group(1).startswith("_") and match.group(1) != "venv":
            names.add(match.group(1))
    return sorted(names)


def _materialize_python(workspace: Path) -> None:
    output = run_bazel(workspace, "query", PY_MATERIALIZATION_TARGETS)
    targets = [line for line in output.splitlines() if line.startswith("//")]
    if targets:
        run_bazel(workspace, "build", *targets)


def _python_site_packages(workspace: Path) -> list[Path]:
    names = _python_dependency_names(workspace)
    if not names:
        return []
    _materialize_python(workspace)
    roots: set[Path] = set()
    missing: list[str] = []
    external = workspace / "bazel-bin" / "external"
    for name in names:
        matches = list(
            external.glob(
                f"aspect_rules_py++uv+whl_install__*__{name}__*/install/lib/python*/site-packages"
            )
        )
        if matches:
            roots.update(path.resolve() for path in matches if path.exists())
        else:
            missing.append(name)
    if missing:
        print(
            "warning: no Aspect uv site-packages root found for " + ", ".join(missing),
            file=sys.stderr,
        )
    return sorted(roots)


def _sync_python(workspace: Path) -> None:
    paths = _python_import_paths(workspace) + _python_site_packages(workspace)
    sources = _python_owned_sources(workspace)
    config = {
        "extends": "basedpyright.json",
        "extraPaths": [str(path) for path in paths],
        "include": [path.as_posix() for path in sources],
    }
    output = workspace / "pyrightconfig.json"
    output.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {output} ({len(sources)} Bazel-owned sources, {len(paths)} Python search paths)")


def _sync_cpp(workspace: Path) -> None:
    # Hedron still spells its generated Python/C++ executables as native rules.
    # Bazel 9 can supply their Starlark replacements without changing the
    # consuming repository's normal build semantics.
    _run_recursive_bazel_tool(
        workspace,
        "--incompatible_autoload_externally=+@rules_python,+@rules_cc",
        "@hedron_compile_commands//:refresh_all",
    )
    print(f"wrote {workspace / 'compile_commands.json'}")


def _sync_rust(workspace: Path) -> None:
    _run_recursive_bazel_tool(
        workspace,
        "@@rules_rust+//tools/rust_analyzer:gen_rust_project",
    )
    print(f"wrote {workspace / 'rust-project.json'}")


def main() -> int:
    """Generate project metadata for the languages present in the workspace."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--language",
        choices=("python", "cpp", "rust"),
        action="append",
        help="sync only selected languages (repeatable)",
    )
    args = parser.parse_args()
    languages = cast("list[str] | None", args.language)
    selected = set(languages or ())
    workspace = bazel_workspace()
    operations = (
        ("python", "py_(library|binary|test) rule", _sync_python),
        ("cpp", "cc_(library|binary|test) rule", _sync_cpp),
        ("rust", "rust_(library|binary|test) rule", _sync_rust),
    )
    try:
        for language, kinds, operation in operations:
            if selected and language not in selected:
                continue
            if _has_targets(workspace, kinds):
                operation(workspace)
            else:
                print(f"skipped {language}: no matching Bazel targets")
    except RuntimeError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
