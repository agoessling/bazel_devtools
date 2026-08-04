"""Command-line entry point for installing and upgrading bazel_devtools."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import cast

from tools.languages import SUPPORTED_LANGUAGES, normalize_languages
from tools.setup_lib import (
    Result,
    SetupError,
    doctor,
    initialize,
    installed_languages,
    plan_initialize,
    upgrade,
)
from tools.templates import templates_for_languages


def _default_workspace() -> Path:
    for variable in ("BUILD_WORKSPACE_DIRECTORY", "BUILD_WORKING_DIRECTORY"):
        if workspace := os.environ.get(variable):
            return Path(workspace)
    return Path.cwd()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bazel_devtools setup")
    parser.add_argument(
        "command",
        choices=("plan", "init", "upgrade", "doctor"),
        help="operation to perform",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=_default_workspace(),
        help="consuming Bazel workspace (defaults to Bazel's invocation workspace)",
    )
    parser.add_argument(
        "--language",
        action="append",
        choices=SUPPORTED_LANGUAGES,
        help=(
            "language integration to install (repeatable; defaults to all on init, "
            "or the persisted selection afterward)"
        ),
    )
    return parser


def _selected_languages(
    command: str,
    workspace: Path,
    requested: list[str] | None,
) -> tuple[str, ...]:
    existing = installed_languages(workspace)
    normalized_request = normalize_languages(requested) if requested else None
    if (
        command in ("plan", "init")
        and existing
        and normalized_request
        and normalized_request != existing
    ):
        msg = "language selection is already installed; use setup upgrade to change it"
        raise SetupError(msg)
    if command == "doctor" and normalized_request and normalized_request != existing:
        msg = "setup doctor validates installed languages; use setup upgrade to change them"
        raise SetupError(msg)
    return normalize_languages(normalized_request or existing or SUPPORTED_LANGUAGES)


def _run(command: str, workspace: Path, requested: list[str] | None) -> Result:
    selected = _selected_languages(command, workspace, requested)
    templates = templates_for_languages(selected)
    if command == "plan":
        return plan_initialize(workspace, templates)
    if command == "init":
        return initialize(workspace, templates, languages=selected)
    if command == "upgrade":
        return upgrade(workspace, templates, languages=selected)
    return doctor(workspace, templates)


def main() -> int:
    """Run the requested setup lifecycle operation."""
    args = _parser().parse_args()
    command = cast("str", args.command)
    workspace = cast("Path", args.workspace)
    try:
        requested = cast("list[str] | None", args.language)
        result = _run(command, workspace, requested)
    except SetupError as error:
        print(f"bazel_devtools: {error}", file=sys.stderr)
        return 1

    plan = command == "plan"
    for path in result.created:
        print(f"{'would create' if plan else 'created'} {path}")
    for path in result.changed:
        print(f"{'would update' if plan else 'updated'} {path}")
    for message in result.messages:
        print(message)
    if result.conflicts:
        heading = "setup plan requires review:" if plan else "upgrade requires review:"
        print(heading, file=sys.stderr)
        for conflict in result.conflicts:
            print(f"  {conflict}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
