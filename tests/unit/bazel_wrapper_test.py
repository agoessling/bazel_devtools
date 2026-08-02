from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import final, override

from tools.bazel_wrapper import write_bazel_wrapper


@final
class BazelWrapperTest(unittest.TestCase):
    temp: tempfile.TemporaryDirectory[str]
    root: Path
    capture: Path
    fake_bazel: Path
    wrapper: Path

    def __init__(self, method_name: str = "runTest") -> None:
        super().__init__(method_name)
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.capture = self.root / "arguments.json"
        self.fake_bazel = self.root / "real-bazel"
        self.fake_bazel.write_text(
            """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path
Path(os.environ['BAZEL_WRAPPER_CAPTURE']).write_text(json.dumps(sys.argv[1:]))
""",
            encoding="utf-8",
        )
        self.fake_bazel.chmod(0o755)
        self.wrapper = self.root / "bazel"
        write_bazel_wrapper(
            self.wrapper,
            str(self.fake_bazel),
            ["--host_jvm_args=-Xmx1g"],
            ["--repository_cache=/cache"],
        )

    @override
    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_wrapper(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(self.wrapper), *arguments],
            capture_output=True,
            check=False,
            env={**os.environ, "BAZEL_WRAPPER_CAPTURE": str(self.capture)},
            text=True,
        )

    def test_preserves_nested_startup_options_before_build(self) -> None:
        result = self.run_wrapper("--output_base=/tmp/nested", "build", "//...")

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(
            [
                "--host_jvm_args=-Xmx1g",
                "--output_base=/tmp/nested",
                "build",
                "--repository_cache=/cache",
                "//...",
            ],
            json.loads(self.capture.read_text()),
        )

    def test_supports_hedron_action_cache_dump(self) -> None:
        result = self.run_wrapper("dump", "--action_cache")

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(
            [
                "--host_jvm_args=-Xmx1g",
                "dump",
                "--repository_cache=/cache",
                "--action_cache",
            ],
            json.loads(self.capture.read_text()),
        )

    def test_rejects_an_unknown_command(self) -> None:
        result = self.run_wrapper("--output_base=/tmp/nested", "not-a-command")

        self.assertNotEqual(0, result.returncode)
        self.assertIn("could not find a Bazel command", result.stderr)


if __name__ == "__main__":
    unittest.main()
