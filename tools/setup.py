"""Command-line entry point for installing and upgrading bazel_devtools."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import cast

from tools.setup_lib import SetupError, doctor, initialize, plan_initialize, upgrade


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
    return parser


def main() -> int:
    """Run the requested setup lifecycle operation."""
    args = _parser().parse_args()
    command = cast("str", args.command)
    workspace = cast("Path", args.workspace)
    try:
        if command == "plan":
            result = plan_initialize(workspace)
        elif command == "init":
            result = initialize(workspace)
        elif command == "upgrade":
            result = upgrade(workspace)
        else:
            result = doctor(workspace)
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
