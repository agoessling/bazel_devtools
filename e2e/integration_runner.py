"""Scratch-workspace integration tests for the polyglot example."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from getpass import getuser
from pathlib import Path
from typing import cast, final


def _fail(message: str, output: str = "") -> None:
    if output:
        message += "\n--- command output ---\n" + output[-12000:]
    raise RuntimeError(message)


def _runfile(path: str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    runfiles = os.environ.get("RUNFILES_DIR") or os.environ.get("TEST_SRCDIR")
    workspace = os.environ.get("TEST_WORKSPACE", "_main")
    if runfiles:
        return (Path(runfiles) / workspace / candidate).resolve()
    return candidate.resolve()


def _json(path: Path) -> object:
    decoded: object = json.loads(path.read_text())  # pyright: ignore[reportAny]
    return decoded


def _object(value: object, description: str) -> dict[str, object]:
    if not isinstance(value, dict):
        _fail(f"{description} is not an object")
    raw = cast("dict[object, object]", value)
    if not all(isinstance(key, str) for key in raw):
        _fail(f"{description} contains a non-string key")
    return {key: item for key, item in raw.items() if isinstance(key, str)}


def _array(value: object, description: str) -> list[object]:
    if not isinstance(value, list):
        _fail(f"{description} is not an array")
    return cast("list[object]", value)


@final
class Integration:
    def __init__(self) -> None:
        source_workspace = Path(os.environ["BIT_WORKSPACE_DIR"]).resolve()
        source_repo = source_workspace.parents[1]
        self.scratch_repo = Path(os.environ["TEST_TMPDIR"]) / "bazel_devtools"
        shutil.copytree(source_repo, self.scratch_repo)
        self.workspace = self.scratch_repo / "examples/polyglot"
        self.bazel = Path(os.environ["BIT_BAZEL_BINARY"]).resolve()
        self.output_root = Path(os.environ["TEST_TMPDIR"]) / "bazel-output-root"
        cache_override = os.environ.get("BAZEL_DEVTOOLS_REPOSITORY_CACHE")
        default_cache = (
            Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
            / "bazel"
            / f"_bazel_{getuser()}"
            / "cache/repos/v1"
        )
        self.repository_cache = Path(cache_override) if cache_override else default_cache

    def bazel_run(
        self,
        arguments: list[str],
        *,
        expect_success: bool,
        diagnostic: str | None = None,
        workspace: Path | None = None,
    ) -> str:
        selected_workspace = workspace or self.workspace
        startup_options = [f"--output_user_root={self.output_root}"]
        command_options: list[str] = []
        if self.repository_cache.is_dir():
            command_options.append(f"--repository_cache={self.repository_cache}")
        command = [
            str(self.bazel),
            *startup_options,
            arguments[0],
            *command_options,
            "--color=no",
            "--curses=no",
            *arguments[1:],
        ]
        print(f">>> {selected_workspace.name}: {' '.join(arguments)}", flush=True)
        started = time.monotonic()
        result = subprocess.run(
            command,
            cwd=selected_workspace,
            check=False,
            env={
                **os.environ,
                "BAZEL_DEVTOOLS_BAZEL_STARTUP_OPTIONS": " ".join(startup_options),
                "BAZEL_DEVTOOLS_BAZEL_COMMAND_OPTIONS": " ".join(command_options),
                "BAZEL_DEVTOOLS_WORKSPACE": str(selected_workspace),
            },
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        output = result.stdout
        print(
            f"<<< exit {result.returncode} after {time.monotonic() - started:.1f}s",
            flush=True,
        )
        if expect_success and result.returncode != 0:
            _fail(f"expected success: {' '.join(command)}", output)
        if not expect_success and result.returncode == 0:
            _fail(f"expected failure: {' '.join(command)}", output)
        if diagnostic and diagnostic.lower() not in output.lower():
            _fail(f"missing diagnostic {diagnostic!r}: {' '.join(command)}", output)
        return output

    def prepare_greenfield(self) -> Path:
        """Create an unconfigured consumer from the example's project inputs."""
        workspace = Path(os.environ["TEST_TMPDIR"]) / "greenfield"
        workspace.mkdir()
        module = (self.workspace / "MODULE.bazel").read_text(encoding="utf-8")
        begin = "# ##BAZEL_DEVTOOLS_MANAGED_BEGIN:ide-dependencies##"
        end = "# ##BAZEL_DEVTOOLS_MANAGED_END:ide-dependencies##"
        prefix, found_begin, remainder = module.partition(begin)
        _managed, found_end, suffix = remainder.partition(end)
        if not found_begin or not found_end:
            _fail("polyglot MODULE.bazel is missing its managed dependency block")
        module = prefix.rstrip() + "\n" + suffix.lstrip("\n")
        module = module.replace(
            'path = "../.."',
            f"path = {json.dumps(str(self.scratch_repo))}",
        )
        (workspace / "MODULE.bazel").write_text(module, encoding="utf-8")
        shutil.copy2(self.workspace / ".bazelversion", workspace / ".bazelversion")
        shutil.copytree(self.workspace / "python", workspace / "python")
        return workspace

    def check_first_time_setup(self) -> None:
        """Exercise blocked brownfield adoption and clean greenfield setup."""
        workspace = self.prepare_greenfield()
        clang_tidy = workspace / ".clang-tidy"
        legacy_policy = "Checks: 'modernize-*'\n"
        clang_tidy.write_text(legacy_policy, encoding="utf-8")

        self.bazel_run(
            ["run", "@bazel_devtools//tools:setup", "--", "plan"],
            expect_success=False,
            diagnostic="existing .clang-tidy",
            workspace=workspace,
        )
        self.bazel_run(
            ["run", "@bazel_devtools//tools:setup", "--", "init"],
            expect_success=False,
            diagnostic="brownfield adoption",
            workspace=workspace,
        )
        if clang_tidy.read_text(encoding="utf-8") != legacy_policy:
            _fail("blocked setup modified the existing brownfield policy")
        if (workspace / ".bazel_devtools/state.json").exists():
            _fail("blocked setup wrote installation state")

        clang_tidy.unlink()
        output = self.bazel_run(
            ["run", "@bazel_devtools//tools:setup", "--", "plan"],
            expect_success=True,
            diagnostic="would create .bazel_devtools/ruff.toml",
            workspace=workspace,
        )
        if (workspace / ".bazel_devtools/state.json").exists() or (
            workspace / ".ruff.toml"
        ).exists():
            _fail("setup plan modified the greenfield workspace", output)

        self.bazel_run(
            ["run", "@bazel_devtools//tools:setup", "--", "init"],
            expect_success=True,
            workspace=workspace,
        )
        self.bazel_run(
            ["run", "@bazel_devtools//tools:setup", "--", "doctor"],
            expect_success=True,
            workspace=workspace,
        )
        self.bazel_run(["test", "//..."], expect_success=True, workspace=workspace)

    def replace_and_reject(
        self,
        source: str,
        fixture: str,
        target: str,
        diagnostic: str,
    ) -> None:
        path = self.workspace / source
        original = path.read_bytes()
        try:
            path.write_bytes((self.scratch_repo / fixture).read_bytes())
            self.bazel_run(
                ["test", target, "--keep_going"],
                expect_success=False,
                diagnostic=diagnostic,
            )
        finally:
            path.write_bytes(original)

    def check_opt_out(self, language: str, fixture: str, tag: str = "no-format") -> None:
        package = self.workspace / language
        source = package / (
            "greeting.py"
            if language == "python"
            else "greeting.cc"
            if language == "cpp"
            else "greeting.rs"
        )
        build = package / "BUILD.bazel"
        original_source = source.read_bytes()
        original_build = build.read_text(encoding="utf-8")
        needle = '    name = "greeting",\n'
        if needle not in original_build:
            _fail(f"cannot locate greeting target in {build}")
        try:
            source.write_bytes((self.scratch_repo / fixture).read_bytes())
            build.write_text(
                original_build.replace(needle, needle + f'    tags = ["{tag}"],\n', 1),
                encoding="utf-8",
            )
            self.bazel_run(
                ["test", f"//{language}:all"],
                expect_success=True,
            )
        finally:
            source.write_bytes(original_source)
            build.write_text(original_build, encoding="utf-8")

    def check_write_format_opt_out(self, language: str, fixture: str, tag: str) -> None:
        package = self.workspace / language
        source = package / (
            "greeting.py"
            if language == "python"
            else "greeting.cc"
            if language == "cpp"
            else "greeting.rs"
        )
        build = package / "BUILD.bazel"
        original_source = source.read_bytes()
        original_build = build.read_text(encoding="utf-8")
        violation = (self.scratch_repo / fixture).read_bytes()
        needle = '    name = "greeting",\n'
        try:
            source.write_bytes(violation)
            build.write_text(
                original_build.replace(needle, needle + f'    tags = ["{tag}"],\n', 1),
                encoding="utf-8",
            )
            self.bazel_run(
                ["run", "//:format", "--", f"//{language}:greeting"],
                expect_success=True,
            )
            if source.read_bytes() != violation:
                _fail(f"write-mode formatter ignored target tag {tag!r}")
        finally:
            source.write_bytes(original_source)
            build.write_text(original_build, encoding="utf-8")

    def check_language_isolation(self) -> None:
        builds = {
            language: self.workspace / language / "BUILD.bazel"
            for language in ("python", "cpp", "rust")
        }
        for selected in builds:
            disabled: list[tuple[Path, Path]] = []
            try:
                for language, build in builds.items():
                    if language == selected:
                        continue
                    hidden = build.with_name("BUILD.bazel.disabled")
                    build.rename(hidden)
                    disabled.append((hidden, build))
                self.bazel_run(["test", "//..."], expect_success=True)
            finally:
                for hidden, build in reversed(disabled):
                    hidden.rename(build)

    def check_format_is_scratch_only(self) -> None:
        cases = {
            "python/greeting.py": "e2e/testdata/violations/python/format.py",
            "cpp/greeting.cc": "e2e/testdata/violations/cpp/format.cc",
            "rust/greeting.rs": "e2e/testdata/violations/rust/format.rs",
        }
        for destination, fixture in cases.items():
            (self.workspace / destination).write_bytes((self.scratch_repo / fixture).read_bytes())
        unowned = self.workspace / "not_owned_by_bazel.py"
        unowned_content = "value={  'still':\t'unformatted'  }\n"
        unowned.write_text(unowned_content, encoding="utf-8")

        format_output = self.bazel_run(
            ["run", "//:format", "--", "//..."],
            expect_success=True,
        )
        for destination, fixture in cases.items():
            if (self.workspace / destination).read_bytes() == (
                self.scratch_repo / fixture
            ).read_bytes():
                _fail(f"format did not update {destination}", format_output)
        if unowned.read_text(encoding="utf-8") != unowned_content:
            _fail("format changed a file that is not owned by a Bazel target")
        self.bazel_run(["test", "//..."], expect_success=True)
        self.check_language_isolation()

    def check_ide_metadata(self) -> None:
        self.bazel_run(["run", "//:ide-sync"], expect_success=True)
        pyright = _object(_json(self.workspace / "pyrightconfig.json"), "pyrightconfig.json")
        extra_paths = _array(pyright.get("extraPaths"), "pyrightconfig.json extraPaths")
        if pyright.get("extends") != "basedpyright.json" or not extra_paths:
            _fail("pyrightconfig.json does not describe the Bazel Python roots")
        include = _array(pyright.get("include"), "pyrightconfig.json include")
        if not all(isinstance(item, str) for item in include):
            _fail("pyrightconfig.json include contains a non-string value")
        python_sources = {item for item in include if isinstance(item, str)}
        if not {
            "python/greeting.py",
            "python/greeting_test.py",
        }.issubset(python_sources):
            _fail("pyrightconfig.json omits Bazel-owned Python sources")
        if "python/generated_unformatted.py" in python_sources:
            _fail("pyrightconfig.json includes a generated Python source")
        if "not_owned_by_bazel.py" in python_sources:
            _fail("pyrightconfig.json includes a non-target-owned Python source")
        commands = _array(_json(self.workspace / "compile_commands.json"), "compile_commands")
        command_files = (_object(entry, "compile command").get("file") for entry in commands)
        if not any(
            isinstance(path, str) and path.endswith("cpp/greeting.cc") for path in command_files
        ):
            _fail("compile_commands.json does not contain cpp/greeting.cc")
        rust_project = _object(_json(self.workspace / "rust-project.json"), "rust-project.json")
        if not _array(rust_project.get("crates"), "rust-project.json crates"):
            _fail("rust-project.json contains no crates")

        nvim = _runfile(os.environ["BAZEL_DEVTOOLS_NVIM"])
        script = self.scratch_repo / "e2e/minimal_neovim_probe.lua"
        result = subprocess.run(
            [str(nvim), "--clean", "--headless", "-u", "NONE", "-l", str(script)],
            cwd=self.workspace,
            env={**os.environ, "BAZEL_DEVTOOLS_WORKSPACE": str(self.workspace)},
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if result.returncode != 0:
            _fail("minimal Neovim metadata probe failed", result.stdout)

    def run_presubmit_hook(
        self,
        hook: Path,
        environment: dict[str, str],
        *,
        expect_success: bool,
        diagnostic: str | None = None,
    ) -> str:
        """Run an installed hook and check its expected result."""
        result = subprocess.run(
            [str(hook)],
            cwd=self.workspace,
            env=environment,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if expect_success and result.returncode != 0:
            _fail("expected installed pre-commit hook to pass", result.stdout)
        if not expect_success and result.returncode == 0:
            _fail("expected installed pre-commit hook to fail", result.stdout)
        if diagnostic and diagnostic.lower() not in result.stdout.lower():
            _fail(f"pre-commit output omitted {diagnostic!r}", result.stdout)
        return result.stdout

    def check_presubmit_failures(self, hook: Path, environment: dict[str, str]) -> None:
        """Prove representative hook failures are check-only."""
        failures = (
            ("e2e/testdata/violations/python/format.py", "reformat"),
            ("e2e/testdata/violations/python/ruff_lint.py", "D100"),
            ("e2e/testdata/violations/python/type_error.py", "not assignable"),
        )
        source = self.workspace / "python/greeting.py"
        original = source.read_bytes()
        for fixture, diagnostic in failures:
            violation = (self.scratch_repo / fixture).read_bytes()
            source.write_bytes(violation)
            subprocess.run(["git", "add", str(source)], cwd=self.workspace, check=True)
            self.run_presubmit_hook(
                hook,
                environment,
                expect_success=False,
                diagnostic=diagnostic,
            )
            if source.read_bytes() != violation:
                _fail("check-only pre-commit hook modified a source file")
        source.write_bytes(original)
        subprocess.run(["git", "add", str(source)], cwd=self.workspace, check=True)

    def check_presubmit(self) -> None:
        """Exercise generated config, explicit installation, and check-only failure behavior."""
        config = self.workspace / ".pre-commit-config.yaml"
        workflow = self.workspace / ".github/workflows/bazel-devtools.yml"
        if "id: bazel-devtools-check" not in config.read_text(encoding="utf-8"):
            _fail("generated pre-commit configuration is missing its Bazel hook")
        if "bazel test //... --test_output=errors" not in workflow.read_text(encoding="utf-8"):
            _fail("generated GitHub workflow does not run the canonical presubmit")
        actionlint = _runfile(os.environ["BAZEL_DEVTOOLS_ACTIONLINT"])
        actionlint_result = subprocess.run(
            [str(actionlint), str(workflow)],
            check=False,
            capture_output=True,
            text=True,
        )
        if actionlint_result.returncode != 0:
            _fail("generated GitHub workflow failed actionlint", actionlint_result.stdout)

        self.bazel_run(
            ["run", "//:pre-commit", "--", "validate-config", str(config)],
            expect_success=True,
        )
        subprocess.run(
            ["git", "init", "--quiet", "--initial-branch=master"],
            cwd=self.workspace,
            check=True,
        )
        subprocess.run(["git", "add", "-A"], cwd=self.workspace, check=True)
        self.bazel_run(["run", "//:install-hooks"], expect_success=True)
        hook = self.workspace / ".git/hooks/pre-commit"
        if not hook.is_file() or not os.access(hook, os.X_OK):
            _fail("setup did not install an executable pre-commit hook")
        if "BAZEL_DEVTOOLS_MANAGED_GIT_HOOK" not in hook.read_text(encoding="utf-8"):
            _fail("installed pre-commit hook is not marked as managed")

        binary_directory = self.workspace / ".git/bazel-devtools-test-bin"
        binary_directory.mkdir()
        bazel_wrapper = binary_directory / "bazel"
        bazel_wrapper.write_text(
            f"""#!/bin/sh
exec {json.dumps(str(self.bazel))} --output_user_root={json.dumps(str(self.output_root))} "$@"
""",
            encoding="utf-8",
        )
        bazel_wrapper.chmod(0o755)
        hook_environment = {
            **os.environ,
            "BIT_BAZELISK_BINARY": str(_runfile(os.environ["BAZEL_DEVTOOLS_BAZELISK"])),
            "PATH": str(binary_directory) + os.pathsep + os.environ.get("PATH", ""),
        }

        self.run_presubmit_hook(hook, hook_environment, expect_success=True)
        self.check_presubmit_failures(hook, hook_environment)

    def run(self) -> None:
        self.check_first_time_setup()
        self.bazel_run(
            ["run", "@bazel_devtools//tools:setup", "--", "init"],
            expect_success=True,
        )
        self.bazel_run(
            ["run", "@bazel_devtools//tools:setup", "--", "doctor"],
            expect_success=True,
        )
        self.bazel_run(["test", "//..."], expect_success=True)

        failures = (
            (
                "python/greeting.py",
                "e2e/testdata/violations/python/ruff_lint.py",
                "//python:greeting",
                "D100",
            ),
            (
                "python/greeting.py",
                "e2e/testdata/violations/python/type_error.py",
                "//python:greeting",
                "not assignable",
            ),
            (
                "python/greeting.py",
                "e2e/testdata/violations/python/format.py",
                "//python:greeting",
                "reformat",
            ),
            (
                "cpp/greeting.cc",
                "e2e/testdata/violations/cpp/format.cc",
                "//cpp:greeting",
                "clang-format",
            ),
            (
                "cpp/greeting.cc",
                "e2e/testdata/violations/cpp/clang_tidy.cc",
                "//cpp:greeting",
                "modernize-use-trailing-return-type",
            ),
            (
                "rust/greeting.rs",
                "e2e/testdata/violations/rust/format.rs",
                "//rust:greeting",
                "Diff in",
            ),
            (
                "rust/greeting.rs",
                "e2e/testdata/violations/rust/clippy.rs",
                "//rust:greeting",
                "is_empty",
            ),
        )
        for source, fixture, target, diagnostic in failures:
            self.replace_and_reject(source, fixture, target, diagnostic)

        self.check_opt_out("python", "e2e/testdata/violations/python/format.py")
        self.check_opt_out("cpp", "e2e/testdata/violations/cpp/format.cc")
        self.check_opt_out("rust", "e2e/testdata/violations/rust/format.rs")
        self.check_opt_out("python", "e2e/testdata/violations/python/ruff_lint.py", "no-lint")
        self.check_opt_out(
            "python",
            "e2e/testdata/violations/python/type_error_runtime_safe.py",
            "no-typecheck",
        )
        self.check_opt_out("cpp", "e2e/testdata/violations/cpp/clang_tidy.cc", "no-lint")
        self.check_opt_out("rust", "e2e/testdata/violations/rust/clippy.rs", "no-clippy")
        self.check_write_format_opt_out(
            "python",
            "e2e/testdata/violations/python/format.py",
            "no-ruff-format",
        )
        self.check_write_format_opt_out(
            "cpp",
            "e2e/testdata/violations/cpp/format.cc",
            "no-clang-format",
        )
        self.check_write_format_opt_out(
            "rust",
            "e2e/testdata/violations/rust/format.rs",
            "no-rustfmt",
        )
        self.check_format_is_scratch_only()
        self.check_ide_metadata()
        self.check_presubmit()


def main() -> int:
    try:
        Integration().run()
    except (OSError, RuntimeError, json.JSONDecodeError) as error:
        print(f"bazel_devtools integration test: {error}", file=sys.stderr)
        return 1
    print("bazel_devtools polyglot integration test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
