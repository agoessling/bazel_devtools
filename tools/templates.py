"""Installable bazel_devtools policy and integration templates."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from tools.languages import SUPPORTED_LANGUAGES, normalize_languages

if TYPE_CHECKING:
    from collections.abc import Iterable

BAZEL_DEVTOOLS_VERSION = "0.1.0"


class Ownership(str, Enum):
    """Upgrade behavior for an installed template."""

    MANAGED_FILE = "managed_file"
    MANAGED_BLOCK = "managed_block"
    CREATE_ONLY = "create_only"


@dataclass(frozen=True)
class Template:
    """One file or managed block installed into a consuming repository."""

    path: str
    content: str
    ownership: Ownership
    block_id: str | None = None


RUFF_POLICY = """\
line-length = 100

[lint]
select = ["ALL"]
ignore = [
    # These rules conflict with Ruff's formatter.
    "COM812",
    "ISC001",
    # A repository-level license is sufficient; per-file notices add churn.
    "CPY001",
    # Bazel package boundaries do not imply Python package boundaries.
    "INP001",
    # Assertions and unittest assertion helpers are valid project policy.
    "PT009",
    "PT027",
    "S101",
    # These security audits are low-signal for Bazel-owned tool invocations
    # and Bazel-generated XML.
    "S314",
    "S603",
    "S607",
    # CLI tools intentionally use print as their user interface.
    "T201",
]

[lint.pydocstyle]
convention = "google"

[format]
docstring-code-format = true
line-ending = "lf"
"""


BASEDPYRIGHT_POLICY = """\
{
  "typeCheckingMode": "all",
  "reportUnusedCallResult": "none",
  "exclude": [
    "**/__pycache__",
    "**/.cache",
    "**/.git",
    "**/.ruff_cache",
    "**/bazel-*",
    "**/external"
  ]
}
"""


_CPP_MODULE_BLOCK = """\
bazel_dep(name = "toolchains_llvm", version = "1.8.0", dev_dependency = True)
bazel_dep(name = "hedron_compile_commands", dev_dependency = True)
git_override(
    module_name = "hedron_compile_commands",
    commit = "abb61a688167623088f8768cc9264798df6a9d10",
    remote = "https://github.com/hedronvision/bazel-compile-commands-extractor.git",
)

bazel_devtools_llvm = use_extension(
    "@toolchains_llvm//toolchain/extensions:llvm.bzl",
    "llvm",
    dev_dependency = True,
)
bazel_devtools_llvm.toolchain(
    name = "bazel_devtools_llvm_toolchain",
    llvm_version = "22.1.6",
)
use_repo(
    bazel_devtools_llvm,
    "bazel_devtools_llvm_toolchain",
    "bazel_devtools_llvm_toolchain_llvm",
)
"""


_TYPESCRIPT_MODULE_BLOCK = """\
bazel_dep(name = "aspect_rules_js", version = "3.4.0")
bazel_dep(name = "aspect_rules_ts", version = "3.10.0")

