"""Run the pinned pre-commit framework from the invoking Bazel workspace."""

from __future__ import annotations

import os
import runpy

from tools.bazel_support import bazel_workspace


def main() -> None:
    """Delegate to pre-commit after restoring the consuming workspace."""
    os.chdir(bazel_workspace())
    runpy.run_module("pre_commit.main", run_name="__main__")


if __name__ == "__main__":
    main()
