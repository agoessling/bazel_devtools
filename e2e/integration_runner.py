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

_LANGUAGE_MODULE_EXTRAS = {
    "cpp": 'bazel_dep(name = "rules_cc", version = "0.2.22")\n',
    "rust": """\
bazel_dep(name = "rules_rust", version = "0.73.0")

rust = use_extension("@rules_rust//rust:extensions.bzl", "rust")
rust.toolchain(
    edition = "2024",
    versions = ["1.89.0"],
)
use_repo(rust, "rust_toolchains")
register_toolchains("@rust_toolchains//:all")
""",
    "typescript": "",
}

_LANGUAGE_POLICY_PATHS = {
    "python": (
        ".bazel_devtools/basedpyright.json",
        ".bazel_devtools/ruff.toml",
        ".ruff.toml",
        "basedpyright.json",
        "pyrightconfig.json",
    ),
    "cpp": (".clang-format", ".clang-tidy"),
    "rust": ("rustfmt.toml",),
    "typescript": (
        ".bazel_devtools/biome.json",
        ".bazel_devtools/tsconfig.json",
        "biome.json",
        "tsconfig.json",
    ),
}

_LANGUAGE_ASPECT_MARKERS = {
    "python": "checks:python.bzl",
    "cpp": "checks:cpp.bzl",
    "rust": "checks:rust.bzl",
    "typescript": "checks:typescript.bzl",
}

_REQUIRED_CLANG_TIDY_CHECKS = {
    "bugprone-easily-swappable-parameters",
    "bugprone-narrowing-conversions",
    "bugprone-unchecked-optional-access",
    "cppcoreguidelines-avoid-c-arrays",
    "cppcoreguidelines-avoid-non-const-global-variables",
    "cppcoreguidelines-narrowing-conversions",
    "cppcoreguidelines-pro-bounds-array-to-pointer-decay",
    "cppcoreguidelines-pro-bounds-pointer-arithmetic",
    "cppcoreguidelines-special-member-functions",
    "misc-include-cleaner",
    "readability-function-cognitive-complexity",
    "readability-implicit-bool-conversion",
}

_EXCLUDED_CLANG_TIDY_CHECKS = {
    "clang-analyzer-optin.performance.GCDAntipattern",
    "clang-analyzer-optin.performance.Padding",
    "cppcoreguidelines-avoid-do-while",
    "cppcoreguidelines-avoid-magic-numbers",
    "cppcoreguidelines-macro-to-enum",
    "cppcoreguidelines-non-private-member-variables-in-classes",
    "cppcoreguidelines-owning-memory",
    "cppcoreguidelines-pro-bounds-avoid-unchecked-container-access",
    "cppcoreguidelines-pro-bounds-constant-array-index",
    "google-readability-function-size",
    "google-readability-todo",
    "misc-no-recursion",
    "misc-non-private-member-variables-in-classes",
    "modernize-macro-to-enum",
    "modernize-min-max-use-initializer-list",
    "modernize-pass-by-value",
    "modernize-raw-string-literal",
    "modernize-return-braced-init-list",
    "modernize-use-constraints",
    "modernize-use-trailing-return-type",
    "performance-enum-size",
    "portability-restrict-system-includes",
    "readability-convert-member-functions-to-static",
    "readability-function-size",
    "readability-identifier-length",
    "readability-magic-numbers",
    "readability-math-missing-parentheses",
}

_EXCLUDED_CLANG_TIDY_PREFIXES = (
    "clang-analyzer-fuchsia.",
    "clang-analyzer-optin.mpi.",
    "clang-analyzer-optin.osx.",
    "clang-analyzer-osx.",
    "clang-analyzer-webkit.",
    "google-objc-",
)