bazel_devtools_rules_ts = use_extension(
    "@aspect_rules_ts//ts:extensions.bzl",
    "typescript",
)
bazel_devtools_rules_ts.deps(version = "5.9.3")
use_repo(bazel_devtools_rules_ts, "npm_typescript")
"""


def _module_block(languages: tuple[str, ...]) -> str:
    parts: list[str] = []
    if "cpp" in languages:
        parts.append(_CPP_MODULE_BLOCK.rstrip())
    if "typescript" in languages:
        parts.append(_TYPESCRIPT_MODULE_BLOCK.rstrip())
    return "\n\n".join(parts) + ("\n" if parts else "")


CLANG_FORMAT_POLICY = """\
BasedOnStyle: Google
ColumnLimit: 100
DerivePointerAlignment: false
PointerAlignment: Right
"""


CLANG_TIDY_POLICY = """\
# Begin with no checks, enable the reviewed general-purpose families, then
# remove their documented platform, API-design, and high-noise diagnostics.
# clang-diagnostic-* surfaces only diagnostics enabled by the compile flags.
# Bazel's host C++ toolchain intentionally redefines __DATE__, __TIME__, and
# __TIMESTAMP__ to deterministic values, so that one non-source diagnostic is
# excluded without suppressing any other compiler warning.
# Analyzer exclusions remove unsupported platform/domain checks and ABI-padding
# policy. C++/Google/misc exclusions remove subjective architecture, field,
# function-size, TODO, recursion, and magic-number policy. Unchecked-container
# access is excluded because LLVM 22 flags ordinary indexed access even when
# size invariants are established, while C++20 span has no at() alternative.
# Modernize/readability exclusions avoid API or expression-style rewrites. In particular,
# readability-math-missing-parentheses requires redundant parentheses around
# conventional mathematical precedence, making expressions noisier without
# identifying a defect. Performance/portability exclusions avoid enum-layout
# and system-header deployment policy.
# Paired aliases are excluded under every selected family that registers them.
Checks: >-
  -*,
  clang-diagnostic-*,
  clang-analyzer-*,
  bugprone-*,
  cert-*,
  concurrency-*,
  cppcoreguidelines-*,
  google-*,
  misc-*,
  modernize-*,
  performance-*,
  portability-*,
  readability-*,

  -clang-diagnostic-builtin-macro-redefined,

  -clang-analyzer-fuchsia.*,
  -clang-analyzer-optin.mpi.*,
  -clang-analyzer-optin.osx.*,
  -clang-analyzer-optin.performance.GCDAntipattern,
  -clang-analyzer-optin.performance.Padding,
  -clang-analyzer-osx.*,
  -clang-analyzer-webkit.*,

  -cppcoreguidelines-avoid-do-while,
  -cppcoreguidelines-avoid-magic-numbers,
  -cppcoreguidelines-macro-to-enum,
  -cppcoreguidelines-non-private-member-variables-in-classes,
  -cppcoreguidelines-owning-memory,
  -cppcoreguidelines-pro-bounds-avoid-unchecked-container-access,
  -cppcoreguidelines-pro-bounds-constant-array-index,

  -google-objc-*,
  -google-readability-function-size,
  -google-readability-todo,

  -misc-no-recursion,
  -misc-non-private-member-variables-in-classes,

  -modernize-macro-to-enum,
  -modernize-min-max-use-initializer-list,
  -modernize-pass-by-value,
  -modernize-raw-string-literal,
  -modernize-return-braced-init-list,
  -modernize-use-constraints,
  -modernize-use-trailing-return-type,

  -performance-enum-size,
  -portability-restrict-system-includes,

  -readability-convert-member-functions-to-static,
  -readability-function-size,
  -readability-identifier-length,
  -readability-magic-numbers,
  -readability-math-missing-parentheses
WarningsAsErrors: '*'
HeaderFilterRegex: '.*'
CheckOptions:
  # LLVM classifies static const/constexpr members as ClassConstant, so
  # these access-specific categories enforce state suffixes without changing
  # valid Google constants such as `static constexpr int kFrameRate`.
  readability-identifier-naming.PrivateMemberCase: lower_case
  readability-identifier-naming.PrivateMemberSuffix: '_'
  readability-identifier-naming.ProtectedMemberCase: lower_case
  readability-identifier-naming.ProtectedMemberSuffix: '_'
  readability-identifier-naming.PublicMemberCase: lower_case
