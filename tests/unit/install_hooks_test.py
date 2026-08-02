from __future__ import annotations

import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import final, override

from tools.install_hooks import HOOK_MARKER, install


@final
class InstallHooksTest(unittest.TestCase):
    temp: tempfile.TemporaryDirectory[str]
    workspace: Path
    hook: Path

    def __init__(self, method_name: str = "runTest") -> None:
        super().__init__(method_name)
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name)
        subprocess.run(["git", "init", "--quiet"], cwd=self.workspace, check=True)
        self.hook = self.workspace / ".git/hooks/pre-commit"

    @override
    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_install_is_idempotent_and_executable(self) -> None:
        first = install(self.workspace)
        original = self.hook.read_bytes()
        second = install(self.workspace)

        self.assertEqual(self.hook, first)
        self.assertEqual(first, second)
        self.assertEqual(original, self.hook.read_bytes())
        self.assertIn(HOOK_MARKER, self.hook.read_text(encoding="utf-8"))
        self.assertNotEqual(0, self.hook.stat().st_mode & stat.S_IXUSR)
        subprocess.run(["bash", "-n", str(self.hook)], check=True)

    def test_install_preserves_an_unmanaged_hook(self) -> None:
        existing = "#!/bin/sh\nexit 0\n"
        self.hook.write_text(existing, encoding="utf-8")

        with self.assertRaisesRegex(RuntimeError, "unmanaged Git hook"):
            install(self.workspace)

        self.assertEqual(existing, self.hook.read_text(encoding="utf-8"))

    def test_install_refuses_a_configured_hooks_path(self) -> None:
        subprocess.run(
            ["git", "config", "core.hooksPath", ".githooks"],
            cwd=self.workspace,
            check=True,
        )

        with self.assertRaisesRegex(RuntimeError, "core.hooksPath"):
            install(self.workspace)

        self.assertFalse((self.workspace / ".githooks/pre-commit").exists())


if __name__ == "__main__":
    unittest.main()
