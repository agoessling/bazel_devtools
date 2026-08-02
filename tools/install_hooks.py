"""Install bazel_devtools-managed Git hooks explicitly."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from tools.bazel_support import bazel_workspace

HOOK_MARKER = "# BAZEL_DEVTOOLS_MANAGED_GIT_HOOK"
HOOK = f"""#!/usr/bin/env bash
set -euo pipefail
{HOOK_MARKER}

workspace="$(git rev-parse --show-toplevel)"
cd "$workspace"
target="@bazel_devtools//tools:pre-commit"

bazel build "$target" --noshow_progress
pre_commit="$(
  bazel cquery "$target" --output=files 2>/dev/null |
    while IFS= read -r output; do
      case "$output" in
        *_entry_point.py) ;;
        *) printf '%s\\n' "$output"; break ;;
      esac
    done
)"
if [[ -z "$pre_commit" ]]; then
  echo "bazel_devtools: could not resolve the pinned pre-commit executable" >&2
  exit 1
fi
if [[ "$pre_commit" != /* ]]; then
  pre_commit="$workspace/$pre_commit"
fi

exec "$pre_commit" hook-impl \\
  --config=.pre-commit-config.yaml \\
  --hook-type=pre-commit \\
  --hook-dir="$(dirname "$0")" \\
  -- "$@"
"""


def _git(workspace: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=workspace,
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout.strip()


def _hooks_path_override(workspace: Path) -> str | None:
    result = subprocess.run(
        ["git", "config", "--get", "core.hooksPath"],
        cwd=workspace,
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode == 1:
        return None
    if result.returncode != 0:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout.strip() or None


def install(workspace: Path) -> Path:
    """Install or update the managed pre-commit hook in one Git repository."""
    workspace = workspace.resolve()
    repository = Path(_git(workspace, "rev-parse", "--show-toplevel")).resolve()
    if repository != workspace:
        msg = f"{workspace} is nested inside Git repository {repository}"
        raise RuntimeError(msg)
    if hooks_path := _hooks_path_override(workspace):
        msg = f"core.hooksPath is already configured as {hooks_path!r}; integrate the hook manually"
        raise RuntimeError(msg)

    rendered = _git(workspace, "rev-parse", "--git-path", "hooks/pre-commit")
    hook = Path(rendered)
    if not hook.is_absolute():
        hook = workspace / hook
    if hook.is_symlink():
        msg = f"refusing to replace symbolic-link Git hook {hook}"
        raise RuntimeError(msg)
    hook = hook.resolve()
    if hook.exists() and not hook.is_file():
        msg = f"refusing to replace non-file Git hook {hook}"
        raise RuntimeError(msg)
    if hook.exists() and HOOK_MARKER not in hook.read_text(encoding="utf-8"):
        msg = f"existing unmanaged Git hook would be overwritten: {hook}"
        raise RuntimeError(msg)

    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(HOOK, encoding="utf-8")
    hook.chmod(0o755)
    return hook


def main() -> int:
    """Install the hook selected by Bazel's invoking workspace environment."""
    try:
        hook = install(bazel_workspace())
    except (OSError, RuntimeError) as error:
        print(f"bazel_devtools: {error}", file=sys.stderr)
        return 1
    print(f"installed {hook}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