_CLANG_TIDY_CHECK_COUNT = 421


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
        module = f"""\
module(name = "bazel_devtools_python_greenfield")

bazel_dep(name = "bazel_devtools", version = "0.1.0")
local_path_override(
    module_name = "bazel_devtools",
    path = {json.dumps(str(self.scratch_repo))},
)

bazel_dep(name = "aspect_rules_py", version = "1.11.7")

interpreters = use_extension(
    "@aspect_rules_py//py/unstable:extension.bzl",
    "python_interpreters",
)
interpreters.toolchain(
    is_default = True,
    python_version = "3.14",
)
use_repo(interpreters, "python_interpreters")
register_toolchains("@python_interpreters//:all")
"""
        (workspace / "MODULE.bazel").write_text(module, encoding="utf-8")
        shutil.copy2(self.workspace / ".bazelversion", workspace / ".bazelversion")
        shutil.copytree(self.workspace / "python", workspace / "python")
        return workspace

    def prepare_language_workspace(self, language: str) -> Path:
        """Create an unconfigured single-language consumer workspace."""
        workspace = Path(os.environ["TEST_TMPDIR"]) / f"{language}-only"
        workspace.mkdir()
        module = f"""\
module(name = "bazel_devtools_{language}_only")

bazel_dep(name = "bazel_devtools", version = "0.1.0")
local_path_override(
    module_name = "bazel_devtools",
    path = {json.dumps(str(self.scratch_repo))},
)

{_LANGUAGE_MODULE_EXTRAS[language]}"""
        (workspace / "MODULE.bazel").write_text(module, encoding="utf-8")
        shutil.copy2(self.workspace / ".bazelversion", workspace / ".bazelversion")
        shutil.copytree(self.workspace / language, workspace / language)
        if language == "typescript":
            for relative in ("package.json", "pnpm-lock.yaml", "pnpm-workspace.yaml"):
                shutil.copy2(self.workspace / relative, workspace / relative)
            (workspace / "BUILD.bazel").write_text(
                """\
load("@npm//:defs.bzl", "npm_link_all_packages")
load("@aspect_rules_ts//ts:defs.bzl", "ts_config")

npm_link_all_packages(name = "node_modules")

ts_config(
    name = "tsconfig_base",
    src = ".bazel_devtools/tsconfig.json",
)

ts_config(
    name = "tsconfig",
    src = "tsconfig.json",
    deps = [":tsconfig_base"],
    visibility = ["//visibility:public"],
)
""",
                encoding="utf-8",
            )
        return workspace

    def enable_typescript_npm(self, workspace: Path) -> None:
        """Add project-owned npm translation after setup provides rules_js."""
        module = workspace / "MODULE.bazel"
        module.write_text(
            module.read_text(encoding="utf-8")
            + """\

npm = use_extension("@aspect_rules_js//npm:extensions.bzl", "npm")
npm.npm_translate_lock(
    name = "npm",
    pnpm_lock = "//:pnpm-lock.yaml",
)
use_repo(npm, "npm")
""",
            encoding="utf-8",
        )

    def check_first_time_setup(self) -> None:
        """Exercise blocked brownfield adoption and clean greenfield setup."""
        workspace = self.prepare_greenfield()
        language_arguments = ["--language", "python"]
        ruff = workspace / ".ruff.toml"
        legacy_policy = "line-length = 88\n"
        ruff.write_text(legacy_policy, encoding="utf-8")

        self.bazel_run(
            ["run", "@bazel_devtools//tools:setup", "--", "plan", *language_arguments],
            expect_success=False,
            diagnostic="existing .ruff.toml",
            workspace=workspace,
        )
        self.bazel_run(
            ["run", "@bazel_devtools//tools:setup", "--", "init", *language_arguments],
            expect_success=False,
            diagnostic="brownfield adoption",
            workspace=workspace,
        )
        if ruff.read_text(encoding="utf-8") != legacy_policy:
            _fail("blocked setup modified the existing brownfield policy")
        if (workspace / ".bazel_devtools/state.json").exists():
            _fail("blocked setup wrote installation state")

        ruff.unlink()
        output = self.bazel_run(
            ["run", "@bazel_devtools//tools:setup", "--", "plan", *language_arguments],
            expect_success=True,
            diagnostic="would create .bazel_devtools/ruff.toml",
            workspace=workspace,
        )
        if (workspace / ".bazel_devtools/state.json").exists() or (
            workspace / ".ruff.toml"
        ).exists():
            _fail("setup plan modified the greenfield workspace", output)

        self.bazel_run(
            ["run", "@bazel_devtools//tools:setup", "--", "init", *language_arguments],
            expect_success=True,
            workspace=workspace,
        )
        self.bazel_run(
            ["run", "@bazel_devtools//tools:setup", "--", "doctor"],
            expect_success=True,
            workspace=workspace,
        )
        state = _object(
            _json(workspace / ".bazel_devtools/state.json"),
            "greenfield setup state",
        )
        if state.get("languages") != ["python"]:
            _fail("greenfield setup did not persist its Python-only selection")
        unexpected = (
            ".clang-format",
            ".clang-tidy",
            ".bazel_devtools/biome.json",
            "rustfmt.toml",
        )
        if any((workspace / path).exists() for path in unexpected):
            _fail("Python-only setup installed another language's policy")
        aspects = (workspace / "tools/bazel_devtools/aspects.bzl").read_text(encoding="utf-8")
        if any(
            marker in aspects
            for marker in ("checks:cpp.bzl", "checks:rust.bzl", "checks:typescript.bzl")
        ):
            _fail("Python-only setup loads another language's aspects")
        tools_build = (workspace / "tools/bazel_devtools/BUILD.bazel").read_text(encoding="utf-8")
        if any(
            marker in tools_build
            for marker in ("clang_format", "current_rustfmt_toolchain", "biome")
        ):
            _fail("Python-only setup loads another language's formatter")
        if "toolchains_llvm" in (workspace / "MODULE.bazel").read_text(encoding="utf-8"):
            _fail("Python-only setup installed the LLVM toolchain")
        self.bazel_run(["test", "//..."], expect_success=True, workspace=workspace)

        self.check_language_selection_changes(workspace)

    def check_language_selection_changes(self, workspace: Path) -> None:
        """Exercise adding and removing a configured language integration."""
        self.bazel_run(
            [
                "run",
                "@bazel_devtools//tools:setup",
                "--",
                "upgrade",
                "--language",
                "python",
                "--language",
                "cpp",
            ],
            expect_success=True,
            workspace=workspace,
        )
        module = workspace / "MODULE.bazel"
        if "toolchains_llvm" not in module.read_text(encoding="utf-8"):
            _fail("adding C++ support did not install the LLVM toolchain")
        self.bazel_run(
            [
                "run",
                "@bazel_devtools//tools:setup",
                "--",
                "upgrade",
                "--language",
                "python",
            ],
            expect_success=True,
            workspace=workspace,
        )
        if "toolchains_llvm" in module.read_text(encoding="utf-8"):
            _fail("removing C++ support left the LLVM toolchain active")
        self.bazel_run(
            ["run", "@bazel_devtools//tools:setup", "--", "doctor"],
            expect_success=True,
            diagnostic="languages: python",
            workspace=workspace,
        )

    def check_conditional_language_installations(self) -> None:
        """Analyze and exercise each generated non-Python consumer."""
        for language in ("cpp", "rust", "typescript"):
            self.check_conditional_language_installation(language)

    def check_conditional_language_installation(self, language: str) -> None:
        """Exercise one generated single-language consumer."""
        workspace = self.prepare_language_workspace(language)
        self.bazel_run(
            [
                "run",
                "@bazel_devtools//tools:setup",
                "--",
                "init",
                "--language",
                language,
            ],
            expect_success=True,
            workspace=workspace,
        )
        if language == "typescript":
            self.enable_typescript_npm(workspace)
        self.bazel_run(
            ["run", "@bazel_devtools//tools:setup", "--", "doctor"],
            expect_success=True,
            diagnostic=f"languages: {language}",
            workspace=workspace,
        )
        self.check_conditional_language_files(workspace, language)

        self.bazel_run(
            ["build", "//tools/bazel_devtools:formatters"],
            expect_success=True,
            workspace=workspace,
        )
        self.bazel_run(
            ["run", "//:format", "--", "--language", language, "//..."],
            expect_success=True,
            workspace=workspace,
        )
        self.bazel_run(["test", "//..."], expect_success=True, workspace=workspace)

        diagnostic = "language support is not installed for: python"
        self.bazel_run(
            ["run", "//:format", "--", "--language", "python", "//..."],
            expect_success=False,
            diagnostic=diagnostic,
            workspace=workspace,
        )
        self.bazel_run(
            ["run", "//:ide-sync", "--", "--language", "python"],
            expect_success=False,
            diagnostic=diagnostic,
            workspace=workspace,
        )

    def check_conditional_language_files(self, workspace: Path, language: str) -> None:
        """Validate generated files and loads for one selected language."""
        for candidate, paths in _LANGUAGE_POLICY_PATHS.items():
            for relative in paths:
                if (workspace / relative).exists() != (candidate == language):
                    _fail(f"{language}-only setup produced an unexpected policy path: {relative}")

        aspects = (workspace / "tools/bazel_devtools/aspects.bzl").read_text(encoding="utf-8")
        for candidate, marker in _LANGUAGE_ASPECT_MARKERS.items():
            if (marker in aspects) != (candidate == language):
                _fail(f"{language}-only setup produced an unexpected aspect load: {marker}")

        module = (workspace / "MODULE.bazel").read_text(encoding="utf-8")
        if ("toolchains_llvm" in module) != (language == "cpp"):
            _fail(f"{language}-only setup produced unexpected LLVM toolchain configuration")
        if ("rust.toolchain" in module) != (language == "rust"):
            _fail(f"{language}-only setup produced unexpected Rust toolchain configuration")
        if ("aspect_rules_ts" in module) != (language == "typescript"):
            _fail(f"{language}-only setup produced unexpected TypeScript rule configuration")

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
        source = (
            package
            / {
                "cpp": "greeting.cc",
                "python": "greeting.py",
                "rust": "greeting.rs",
                "typescript": "greeting.ts",
            }[language]
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
        source = (
            package
            / {
                "cpp": "greeting.cc",
                "python": "greeting.py",
                "rust": "greeting.rs",
                "typescript": "greeting.ts",
            }[language]
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
            for language in ("python", "cpp", "rust", "typescript")
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

    def check_manual_test_contract(self) -> None:
        """Prove wildcard tests check manual tests without executing them."""
        self.replace_and_reject(
            "python/manual_contract_test.py",
            "e2e/testdata/violations/python/ruff_lint.py",
            "//...",
            "D100",
        )

    def check_cpp_style_policy(self) -> None:
        """Exercise the managed member-naming and pointer-alignment policy."""
        clang_tidy = "//tools/bazel_devtools:clang_tidy"
        config = self.workspace / ".clang-tidy"
        diagnostic_exclusions = [
            line.strip().removesuffix(",")
            for line in config.read_text(encoding="utf-8").splitlines()
            if line.strip().startswith("-clang-diagnostic-")
        ]
        expected_diagnostic_exclusions = ["-clang-diagnostic-builtin-macro-redefined"]
        if diagnostic_exclusions != expected_diagnostic_exclusions:
            _fail(f"clang-diagnostic exclusions broadened unexpectedly: {diagnostic_exclusions}")
        version = self.bazel_run(
            ["run", clang_tidy, "--", "--version"],
            expect_success=True,
        )
        if "LLVM version 22.1.6" not in version:
            _fail("clang-tidy policy inventory ran with an unexpected LLVM version", version)

        listed = self.bazel_run(
            ["run", clang_tidy, "--", "--list-checks", f"--config-file={config}"],
            expect_success=True,
        )
        actual_checks = {
            line.strip()
            for line in listed.splitlines()
            if line.startswith("    ") and "-" in line and " " not in line.strip()
        }
        inventory_path = self.scratch_repo / "e2e/testdata/cpp/clang_tidy_checks_22_1_6.txt"
        expected_checks = set(inventory_path.read_text(encoding="utf-8").splitlines())
        if actual_checks != expected_checks:
            added = sorted(actual_checks - expected_checks)
            removed = sorted(expected_checks - actual_checks)
            difference = f"added: {added}\nremoved: {removed}"
            change = "LLVM 22.1.6 clang-tidy policy inventory changed"
            instruction = "explicitly review and regenerate the snapshot"
            _fail(
                f"{change}; {instruction}\n{difference}",
                listed,
            )
        actual_count = len(actual_checks)
        if actual_count != _CLANG_TIDY_CHECK_COUNT:
            expected_count = _CLANG_TIDY_CHECK_COUNT
            _fail(f"expected {expected_count} resolved clang-tidy checks; found {actual_count}")

        missing_required = sorted(_REQUIRED_CLANG_TIDY_CHECKS - actual_checks)
        if missing_required:
            _fail(f"strict clang-tidy checks are unexpectedly disabled: {missing_required}")
        enabled_exclusions = sorted(_EXCLUDED_CLANG_TIDY_CHECKS & actual_checks)
        enabled_exclusions.extend(
            sorted(
                check for check in actual_checks if check.startswith(_EXCLUDED_CLANG_TIDY_PREFIXES)
            )
        )
        if enabled_exclusions:
            _fail(f"excluded clang-tidy checks are unexpectedly enabled: {enabled_exclusions}")

        check_arguments = [
            "--checks=-*,readability-identifier-naming",
            f"--config-file={config}",
            "--",
            "-std=c++20",
        ]
        bad_member = self.scratch_repo / "e2e/testdata/violations/cpp/member_naming.cc"
        self.bazel_run(
            ["run", clang_tidy, "--", str(bad_member), *check_arguments],
            expect_success=False,
            diagnostic="invalid case style for private member 'frame_count'",
        )

        good_members = self.scratch_repo / "e2e/testdata/cpp/member_naming_good.cc"
        self.bazel_run(
            ["run", clang_tidy, "--", str(good_members), *check_arguments],
            expect_success=True,
        )

        included = self.scratch_repo / "e2e/testdata/violations/cpp/easily_swappable.cc"
        self.bazel_run(
            [
                "run",
                clang_tidy,
                "--",
                str(included),
                f"--config-file={config}",
                "--",
                "-std=c++20",
            ],
            expect_success=False,
            diagnostic="bugprone-easily-swappable-parameters",
        )

        excluded = self.scratch_repo / "e2e/testdata/cpp/excluded_policy_good.cc"
        self.bazel_run(
            [
                "run",
                clang_tidy,
                "--",
                str(excluded),
                f"--config-file={config}",
                "--",
                "-std=c++20",
            ],
            expect_success=True,
        )

        pointer_fixture = self.scratch_repo / "e2e/testdata/cpp/pointer_format.cc"
        formatted = self.bazel_run(
            [
                "run",
                "//tools/bazel_devtools:clang_format",
                "--",
                f"--style=file:{self.workspace / '.clang-format'}",
                str(pointer_fixture),
            ],
            expect_success=True,
        )
        expected = "void Consume(Type *value, const Type &reference);"
        if expected not in formatted:
            _fail("managed clang-format policy did not use right pointer alignment", formatted)

    def check_format_is_scratch_only(self) -> None:
        cases = {
            "python/greeting.py": "e2e/testdata/violations/python/format.py",
            "cpp/greeting.cc": "e2e/testdata/violations/cpp/format.cc",
            "rust/greeting.rs": "e2e/testdata/violations/rust/format.rs",
            "typescript/greeting.ts": "e2e/testdata/violations/typescript/format.ts",
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
            "python/manual_contract_test.py",
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
        tsconfig = _object(_json(self.workspace / "tsconfig.json"), "tsconfig.json")
        if tsconfig.get("extends") != "./.bazel_devtools/tsconfig.json":
            _fail("tsconfig.json does not extend the managed TypeScript baseline")

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
        if "branches:" in workflow.read_text(encoding="utf-8"):
            _fail("generated GitHub workflow is unexpectedly limited to a named branch")
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
        self.check_conditional_language_installations()
        self.bazel_run(
            ["run", "@bazel_devtools//tools:setup", "--", "init"],
            expect_success=True,
        )
        self.bazel_run(
            ["run", "@bazel_devtools//tools:setup", "--", "doctor"],
            expect_success=True,
        )
        self.bazel_run(["test", "//..."], expect_success=True)
        self.check_manual_test_contract()
        self.check_cpp_style_policy()
        self.replace_and_reject(
            "cpp_transition/configured.c",
            "e2e/testdata/violations/cpp/implicit_bool_conversion.c",
            "//cpp_transition:configured_entry",
            "readability-implicit-bool-conversion",
        )

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
                "modernize-use-nullptr",
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
            (
                "typescript/greeting.ts",
                "e2e/testdata/violations/typescript/format.ts",
                "//typescript:greeting_typecheck_test",
                "format",
            ),
            (
                "typescript/greeting.ts",
                "e2e/testdata/violations/typescript/biome_lint.ts",
                "//typescript:greeting_typecheck_test",
                "Unexpected any",
            ),
            (
                "typescript/greeting.ts",
                "e2e/testdata/violations/typescript/type_error.ts",
                "//typescript:greeting_typecheck_test",
                "not assignable to type 'string'",
            ),
        )
        for source, fixture, target, diagnostic in failures:
            self.replace_and_reject(source, fixture, target, diagnostic)

        self.check_opt_out("python", "e2e/testdata/violations/python/format.py")
        self.check_opt_out("cpp", "e2e/testdata/violations/cpp/format.cc")
        self.check_opt_out("rust", "e2e/testdata/violations/rust/format.rs")
        self.check_opt_out("typescript", "e2e/testdata/violations/typescript/format.ts")
        self.check_opt_out("python", "e2e/testdata/violations/python/ruff_lint.py", "no-lint")
        self.check_opt_out(
            "python",
            "e2e/testdata/violations/python/type_error_runtime_safe.py",
            "no-typecheck",
        )
        self.check_opt_out("cpp", "e2e/testdata/violations/cpp/clang_tidy.cc", "no-lint")
        self.check_opt_out("rust", "e2e/testdata/violations/rust/clippy.rs", "no-clippy")
        self.check_opt_out(
            "typescript",
            "e2e/testdata/violations/typescript/biome_lint.ts",
            "no-lint",
        )
        self.check_opt_out(
            "typescript",
            "e2e/testdata/violations/typescript/biome_lint.ts",
            "no-biome-lint",
        )
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
        self.check_write_format_opt_out(
            "typescript",
            "e2e/testdata/violations/typescript/format.ts",
            "no-biome-format",
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