"""


RUSTFMT_POLICY = """\
max_width = 100
newline_style = "Unix"
"""


BIOME_POLICY = """\
{
  "$schema": "https://biomejs.dev/schemas/2.5.6/schema.json",
  "files": {
    "includes": ["**", "!**/bazel-*", "!**/node_modules"]
  },
  "formatter": {
    "enabled": true,
    "formatWithErrors": false,
    "indentStyle": "space",
    "lineEnding": "lf",
    "lineWidth": 100
  },
  "linter": {
    "enabled": true,
    "rules": {
      "recommended": true
    }
  },
  "javascript": {
    "formatter": {
      "jsxQuoteStyle": "double",
      "quoteStyle": "double",
      "semicolons": "always"
    }
  }
}
"""


TSCONFIG_POLICY = """\
{
  "compilerOptions": {
    "allowJs": false,
    "esModuleInterop": true,
    "exactOptionalPropertyTypes": true,
    "forceConsistentCasingInFileNames": true,
    "isolatedModules": true,
    "jsx": "react-jsx",
    "lib": ["DOM", "DOM.Iterable", "ES2023"],
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "noEmit": true,
    "noFallthroughCasesInSwitch": true,
    "noImplicitOverride": true,
    "noUncheckedIndexedAccess": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "strict": true,
    "target": "ES2022",
    "verbatimModuleSyntax": true
  }
}
"""


BIOME_USER_CONFIG = """\
{
  "extends": ["./.bazel_devtools/biome.json"]
}
"""


TSCONFIG_USER_CONFIG = """\
{
  "extends": "./.bazel_devtools/tsconfig.json"
}
"""


BAZELRC_IMPORT_BLOCK = """\
try-import %workspace%/.bazelrc.bazel_devtools
"""


CLIPPY_STRICT_FLAGS = "-Dwarnings,-Dclippy::all,-Dclippy::pedantic,-Dclippy::nursery"


def _bazelrc_devtools_block(languages: tuple[str, ...]) -> str:
    lines = [
        "# Do not synthesize empty __init__.py files in Python runfiles trees.",
        "common --incompatible_default_to_explicit_init_py",
        "",
        "# Compile and check manual tests selected by wildcard target patterns, but do",
        "# not execute them. Manual non-test targets retain Bazel's normal exclusion.",
        "build --build_manual_tests",
        "",
        "# Apply checks to every target requested by `bazel test`.",
    ]
    aspects = {
        "python": ("ruff", "basedpyright", "ruff_format"),
        "cpp": ("clang_tidy", "clang_format"),
        "rust": ("rustfmt", "clippy"),
        "typescript": ("biome_lint", "biome_format"),
    }
    for language in languages:
        lines.extend(
            f"test --aspects=//tools/bazel_devtools:aspects.bzl%{aspect}"
            for aspect in aspects[language]
        )
    if "python" in languages or "cpp" in languages or "typescript" in languages:
        lines.append("test --@@aspect_rules_lint+//lint:fail_on_violation")
    if "rust" in languages:
        lines.extend(
            (
                "test --@@rules_rust+//rust/settings:rustfmt.toml=//:rustfmt.toml",
                f"test --@@rules_rust+//rust/settings:clippy_flags={CLIPPY_STRICT_FLAGS}",
                "test --output_groups=+rustfmt_checks,+clippy_checks",
            )
        )
    return "\n".join(lines) + "\n"


_PYTHON_ASPECTS = """\
load(
    "@bazel_devtools//checks:python.bzl",
    "basedpyright_aspect",
    "ruff_format_aspect",
    "ruff_lint_aspect",
)

ruff = ruff_lint_aspect(
    binary = Label("@bazel_devtools//tools:ruff"),
    configs = [
        Label("//:.ruff.toml"),
        Label("//:.bazel_devtools/ruff.toml"),
    ],
)

basedpyright = basedpyright_aspect(
    binary = Label("@bazel_devtools//tools:basedpyright"),
    config = Label("//:basedpyright.json"),
    configs = [Label("//:.bazel_devtools/basedpyright.json")],
)

ruff_format = ruff_format_aspect(
    binary = Label("@bazel_devtools//tools:ruff"),
    configs = [
        Label("//:.ruff.toml"),
        Label("//:.bazel_devtools/ruff.toml"),
    ],
)
"""


_CPP_ASPECTS = """\
load(
    "@bazel_devtools//checks:cpp.bzl",
    "clang_format_aspect",
    "lint_clang_tidy_aspect",
)

clang_tidy = lint_clang_tidy_aspect(
    binary = Label("//tools/bazel_devtools:clang_tidy"),
    global_config = [Label("//:.clang-tidy")],
    lint_target_headers = True,
)

clang_format = clang_format_aspect(
    binary = Label("//tools/bazel_devtools:clang_format"),
    config = Label("//:.clang-format"),
)
"""


_RUST_ASPECTS = """\
load(
    "@bazel_devtools//checks:rust.bzl",
    "rust_clippy_aspect",
    "rustfmt_aspect",
)

rustfmt = rustfmt_aspect
clippy = rust_clippy_aspect
"""


_TYPESCRIPT_ASPECTS = """\
load(
    "@bazel_devtools//checks:typescript.bzl",
    "biome_format_aspect",
    "biome_lint_aspect",
)

biome_lint = biome_lint_aspect(
    binary = Label("@bazel_devtools//tools:biome"),
    config = Label("//:biome.json"),
    configs = [Label("//:.bazel_devtools/biome.json")],
)

biome_format = biome_format_aspect(
    binary = Label("@bazel_devtools//tools:biome"),
    config = Label("//:biome.json"),
    configs = [Label("//:.bazel_devtools/biome.json")],
)
"""


def _aspects_bzl(languages: tuple[str, ...]) -> str:
    content = {
        "python": _PYTHON_ASPECTS,
        "cpp": _CPP_ASPECTS,
        "rust": _RUST_ASPECTS,
        "typescript": _TYPESCRIPT_ASPECTS,
    }
    loads: list[str] = []
    definitions: list[str] = []
    for language in languages:
        load, separator, definition = content[language].partition("\n\n")
        if not separator:
            msg = f"language aspect template for {language} has no load separator"
            raise ValueError(msg)
        loads.append(load)
        definitions.append(definition.rstrip())
    return "\n\n".join((*loads, *definitions)) + "\n"


def _tools_build(languages: tuple[str, ...]) -> str:
    parts = [
        'load("@bazel_devtools//tools:defs.bzl", "bazel_devtools_formatters", "tool_binary")',
        'package(default_visibility = ["//visibility:public"])',
    ]
    if "cpp" in languages:
        parts.append(
            """\
