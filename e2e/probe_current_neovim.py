"""Run the real user Neovim configuration against the polyglot example."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import cast


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--nvim", default="nvim")
    parser.add_argument("--skip-sync", action="store_true")
    args = parser.parse_args()
    workspace = cast("Path", args.workspace).resolve()
    nvim = cast("str", args.nvim)
    skip_sync = cast("bool", args.skip_sync)
    if not skip_sync:
        sync = subprocess.run(["bazel", "run", "//:ide-sync"], cwd=workspace, check=False)
        if sync.returncode:
            return sync.returncode

    repository = Path(os.environ.get("BUILD_WORKSPACE_DIRECTORY", Path.cwd()))
    script = repository / "e2e/current_neovim_probe.lua"
    result = subprocess.run(
        [
            nvim,
            "--headless",
            "-c",
            f"lua dofile({json.dumps(str(script))})",
        ],
        cwd=workspace,
        env={**os.environ, "BAZEL_DEVTOOLS_WORKSPACE": str(workspace)},
        check=False,
    )
    if result.returncode:
        print("current Neovim configuration probe failed", file=sys.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
