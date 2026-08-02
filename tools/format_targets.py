"""Format only source files owned by selected Bazel targets."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from typing import TYPE_CHECKING, cast

from tools.bazel_support import bazel_command, bazel_workspace, main_repo_source_path, run_bazel

if TYPE_CHECKING:
    from pathlib import Path

SUPPORTED_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".cxx",
    ".h",
    ".hh",
    ".hpp",
    ".hxx",
    ".inc",
    ".py",
    ".pyi",
    ".rs",
}
TARGET_PATTERN = re.compile(r"^(?:@[^/]+)?//[A-Za-z0-9_./+*-]*(?::[A-Za-z0-9_./+*-]+)?$")


def _target_expression(patterns: list[str]) -> str:
    for pattern in patterns:
        if not TARGET_PATTERN.fullmatch(pattern):
            msg = f"unsupported Bazel target pattern: {pattern!r}"
            raise ValueError(msg)
    return " union ".join(f"({pattern})" for pattern in patterns)


def _owned_sources(workspace: Path, patterns: list[str]) -> list[Path]:
    targets = _target_expression(patterns)
    eligible = f'({targets}) except attr("tags", "no-format", ({targets}))'
    languages = (
        ("py_(library|binary|test) rule", "no-ruff-format", ("srcs",)),
        (
            "cc_(library|binary|test) rule",
            "no-clang-format",
            ("srcs", "hdrs", "textual_hdrs"),
        ),
        (
            "rust_(library|binary|test) rule",
            "(no-rustfmt|norustfmt)",
            ("srcs",),
        ),
    )
    owned: list[str] = []
    for rule_kinds, language_opt_out, attributes in languages:
        language_targets = f'kind("{rule_kinds}", ({eligible}))'
        language_targets += f' except attr("tags", "{language_opt_out}", ({language_targets}))'
        owned.extend(f"labels({attribute}, ({language_targets}))" for attribute in attributes)
    owned_files = " union ".join(owned)
    expression = f'kind("source file", {owned_files})'
    output = run_bazel(
        workspace,
        "query",
        "--noshow_progress",
        "--output=label",
        expression,
    )

    sources: set[Path] = set()
    for label in output.splitlines():
        relative = main_repo_source_path(label.strip())
        if relative is None or relative.suffix not in SUPPORTED_SUFFIXES:
            continue
        absolute = (workspace / relative).resolve()
        try:
            absolute.relative_to(workspace)
        except ValueError as error:
            msg = f"source escaped the workspace: {relative}"
            raise RuntimeError(msg) from error
        if absolute.is_file():
            sources.add(relative)
    return sorted(sources)


def main() -> int:
    """Format Bazel-owned sources selected by target patterns."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "targets",
        nargs="*",
        default=["//..."],
        help="Bazel target patterns whose owned sources should be formatted",
    )
    args = parser.parse_args()
    targets = cast("list[str]", args.targets)
    workspace = bazel_workspace()
    try:
        sources = _owned_sources(workspace, targets or ["//..."])
    except (RuntimeError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    if not sources:
        print("No supported source files are owned by the selected targets.")
        return 0

    print(f"Formatting {len(sources)} Bazel-owned source file(s).", flush=True)
    result = subprocess.run(
        bazel_command(
            [
                "run",
                "//tools/bazel_devtools:formatters",
                "--",
                *[str(path) for path in sources],
            ]
        ),
        cwd=workspace,
        check=False,
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