tool_binary(
    name = "clang_format",
    src = "@bazel_devtools_llvm_toolchain_llvm//:bin/clang-format",
)

tool_binary(
    name = "clang_tidy",
    src = "@bazel_devtools_llvm_toolchain_llvm//:bin/clang-tidy",
)"""
        )
    if "typescript" in languages:
        parts.append(
            """\
alias(
    name = "biome",
    actual = "@bazel_devtools//tools:biome",
)

alias(
    name = "biome_cwd",
    actual = "@bazel_devtools//tools:biome_cwd",
)"""
        )
    language_lines = "\n".join(f'        "{language}",' for language in languages)
    arguments = f"    languages = [\n{language_lines}\n    ],"
    if "cpp" in languages:
        arguments += '\n    clang_format = ":clang_format",'
    parts.append(
        f"""\
bazel_devtools_formatters(
    name = "formatters",
{arguments}
)"""
    )
    return "\n\n".join(parts) + "\n"


def _root_build_block(languages: tuple[str, ...]) -> str:
    exported = [
        ".github/workflows/bazel-devtools.yml",
        ".pre-commit-config.yaml",
    ]
    if "python" in languages:
        exported.extend(
            (
                ".bazel_devtools/basedpyright.json",
                ".bazel_devtools/ruff.toml",
                ".ruff.toml",
                "basedpyright.json",
            )
        )
    if "cpp" in languages:
        exported.extend((".clang-format", ".clang-tidy"))
    if "rust" in languages:
        exported.append("rustfmt.toml")
    if "typescript" in languages:
        exported.extend(
            (
                ".bazel_devtools/biome.json",
                ".bazel_devtools/tsconfig.json",
                "biome.json",
                "tsconfig.json",
            )
        )
    export_lines = "\n".join(f'    "{path}",' for path in sorted(exported))
    return f"""\
exports_files([
{export_lines}
])

alias(
    name = "format",
    actual = "@bazel_devtools//tools:format",
)

alias(
    name = "ide-sync",
    actual = "@bazel_devtools//tools:ide_sync",
)

alias(
    name = "install-hooks",
    actual = "@bazel_devtools//tools:install-hooks",
)

alias(
    name = "pre-commit",
    actual = "@bazel_devtools//tools:pre-commit",
)
"""


RUFF_USER_CONFIG = """\
# Repository-specific Ruff overrides belong in this file.
extend = ".bazel_devtools/ruff.toml"
"""


BASEDPYRIGHT_USER_CONFIG = """\
{
  "extends": ".bazel_devtools/basedpyright.json"
}
"""


PYRIGHT_EDITOR_CONFIG = """\
{
  "extends": "basedpyright.json",
  "extraPaths": []
}
"""


_GITIGNORE_BLOCK = """\
/compile_commands.json
/pyrightconfig.json
/rust-project.json
/.cache/
/.ruff_cache/
/external
/.bazel_devtools/updates/
"""


def _gitignore_block(languages: tuple[str, ...]) -> str:
    content = _GITIGNORE_BLOCK
    if "typescript" in languages:
        content += "/node_modules/\n"
    return content


REPO_BAZEL_TYPESCRIPT_BLOCK = """\
ignore_directories(["**/node_modules"])
"""


PRE_COMMIT_CONFIG = """\
minimum_pre_commit_version: "4.6.0"
repos:
  - repo: local
    hooks:
      - id: bazel-devtools-check
        name: bazel_devtools checks
        language: system
        entry: bazel
        args:
          - test
          - //...
          - --test_output=errors
        pass_filenames: false
        always_run: true
        require_serial: true
        stages: [pre-commit]
"""


GITHUB_WORKFLOW = """\
name: Bazel presubmit

on:
  pull_request:
  push:

permissions:
  contents: read

concurrency:
  group: bazel-presubmit-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: true

jobs:
  test:
    name: Bazel test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2
        with:
          persist-credentials: false
      - uses: bazel-contrib/setup-bazel@c5acdfb288317d0b5c0bbd7a396a3dc868bb0f86 # v0.19.0
        with:
          bazelisk-cache: true
          disk-cache: bazel-presubmit
          repository-cache: true
          cache-save: ${{ github.event_name != 'pull_request' }}
      - name: Test and check Bazel targets
        run: bazel test //... --test_output=errors
