"""Safe installation and upgrades for consuming bazel_devtools repositories."""

from __future__ import annotations

import difflib
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict, cast

from tools.languages import SUPPORTED_LANGUAGES, normalize_languages
from tools.templates import (
    BAZEL_DEVTOOLS_VERSION,
    TEMPLATES,
    Ownership,
    Template,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

STATE_PATH = Path(".bazel_devtools/state.json")
UPDATES_PATH = Path(".bazel_devtools/updates")
BEGIN_PATTERN = re.compile(r"^# ##BAZEL_DEVTOOLS_MANAGED_BEGIN:(?P<id>[a-z0-9][a-z0-9-]*)##$")
END_PATTERN = re.compile(r"^# ##BAZEL_DEVTOOLS_MANAGED_END:(?P<id>[a-z0-9][a-z0-9-]*)##$")
RUFF_EXTEND_PATTERN = re.compile(
    r"(?m)^\s*extend\s*=\s*['\"]\.bazel_devtools/ruff\.toml['\"]\s*(?:#.*)?$"
)
PYPROJECT_RUFF_PATTERN = re.compile(r"(?m)^\s*\[tool\.ruff(?:\.|\])")
PYPROJECT_PYRIGHT_PATTERN = re.compile(r"(?m)^\s*\[tool\.(?:basedpyright|pyright)(?:\.|\])")
POLICY_BLOCK_PATHS = (".clang-format", ".clang-tidy", "rustfmt.toml")
DEDICATED_BLOCK_PATHS = {
    ".bazelrc.bazel_devtools": "checks",
    "tools/bazel_devtools/BUILD.bazel": "tools",
    "tools/bazel_devtools/aspects.bzl": "aspects",
}
MODULE_DEPENDENCY_PATTERN = re.compile(
    r"""(?sx)
    \bbazel_dep\s*\([^)]*\bname\s*=\s*['\"]
    (?P<name>toolchains_llvm|hedron_compile_commands)['\"]
    """
)
MODULE_SYMBOL_PATTERN = re.compile(r"(?m)^\s*bazel_devtools_llvm\s*=")
ROOT_TARGET_PATTERN = re.compile(
    r"""(?sx)
    \b[a-zA-Z_][a-zA-Z0-9_]*\s*\([^)]*\bname\s*=\s*['\"]
    (?P<name>format|ide-sync|install-hooks|pre-commit)['\"]
    """
)
PRE_COMMIT_HOOK_PATTERN = re.compile(r"(?m)^\s*-\s+id:\s*bazel-devtools-check\s*$")


class SetupError(RuntimeError):
    """Raised when setup cannot safely make progress."""


@dataclass(frozen=True)
class Block:
    """Location and contents of a managed block in a text file."""

    block_id: str
    begin: int
    body_begin: int
    body_end: int
    end: int
    body: str


@dataclass
class Result:
    """Files and messages produced by a setup operation."""

    changed: list[str]
    created: list[str]
    conflicts: list[str]
    messages: list[str]

    @classmethod
    def empty(cls) -> Result:
        """Create a result with no recorded effects."""
        return cls(changed=[], created=[], conflicts=[], messages=[])


class _StateEntry(TypedDict):
    ownership: str
    block_id: str | None
    base: str
    digest: str
    template_version: str


class _State(TypedDict):
    schema_version: int
    installed_version: str | None
    languages: list[str]
    entries: dict[str, _StateEntry]


def _digest(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _markers(block_id: str) -> tuple[str, str]:
    return (
        f"# ##BAZEL_DEVTOOLS_MANAGED_BEGIN:{block_id}##",
        f"# ##BAZEL_DEVTOOLS_MANAGED_END:{block_id}##",
    )


def render_block(block_id: str, body: str) -> str:
    """Wrap a template body in stable managed-block markers."""
    begin, end = _markers(block_id)
    normalized = body.rstrip("\n")
    return f"{begin}\n{normalized}\n{end}\n"


def parse_blocks(content: str) -> dict[str, Block]:
    """Parse and validate every managed block in a text file."""
    lines = content.splitlines(keepends=True)
    blocks: dict[str, Block] = {}
    open_id: str | None = None
    open_begin = 0
    body_begin = 0
    offset = 0

    for line in lines:
        stripped = line.rstrip("\r\n")
        begin_match = BEGIN_PATTERN.fullmatch(stripped)
        end_match = END_PATTERN.fullmatch(stripped)

        if begin_match:
            block_id = begin_match.group("id")
            if open_id is not None:
                msg = f"nested managed block {block_id!r} inside {open_id!r}"
                raise SetupError(msg)
            if block_id in blocks:
                msg = f"duplicate managed block {block_id!r}"
                raise SetupError(msg)
            open_id = block_id
            open_begin = offset
            body_begin = offset + len(line)
        elif end_match:
            block_id = end_match.group("id")
            if open_id is None:
                msg = f"managed block {block_id!r} ends without beginning"
                raise SetupError(msg)
            if block_id != open_id:
                msg = f"managed block {open_id!r} ended by marker for {block_id!r}"
                raise SetupError(msg)
            blocks[block_id] = Block(
                block_id=block_id,
                begin=open_begin,
                body_begin=body_begin,
                body_end=offset,
                end=offset + len(line),
                body=content[body_begin:offset],
            )
            open_id = None
        offset += len(line)

    if open_id is not None:
        msg = f"managed block {open_id!r} has no end marker"
        raise SetupError(msg)
    return blocks


def replace_block(content: str, block: Block, body: str) -> str:
    """Replace one parsed block without modifying surrounding content."""
    rendered = render_block(block.block_id, body)
    return content[: block.begin] + rendered + content[block.end :]


def append_block(content: str, block_id: str, body: str) -> str:
    """Append a managed block with normalized blank-line separation."""
    prefix = content
    if prefix and not prefix.endswith("\n"):
        prefix += "\n"
    if prefix and not prefix.endswith("\n\n"):
        prefix += "\n"
    return prefix + render_block(block_id, body)


def _object_dict(value: object, description: str) -> dict[str, object]:
    if not isinstance(value, dict):
        msg = f"{description} must be a JSON object"
        raise SetupError(msg)
    raw = cast("dict[object, object]", value)
    result: dict[str, object] = {}
    for key, item in raw.items():
        if not isinstance(key, str):
            msg = f"{description} contains a non-string key"
            raise SetupError(msg)
        result[key] = item
    return result


def _state_entry(value: object, description: str) -> _StateEntry:
    raw = _object_dict(value, description)
    ownership = raw.get("ownership")
    block_id = raw.get("block_id")
    base = raw.get("base")
    digest = raw.get("digest")
    template_version = raw.get("template_version")
    if (
        not isinstance(ownership, str)
        or (block_id is not None and not isinstance(block_id, str))
        or not isinstance(base, str)
        or not isinstance(digest, str)
        or not isinstance(template_version, str)
    ):
        msg = f"{description} has invalid fields"
        raise SetupError(msg)
    return {
        "ownership": ownership,
        "block_id": block_id,
        "base": base,
        "digest": digest,
        "template_version": template_version,
    }


def _read_state(workspace: Path) -> _State:
    path = workspace / STATE_PATH
    if not path.exists():
        return {
            "schema_version": 2,
            "installed_version": None,
            "languages": list(SUPPORTED_LANGUAGES),
            "entries": {},
        }
    try:
        decoded: object = json.loads(  # pyright: ignore[reportAny]
            path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as error:
        msg = f"cannot read {path}: {error}"
        raise SetupError(msg) from error
    raw = _object_dict(decoded, f"state in {path}")
    schema_version = raw.get("schema_version")
    installed_version = raw.get("installed_version")
    if schema_version not in (1, 2) or (
        installed_version is not None and not isinstance(installed_version, str)
    ):
        msg = f"unsupported state schema in {path}"
        raise SetupError(msg)
    raw_languages = raw.get("languages", list(SUPPORTED_LANGUAGES))
    if not isinstance(raw_languages, list):
        msg = f"invalid language selection in {path}"
        raise SetupError(msg)
    language_values = cast("list[object]", raw_languages)
    if not all(isinstance(language, str) for language in language_values):
        msg = f"invalid language selection in {path}"
        raise SetupError(msg)
    try:
        languages = normalize_languages(cast("list[str]", language_values))
    except ValueError as error:
        msg = f"invalid language selection in {path}: {error}"
        raise SetupError(msg) from error
    raw_entries = _object_dict(raw.get("entries"), f"state entries in {path}")
    entries = {
        entry_path: _state_entry(value, f"state entry {entry_path!r} in {path}")
        for entry_path, value in raw_entries.items()
    }
    return {
        "schema_version": 2,
        "installed_version": installed_version,
        "languages": list(languages),
        "entries": entries,
    }


def _write_state(workspace: Path, state: _State) -> None:
    path = workspace / STATE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def installed_languages(workspace: Path) -> tuple[str, ...] | None:
    """Return the installed language selection, or None before initialization."""
    state = _read_state(_validate_workspace(workspace))
    if not state["entries"]:
        return None
    return tuple(state["languages"])


def _entry(template: Template) -> _StateEntry:
    return {
        "ownership": template.ownership.value,
        "block_id": template.block_id,
        "base": template.content,
        "digest": _digest(template.content),
        "template_version": BAZEL_DEVTOOLS_VERSION,
    }


def _validate_templates(templates: tuple[Template, ...]) -> None:
    paths: set[str] = set()
    for template in templates:
        path = Path(template.path)
        if not template.path or path.is_absolute() or path == Path() or ".." in path.parts:
            msg = f"unsafe template path {template.path!r}"
            raise SetupError(msg)
        if template.path in paths:
            msg = f"duplicate template path {template.path!r}"
            raise SetupError(msg)
        paths.add(template.path)
        if template.ownership is Ownership.MANAGED_BLOCK:
            if template.block_id is None or not re.fullmatch(
                r"[a-z0-9][a-z0-9-]*", template.block_id
            ):
                msg = f"managed block template {template.path} has an invalid block id"
                raise SetupError(msg)
        elif template.block_id is not None:
            msg = f"non-block template {template.path} unexpectedly has a block id"
            raise SetupError(msg)


def _validate_entry(template: Template, previous: _StateEntry | None) -> _StateEntry:
    if previous is None:
        msg = f"missing state for managed path {template.path}"
        raise SetupError(msg)
    old_base = previous["base"]
    if previous["digest"] != _digest(old_base):
        msg = f"corrupt baseline digest for managed path {template.path}"
        raise SetupError(msg)
    if previous["ownership"] != template.ownership.value:
        msg = f"ownership changed for managed path {template.path}"
        raise SetupError(msg)
    if previous["block_id"] != template.block_id:
        msg = f"block identity changed for managed path {template.path}"
        raise SetupError(msg)
    return previous


def _validate_workspace(workspace: Path) -> Path:
    resolved = workspace.resolve()
    if not (resolved / "MODULE.bazel").is_file():
        msg = f"{resolved} is not a Bazel module (missing MODULE.bazel)"
        raise SetupError(msg)
    return resolved


def _preflight_initialize(workspace: Path, templates: tuple[Template, ...]) -> None:
    # This is not a filesystem transaction, but rejecting malformed blocks
    # prevents predictable partial setup.
    for template in templates:
        path = workspace / template.path
        if template.ownership is Ownership.MANAGED_BLOCK and path.exists():
            parse_blocks(path.read_text(encoding="utf-8"))


def _json_extends(path: Path, expected: str) -> bool:
    try:
        decoded: object = json.loads(  # pyright: ignore[reportAny]
            path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(decoded, dict):
        return False
    raw = cast("dict[object, object]", decoded)
    return raw.get("extends") == expected


def _message(*parts: str) -> str:
    return " ".join(parts)


def _policy_block_issues(
    workspace: Path,
    templates: tuple[Template, ...],
) -> list[str]:
    by_path = {template.path: template for template in templates}
    issues: list[str] = []
    for relative in POLICY_BLOCK_PATHS:
        template = by_path.get(relative)
        path = workspace / relative
        if template is None or not path.exists():
            continue
        assert template.block_id is not None
        content = path.read_text(encoding="utf-8")
        if content.strip() and template.block_id not in parse_blocks(content):
            issues.append(
                _message(
                    f"existing {relative} has policy content outside a bazel_devtools block;",
                    "move it aside, run setup init, then merge intentional overrides into",
                    "the generated block",
                )
            )
    return issues


def _python_policy_issues(
    workspace: Path,
    templates: tuple[Template, ...],
) -> list[str]:
    template_paths = {template.path for template in templates}
    issues: list[str] = []
    ruff = workspace / ".ruff.toml"
    if (
        ".ruff.toml" in template_paths
        and ruff.exists()
        and not RUFF_EXTEND_PATTERN.search(ruff.read_text(encoding="utf-8"))
    ):
        issues.append(
            _message(
                "existing .ruff.toml does not extend .bazel_devtools/ruff.toml; add the managed",
                "baseline as its top-level extend before initializing",
            )
        )

    basedpyright = workspace / "basedpyright.json"
    if (
        "basedpyright.json" in template_paths
        and basedpyright.exists()
        and not _json_extends(basedpyright, ".bazel_devtools/basedpyright.json")
    ):
        issues.append(
            _message(
                "existing basedpyright.json does not extend",
                ".bazel_devtools/basedpyright.json; add that inheritance before initializing",
            )
        )

    pyright = workspace / "pyrightconfig.json"
    if (
        "pyrightconfig.json" in template_paths
        and pyright.exists()
        and not _json_extends(pyright, "basedpyright.json")
    ):
        issues.append(
            _message(
                "existing pyrightconfig.json does not extend basedpyright.json; migrate",
                "persistent policy to basedpyright.json because ide-sync owns pyrightconfig.json",
            )
        )
    return issues


def _alternate_python_policy_issues(
    workspace: Path,
    templates: tuple[Template, ...],
) -> list[str]:
    template_paths = {template.path for template in templates}
    issues: list[str] = []
    if ".ruff.toml" in template_paths and (workspace / "ruff.toml").exists():
        issues.append(
            _message(
                "existing ruff.toml would be bypassed by bazel_devtools' explicit .ruff.toml;",
                "migrate its settings into .ruff.toml and keep the managed extend",
            )
        )
    if "basedpyright.json" in template_paths and (workspace / "basedpyrightconfig.json").exists():
        issues.append(
            _message(
                "existing basedpyrightconfig.json would be bypassed by basedpyright.json;",
                "migrate its settings into basedpyright.json and keep the managed extends key",
            )
        )

    pyproject = workspace / "pyproject.toml"
    if not pyproject.exists():
        return issues
    content = pyproject.read_text(encoding="utf-8")
    if ".ruff.toml" in template_paths and PYPROJECT_RUFF_PATTERN.search(content):
        issues.append(
            _message(
                "existing Ruff policy in pyproject.toml would be bypassed by .ruff.toml;",
                "migrate the [tool.ruff] settings into .ruff.toml before initializing",
            )
        )
    if "basedpyright.json" in template_paths and PYPROJECT_PYRIGHT_PATTERN.search(content):
        issues.append(
            _message(
                "existing Pyright policy in pyproject.toml would be bypassed by basedpyright.json;",
                "migrate it into basedpyright.json before initializing",
            )
        )
    return issues


def _dedicated_file_issues(
    workspace: Path,
    templates: tuple[Template, ...],
) -> list[str]:
    by_path = {template.path: template for template in templates}
    issues: list[str] = []
    for relative, block_id in DEDICATED_BLOCK_PATHS.items():
        template = by_path.get(relative)
        path = workspace / relative
        if template is None or not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        if content.strip() and block_id not in parse_blocks(content):
            issues.append(
                _message(
                    f"existing {relative} occupies a bazel_devtools integration path;",
                    "move or merge it explicitly before initializing",
                )
            )
    return issues


def _bazel_graph_issues(
    workspace: Path,
    templates: tuple[Template, ...],
) -> list[str]:
    template_paths = {template.path for template in templates}
    issues: list[str] = []
    module = workspace / "MODULE.bazel"
    module_template = next(
        (template for template in templates if template.path == "MODULE.bazel"),
        None,
    )
    if module_template is not None and module_template.content.strip():
        content = module.read_text(encoding="utf-8")
        blocks = parse_blocks(content)
        managed = blocks.get("ide-dependencies")
        unmanaged = (
            content if managed is None else content[: managed.begin] + content[managed.end :]
        )
        dependencies = sorted(
            {match.group("name") for match in MODULE_DEPENDENCY_PATTERN.finditer(unmanaged)}
        )
        if dependencies:
            issues.append(
                _message(
                    "existing MODULE.bazel declarations overlap bazel_devtools:",
                    f"{', '.join(dependencies)}; reconcile them with the managed",
                    "ide-dependencies block before initializing",
                )
            )
        if MODULE_SYMBOL_PATTERN.search(unmanaged):
            issues.append(
                _message(
                    "existing MODULE.bazel symbol bazel_devtools_llvm conflicts with the",
                    "managed extension name",
                )
            )

    build = workspace / "BUILD.bazel"
    if "BUILD.bazel" in template_paths and build.exists():
        content = build.read_text(encoding="utf-8")
        blocks = parse_blocks(content)
        if "root-aliases" not in blocks:
            targets = sorted(
                {match.group("name") for match in ROOT_TARGET_PATTERN.finditer(content)}
            )
            if targets:
                issues.append(
                    _message(
                        "existing root BUILD targets reserve bazel_devtools names:",
                        f"{', '.join(targets)}; rename or explicitly reconcile them before",
                        "initializing",
                    )
                )
    return issues


def _presubmit_adoption_issues(
    workspace: Path,
    templates: tuple[Template, ...],
) -> list[str]:
    by_path = {template.path: template for template in templates}
    issues: list[str] = []
    pre_commit_template = by_path.get(".pre-commit-config.yaml")
    pre_commit = workspace / ".pre-commit-config.yaml"
    has_hook = pre_commit.exists() and PRE_COMMIT_HOOK_PATTERN.search(
        pre_commit.read_text(encoding="utf-8")
    )
    if pre_commit_template is not None and pre_commit.exists() and not has_hook:
        issues.append(
            _message(
                "existing .pre-commit-config.yaml does not include the bazel-devtools-check hook;",
                "merge the generated local hook before initializing",
            )
        )

    workflow_template = by_path.get(".github/workflows/bazel-devtools.yml")
    workflow = workspace / ".github/workflows/bazel-devtools.yml"
    if (
        workflow_template is not None
        and workflow.exists()
        and workflow.read_text(encoding="utf-8") != workflow_template.content
    ):
        issues.append(
            _message(
                "existing .github/workflows/bazel-devtools.yml occupies the managed CI path;",
                "move or reconcile it before initializing",
            )
        )
    return issues


def _brownfield_issues(
    workspace: Path,
    templates: tuple[Template, ...],
) -> list[str]:
    return [
        *_policy_block_issues(workspace, templates),
        *_python_policy_issues(workspace, templates),
        *_alternate_python_policy_issues(workspace, templates),
        *_dedicated_file_issues(workspace, templates),
        *_bazel_graph_issues(workspace, templates),
        *_presubmit_adoption_issues(workspace, templates),
    ]


def _plan_template(workspace: Path, template: Template, result: Result) -> None:
    path = workspace / template.path
    if template.ownership is Ownership.CREATE_ONLY:
        if path.exists():
            result.messages.append(f"would preserve existing {template.path}")
        else:
            result.created.append(template.path)
        return
    if template.ownership is Ownership.MANAGED_FILE:
        if path.exists():
            result.messages.append(f"would adopt existing managed file {template.path}")
        else:
            result.created.append(template.path)
        return

    assert template.block_id is not None
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    blocks = parse_blocks(content)
    if template.block_id in blocks:
        result.messages.append(
            f"would preserve existing block {template.block_id} in {template.path}"
        )
    elif content:
        result.changed.append(template.path)
    else:
        result.created.append(template.path)


def plan_initialize(workspace: Path, templates: Iterable[Template] = TEMPLATES) -> Result:
    """Preview first-time installation without modifying the workspace."""
    templates = tuple(templates)
    _validate_templates(templates)
    workspace = _validate_workspace(workspace)
    state = _read_state(workspace)
    if state["entries"]:
        result = doctor(workspace, templates)
        result.messages.insert(0, "bazel_devtools is already initialized; no init changes planned")
        return result

    _preflight_initialize(workspace, templates)
    result = Result.empty()
    for template in templates:
        _plan_template(workspace, template, result)
    result.conflicts.extend(_brownfield_issues(workspace, templates))
    if result.conflicts:
        result.messages.append("setup init is blocked until the adoption issues are resolved")
    else:
        result.messages.append("setup plan is safe; run setup init to apply it")
    return result


def _initialize_template(
    workspace: Path,
    template: Template,
    entries: dict[str, _StateEntry],
    result: Result,
) -> None:
    path = workspace / template.path
    path.parent.mkdir(parents=True, exist_ok=True)
    if template.ownership is Ownership.CREATE_ONLY:
        if path.exists():
            result.messages.append(f"preserved existing {template.path}")
        else:
            path.write_text(template.content, encoding="utf-8")
            result.created.append(template.path)
        return
    if template.ownership is Ownership.MANAGED_FILE:
        if path.exists():
            result.messages.append(f"adopted existing managed file {template.path}")
        else:
            path.write_text(template.content, encoding="utf-8")
            result.created.append(template.path)
        entries[template.path] = _entry(template)
        return
    assert template.block_id is not None
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    blocks = parse_blocks(content)
    if template.block_id in blocks:
        result.messages.append(f"preserved existing block {template.block_id} in {template.path}")
    else:
        content = append_block(content, template.block_id, template.content)
        path.write_text(content, encoding="utf-8")
        if not blocks and content == render_block(template.block_id, template.content):
            result.created.append(template.path)
        else:
            result.changed.append(template.path)
    entries[template.path] = _entry(template)


def initialize(
    workspace: Path,
    templates: Iterable[Template] = TEMPLATES,
    *,
    languages: Iterable[str] = SUPPORTED_LANGUAGES,
) -> Result:
    """Install configuration while preserving existing user-owned content."""
    templates = tuple(templates)
    selected_languages = normalize_languages(languages)
    preview = plan_initialize(workspace, templates)
    if preview.conflicts:
        details = "\n  - ".join(preview.conflicts)
        msg = f"setup init requires brownfield adoption changes:\n  - {details}"
        raise SetupError(msg)
    workspace = _validate_workspace(workspace)
    state = _read_state(workspace)
    entries = state["entries"]
    if entries:
        if tuple(state["languages"]) != selected_languages:
            msg = "language selection is already installed; use setup upgrade to change it"
            raise SetupError(msg)
        result = doctor(workspace, templates)
        result.messages.insert(0, "bazel_devtools is already initialized")
        return result
    result = Result.empty()
    _preflight_initialize(workspace, templates)
    for template in templates:
        _initialize_template(workspace, template, entries, result)

    if any(template.path == ".pre-commit-config.yaml" for template in templates):
        result.messages.append("run `bazel run //:install-hooks` to enable local presubmit")

    state["installed_version"] = BAZEL_DEVTOOLS_VERSION
    state["languages"] = list(selected_languages)
    _write_state(workspace, state)
    return result


def _write_conflict_patch(
    workspace: Path,
    template: Template,
    old_base: str,
    new_base: str,
) -> str:
    safe_name = template.path.replace("/", "__").lstrip(".")
    if template.block_id:
        safe_name += f"__{template.block_id}"
    relative = UPDATES_PATH / f"{safe_name}.patch"
    path = workspace / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    patch = "".join(
        difflib.unified_diff(
            old_base.splitlines(keepends=True),
            new_base.splitlines(keepends=True),
            fromfile=f"{template.path} (installed baseline)",
            tofile=f"{template.path} (bazel_devtools {BAZEL_DEVTOOLS_VERSION})",
        )
    )
    path.write_text(patch, encoding="utf-8")
    return str(relative)


def _preflight_upgrade(
    workspace: Path,
    templates: tuple[Template, ...],
    entries: dict[str, _StateEntry],
) -> None:
    """Validate every old managed input before performing any writes."""
    new_templates = tuple(template for template in templates if template.path not in entries)
    adoption_issues = _brownfield_issues(workspace, new_templates)
    new_paths = {template.path for template in new_templates}
    active_module = next(
        (
            template
            for template in templates
            if template.path == "MODULE.bazel" and template.content.strip()
        ),
        None,
    )
    if active_module is not None and active_module.path not in new_paths:
        adoption_issues.extend(_bazel_graph_issues(workspace, (active_module,)))
    if adoption_issues:
        details = "\n  - ".join(adoption_issues)
        msg = f"upgrade requires adoption changes:\n  - {details}"
        raise SetupError(msg)
    for template in templates:
        if template.ownership is Ownership.CREATE_ONLY:
            continue
        previous = entries.get(template.path)
        if previous is None:
            continue
        path = workspace / template.path
        _validate_entry(template, previous)
        if not path.exists():
            msg = f"managed path {template.path} was deleted"
            raise SetupError(msg)
        if template.ownership is Ownership.MANAGED_BLOCK:
            assert template.block_id is not None
            blocks = parse_blocks(path.read_text(encoding="utf-8"))
            if template.block_id not in blocks:
                msg = f"managed block {template.block_id!r} was removed from {template.path}"
                raise SetupError(msg)


def _upgrade_conflicts(
    workspace: Path,
    templates: tuple[Template, ...],
    entries: dict[str, _StateEntry],
) -> list[tuple[Template, str]]:
    """Find three-way conflicts without changing installed configuration."""
    conflicts: list[tuple[Template, str]] = []
    for template in templates:
        if template.ownership is Ownership.CREATE_ONLY:
            continue
        previous = entries.get(template.path)
        if previous is None:
            continue
        old_base = _validate_entry(template, previous)["base"]
        path = workspace / template.path
        if template.ownership is Ownership.MANAGED_FILE:
            current = path.read_text(encoding="utf-8")
            if current not in (old_base, template.content) and template.content != old_base:
                conflicts.append((template, old_base))
            continue

        assert template.block_id is not None
        block = parse_blocks(path.read_text(encoding="utf-8"))[template.block_id]
        normalized_old = old_base.rstrip("\n") + "\n"
        normalized_new = template.content.rstrip("\n") + "\n"
        if block.body not in (normalized_old, normalized_new) and normalized_new != normalized_old:
            conflicts.append((template, old_base))
    return conflicts


def _adopt_new_managed_template(
    workspace: Path,
    template: Template,
    entries: dict[str, _StateEntry],
    result: Result,
) -> None:
    path = workspace / template.path
    path.parent.mkdir(parents=True, exist_ok=True)
    if template.ownership is Ownership.MANAGED_FILE:
        if path.exists():
            result.messages.append(f"adopted existing managed file {template.path}")
        else:
            path.write_text(template.content, encoding="utf-8")
            result.created.append(template.path)
    else:
        assert template.block_id is not None
        content = path.read_text(encoding="utf-8") if path.exists() else ""
        if template.block_id in parse_blocks(content):
            result.messages.append(f"adopted existing block {template.block_id} in {template.path}")
        else:
            path.write_text(
                append_block(content, template.block_id, template.content),
                encoding="utf-8",
            )
            (result.changed if content else result.created).append(template.path)
    entries[template.path] = _entry(template)


def _upgrade_managed_file(
    workspace: Path,
    template: Template,
    old_base: str,
    entries: dict[str, _StateEntry],
    result: Result,
) -> None:
    path = workspace / template.path
    current = path.read_text(encoding="utf-8")
    if current == old_base:
        if current != template.content:
            path.write_text(template.content, encoding="utf-8")
            result.changed.append(template.path)
        entries[template.path] = _entry(template)
    elif current == template.content:
        entries[template.path] = _entry(template)
        result.messages.append(f"accepted resolved update in {template.path}")
    elif template.content == old_base:
        result.messages.append(f"preserved override in {template.path}")
    else:
        patch_path = _write_conflict_patch(workspace, template, old_base, template.content)
        result.conflicts.append(template.path)
        result.messages.append(f"review upstream changes in {patch_path}")


def _upgrade_managed_block(
    workspace: Path,
    template: Template,
    old_base: str,
    entries: dict[str, _StateEntry],
    result: Result,
) -> None:
    assert template.block_id is not None
    path = workspace / template.path
    content = path.read_text(encoding="utf-8")
    block = parse_blocks(content).get(template.block_id)
    if block is None:
        msg = f"managed block {template.block_id!r} was removed from {template.path}"
        raise SetupError(msg)
    normalized_old = old_base.rstrip("\n") + "\n"
    normalized_new = template.content.rstrip("\n") + "\n"
    if block.body == normalized_old:
        if block.body != normalized_new:
            path.write_text(replace_block(content, block, template.content), encoding="utf-8")
            result.changed.append(template.path)
        entries[template.path] = _entry(template)
    elif block.body == normalized_new:
        entries[template.path] = _entry(template)
        result.messages.append(
            f"accepted resolved update in block {template.block_id} of {template.path}"
        )
    elif normalized_new == normalized_old:
        result.messages.append(
            f"preserved override in block {template.block_id} of {template.path}"
        )
    else:
        patch_path = _write_conflict_patch(workspace, template, old_base, template.content)
        result.conflicts.append(f"{template.path}:{template.block_id}")
        result.messages.append(f"review upstream changes in {patch_path}")


def _upgrade_template(
    workspace: Path,
    template: Template,
    entries: dict[str, _StateEntry],
    result: Result,
) -> None:
    path = workspace / template.path
    if template.ownership is Ownership.CREATE_ONLY:
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(template.content, encoding="utf-8")
            result.created.append(template.path)
        return
    previous = entries.get(template.path)
    if previous is None:
        _adopt_new_managed_template(workspace, template, entries, result)
        return
    old_base = _validate_entry(template, previous)["base"]
    if template.ownership is Ownership.MANAGED_FILE:
        _upgrade_managed_file(workspace, template, old_base, entries, result)
    else:
        _upgrade_managed_block(workspace, template, old_base, entries, result)


def upgrade(
    workspace: Path,
    templates: Iterable[Template] = TEMPLATES,
    *,
    languages: Iterable[str] = SUPPORTED_LANGUAGES,
) -> Result:
    """Upgrade pristine policy and preserve or report local overrides."""
    templates = tuple(templates)
    selected_languages = normalize_languages(languages)
    _validate_templates(templates)
    workspace = _validate_workspace(workspace)
    state = _read_state(workspace)
    entries = state["entries"]
    if not entries:
        msg = "bazel_devtools is not initialized; run setup init first"
        raise SetupError(msg)
    result = Result.empty()
    _preflight_upgrade(workspace, templates, entries)
    conflicts = _upgrade_conflicts(workspace, templates, entries)
    if conflicts:
        for template, old_base in conflicts:
            patch_path = _write_conflict_patch(workspace, template, old_base, template.content)
            conflict = (
                f"{template.path}:{template.block_id}"
                if template.block_id is not None
                else template.path
            )
            result.conflicts.append(conflict)
            result.messages.append(f"review upstream changes in {patch_path}")
        result.messages.append("installed version was not advanced because updates require review")
        if tuple(state["languages"]) != selected_languages:
            result.messages.append(
                "language selection was not changed because updates require review"
            )
        return result

    for template in templates:
        _upgrade_template(workspace, template, entries, result)

    if ".pre-commit-config.yaml" in result.created:
        result.messages.append("run `bazel run //:install-hooks` to enable local presubmit")

    active_paths = {
        template.path for template in templates if template.ownership is not Ownership.CREATE_ONLY
    }
    for retired in sorted(set(entries) - active_paths):
        del entries[retired]
        result.messages.append(f"retired management of {retired}; left file unchanged")

    if result.conflicts:
        result.messages.append("installed version was not advanced because updates require review")
        if tuple(state["languages"]) != selected_languages:
            result.messages.append(
                "language selection was not changed because updates require review"
            )
    else:
        state["installed_version"] = BAZEL_DEVTOOLS_VERSION
        state["languages"] = list(selected_languages)
    _write_state(workspace, state)
    return result


def _inspect_template(
    workspace: Path,
    template: Template,
    entries: dict[str, _StateEntry],
    result: Result,
) -> None:
    path = workspace / template.path
    if not path.exists():
        if template.ownership is Ownership.CREATE_ONLY:
            result.messages.append(f"optional user-owned file missing: {template.path}")
            return
        msg = f"managed path missing: {template.path}"
        raise SetupError(msg)
    if template.ownership is Ownership.CREATE_ONLY:
        return
    old_base = _validate_entry(template, entries.get(template.path))["base"]
    if template.ownership is Ownership.MANAGED_FILE:
        if path.read_text(encoding="utf-8") != old_base:
            result.messages.append(f"local override in {template.path}")
        return
    assert template.block_id is not None
    block = parse_blocks(path.read_text(encoding="utf-8")).get(template.block_id)
    if block is None:
        msg = f"managed block {template.block_id!r} missing from {template.path}"
        raise SetupError(msg)
    if block.body != old_base.rstrip("\n") + "\n":
        result.messages.append(f"local override in block {template.block_id} of {template.path}")


def doctor(workspace: Path, templates: Iterable[Template] = TEMPLATES) -> Result:
    """Validate setup state and report safe local overrides."""
    templates = tuple(templates)
    _validate_templates(templates)
    workspace = _validate_workspace(workspace)
    state = _read_state(workspace)
    entries = state["entries"]
    if not entries:
        msg = "bazel_devtools is not initialized"
        raise SetupError(msg)
    result = Result.empty()
    for template in templates:
        _inspect_template(workspace, template, entries, result)

    pre_commit = workspace / ".pre-commit-config.yaml"
    if pre_commit.exists() and not PRE_COMMIT_HOOK_PATTERN.search(
        pre_commit.read_text(encoding="utf-8")
    ):
        msg = ".pre-commit-config.yaml is missing the bazel-devtools-check hook"
        raise SetupError(msg)

    languages = ", ".join(state["languages"])
    version = state.get("installed_version")
    result.messages.append(
        f"bazel_devtools setup is structurally valid (installed {version}; languages: {languages})"
    )
    return result
