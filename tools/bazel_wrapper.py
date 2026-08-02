"""Helpers for tools that recursively invoke Bazel."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

BAZEL_COMMANDS = frozenset(
    {
        "analyze-profile",
        "aquery",
        "build",
        "canonicalize-flags",
        "clean",
        "config",
        "coverage",
        "cquery",
        "dump",
        "fetch",
        "help",
        "info",
        "license",
        "mobile-install",
        "mod",
        "print_action",
        "query",
        "run",
        "shutdown",
        "sync",
        "test",
        "version",
    }
)


def write_bazel_wrapper(
    path: Path,
    bazel: str,
    startup_options: list[str],
    command_options: list[str],
) -> None:
    """Write a Bazel proxy that injects options on the correct side of the command."""
    script = f"""#!/usr/bin/env python3
import os
import sys
bazel = {bazel!r}
startup = {startup_options!r}
common = {command_options!r}
commands = {sorted(BAZEL_COMMANDS)!r}
arguments = sys.argv[1:]
try:
    command_index = next(
        index for index, argument in enumerate(arguments)
        if argument in commands
    )
except StopIteration:
    raise SystemExit('bazel_devtools wrapper could not find a Bazel command')
os.execv(
    bazel,
    [bazel, *startup, *arguments[:command_index + 1],
     *common, *arguments[command_index + 1:]],
)
"""
    path.write_text(
        script,
        encoding="utf-8",
    )
    path.chmod(0o755)
