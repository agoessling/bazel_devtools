"""Shared helpers for Bazel-backed development tools."""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence


def bazel_workspace() -> Path:
    """Return the workspace selected for a Bazel-backed tool invocation."""
    return Path(
        os.environ.get(
            "BAZEL_DEVTOOLS_WORKSPACE",
            os.environ.get("BUILD_WORKSPACE_DIRECTORY", Path.cwd()),
        )
    ).resolve()


def bazel_options() -> tuple[list[str], list[str]]:
    """Return inherited Bazel startup and command options."""
    startup = shlex.split(os.environ.get("BAZEL_DEVTOOLS_BAZEL_STARTUP_OPTIONS", ""))
    command = shlex.split(os.environ.get("BAZEL_DEVTOOLS_BAZEL_COMMAND_OPTIONS", ""))
    return startup, command


def bazel_command(arguments: Sequence[str]) -> list[str]:
    """Build a Bazel command with inherited options in their valid positions."""
    if not arguments:
        msg = "a Bazel command is required"
        raise ValueError(msg)
    startup, command = bazel_options()
    return ["bazel", *startup, arguments[0], *command, *arguments[1:]]


def run_bazel(workspace: Path, *arguments: str) -> str:
    """Run Bazel, returning captured stdout or raising on failure."""
    result = subprocess.run(
        bazel_command(arguments),
        cwd=workspace,
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout


def main_repo_source_path(label: str) -> Path | None:
    """Convert a canonical main-repository source label to a relative path."""
    if not label.startswith("//"):
        return None
    package, separator, name = label[2:].partition(":")
    if not separator:
        return None
    return Path(package) / name if package else Path(name)
