from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from typing import final, override
from unittest.mock import patch

from tools.bazel_support import (
    bazel_command,
    bazel_workspace,
    main_repo_source_path,
    run_bazel,
)


@final
class BazelSupportTest(unittest.TestCase):
    temp: tempfile.TemporaryDirectory[str]
    root: Path

    def __init__(self, method_name: str = "runTest") -> None:
        super().__init__(method_name)
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    @override
    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_workspace_prefers_explicit_override(self) -> None:
        selected = self.root / "selected"
        with patch.dict(
            os.environ,
            {
                "BAZEL_DEVTOOLS_WORKSPACE": str(selected),
                "BUILD_WORKSPACE_DIRECTORY": str(self.root / "ignored"),
            },
        ):
            self.assertEqual(selected, bazel_workspace())

    def test_command_places_options_around_bazel_command(self) -> None:
        with patch.dict(
            os.environ,
            {
                "BAZEL_DEVTOOLS_BAZEL_STARTUP_OPTIONS": "--output_base=/tmp/output",
                "BAZEL_DEVTOOLS_BAZEL_COMMAND_OPTIONS": "--repository_cache=/tmp/cache",
            },
        ):
            actual = bazel_command(("query", "//..."))

        self.assertEqual(
            [
                "bazel",
                "--output_base=/tmp/output",
                "query",
                "--repository_cache=/tmp/cache",
                "//...",
            ],
            actual,
        )

    def test_run_returns_stdout_and_raises_with_bazel_output(self) -> None:
        fake_bazel = self.root / "bazel"
        fake_bazel.write_text(
            """#!/bin/sh
if [ "$1" = "fail" ]; then
  echo "failure output" >&2
  exit 7
fi
echo "query output"
""",
            encoding="utf-8",
        )
        fake_bazel.chmod(0o755)
        with patch.dict(
            os.environ,
            {
                "PATH": str(self.root),
                "BAZEL_DEVTOOLS_BAZEL_STARTUP_OPTIONS": "",
                "BAZEL_DEVTOOLS_BAZEL_COMMAND_OPTIONS": "",
            },
        ):
            self.assertEqual("query output\n", run_bazel(self.root, "query"))
            with self.assertRaisesRegex(RuntimeError, "failure output"):
                run_bazel(self.root, "fail")

    def test_source_label_path_accepts_only_main_repo_labels(self) -> None:
        self.assertEqual(Path("pkg/source.cc"), main_repo_source_path("//pkg:source.cc"))
        self.assertEqual(Path("root.py"), main_repo_source_path("//:root.py"))
        self.assertIsNone(main_repo_source_path("@dependency//pkg:source.cc"))
        self.assertIsNone(main_repo_source_path("//pkg"))


if __name__ == "__main__":
    unittest.main()