"""


def templates_for_languages(languages: Iterable[str]) -> tuple[Template, ...]:
    """Build the installable template set for the selected languages."""
    selected = normalize_languages(languages)
    templates: list[Template] = []
    if "python" in selected:
        templates.extend(
            (
                Template(".bazel_devtools/ruff.toml", RUFF_POLICY, Ownership.MANAGED_FILE),
                Template(
                    ".bazel_devtools/basedpyright.json",
                    BASEDPYRIGHT_POLICY,
                    Ownership.MANAGED_FILE,
                ),
                Template(".ruff.toml", RUFF_USER_CONFIG, Ownership.CREATE_ONLY),
                Template("basedpyright.json", BASEDPYRIGHT_USER_CONFIG, Ownership.CREATE_ONLY),
                Template("pyrightconfig.json", PYRIGHT_EDITOR_CONFIG, Ownership.CREATE_ONLY),
            )
        )
    if "cpp" in selected:
        templates.extend(
            (
                Template(
                    ".clang-format",
                    CLANG_FORMAT_POLICY,
                    Ownership.MANAGED_BLOCK,
                    "clang-format-policy",
                ),
                Template(
                    ".clang-tidy",
                    CLANG_TIDY_POLICY,
                    Ownership.MANAGED_BLOCK,
                    "clang-tidy-policy",
                ),
            )
        )
    if "rust" in selected:
        templates.append(
            Template(
                "rustfmt.toml",
                RUSTFMT_POLICY,
                Ownership.MANAGED_BLOCK,
                "rustfmt-policy",
            )
        )
    if "typescript" in selected:
        templates.extend(
            (
                Template(
                    ".bazel_devtools/biome.json",
                    BIOME_POLICY,
                    Ownership.MANAGED_FILE,
                ),
                Template(
                    ".bazel_devtools/tsconfig.json",
                    TSCONFIG_POLICY,
                    Ownership.MANAGED_FILE,
                ),
                Template("biome.json", BIOME_USER_CONFIG, Ownership.CREATE_ONLY),
                Template("tsconfig.json", TSCONFIG_USER_CONFIG, Ownership.CREATE_ONLY),
            )
        )
    templates.extend(
        (
            Template(
                "MODULE.bazel",
                _module_block(selected),
                Ownership.MANAGED_BLOCK,
                "ide-dependencies",
            ),
            Template(
                "REPO.bazel",
                REPO_BAZEL_TYPESCRIPT_BLOCK if "typescript" in selected else "",
                Ownership.MANAGED_BLOCK,
                "typescript-node-modules",
            ),
            Template(".bazelrc", BAZELRC_IMPORT_BLOCK, Ownership.MANAGED_BLOCK, "bazelrc-import"),
            Template(
                ".gitignore",
                _gitignore_block(selected),
                Ownership.MANAGED_BLOCK,
                "generated-ide-files",
            ),
            Template(
                ".bazelrc.bazel_devtools",
                _bazelrc_devtools_block(selected),
                Ownership.MANAGED_BLOCK,
                "checks",
            ),
            Template(".pre-commit-config.yaml", PRE_COMMIT_CONFIG, Ownership.MANAGED_FILE),
            Template(
                ".github/workflows/bazel-devtools.yml",
                GITHUB_WORKFLOW,
                Ownership.MANAGED_FILE,
            ),
            Template(
                "tools/bazel_devtools/aspects.bzl",
                _aspects_bzl(selected),
                Ownership.MANAGED_BLOCK,
                "aspects",
            ),
            Template(
                "tools/bazel_devtools/BUILD.bazel",
                _tools_build(selected),
                Ownership.MANAGED_BLOCK,
                "tools",
            ),
            Template(
                "BUILD.bazel",
                _root_build_block(selected),
                Ownership.MANAGED_BLOCK,
                "root-aliases",
            ),
        )
    )
    return tuple(templates)


BAZELRC_DEVTOOLS_BLOCK = _bazelrc_devtools_block(SUPPORTED_LANGUAGES)
ASPECTS_BZL = _aspects_bzl(SUPPORTED_LANGUAGES)
TOOLS_BUILD = _tools_build(SUPPORTED_LANGUAGES)
ROOT_BUILD_BLOCK = _root_build_block(SUPPORTED_LANGUAGES)
TEMPLATES = templates_for_languages(SUPPORTED_LANGUAGES)
