"""Installable bazel_devtools policy and integration templates."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

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


MODULE_BLOCK = """\
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
    llvm_version = "20.1.8",
)
use_repo(
    bazel_devtools_llvm,
    "bazel_devtools_llvm_toolchain",
    "bazel_devtools_llvm_toolchain_llvm",
)
"""


CLANG_FORMAT_POLICY = """\
BasedOnStyle: LLVM
IndentWidth: 4
ContinuationIndentWidth: 4
ColumnLimit: 100
"""


CLANG_TIDY_POLICY = """\
# Start from every check, then exclude platform/runtime policies that do not
# describe ordinary portable C++ and diagnostics that depend on sandbox paths.
Checks: >-
  *,
  -fuchsia-*,
  -llvmlibc-*,
  -zircon-*,
  -llvm-header-guard,
  -clang-diagnostic-builtin-macro-redefined
WarningsAsErrors: '*'
HeaderFilterRegex: '.*'
"""


RUSTFMT_POLICY = """\
max_width = 100
newline_style = "Unix"
"""


BAZELRC_IMPORT_BLOCK = """\
try-import %workspace%/.bazelrc.bazel_devtools
"""


CLIPPY_STRICT_FLAGS = "-Dwarnings,-Dclippy::all,-Dclippy::pedantic,-Dclippy::nursery"


BAZELRC_DEVTOOLS_BLOCK = f"""\
# Do not synthesize empty __init__.py files in Python runfiles trees.
common --incompatible_default_to_explicit_init_py

# Apply checks to every target requested by `bazel test`.
test --aspects=//tools/bazel_devtools:aspects.bzl%ruff
test --aspects=//tools/bazel_devtools:aspects.bzl%basedpyright
test --aspects=//tools/bazel_devtools:aspects.bzl%ruff_format
test --aspects=//tools/bazel_devtools:aspects.bzl%clang_tidy
test --aspects=//tools/bazel_devtools:aspects.bzl%clang_format
test --aspects=//tools/bazel_devtools:aspects.bzl%rustfmt
test --aspects=//tools/bazel_devtools:aspects.bzl%clippy
test --@@aspect_rules_lint+//lint:fail_on_violation
test --@@rules_rust+//rust/settings:rustfmt.toml=//:rustfmt.toml
test --@@rules_rust+//rust/settings:clippy_flags={CLIPPY_STRICT_FLAGS}
test --output_groups=+rustfmt_checks,+clippy_checks
"""


ASPECTS_BZL = """\
load(
    "@bazel_devtools//checks:defs.bzl",
    "basedpyright_aspect",
    "clang_format_aspect",
    "lint_clang_tidy_aspect",
    "lint_ruff_aspect",
    "ruff_format_aspect",
    "rust_clippy_aspect",
    "rustfmt_aspect",
)

ruff = lint_ruff_aspect(
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

clang_tidy = lint_clang_tidy_aspect(
    binary = Label("//tools/bazel_devtools:clang_tidy"),
    global_config = [Label("//:.clang-tidy")],
    lint_target_headers = True,
)

clang_format = clang_format_aspect(
    binary = Label("//tools/bazel_devtools:clang_format"),
    config = Label("//:.clang-format"),
)

rustfmt = rustfmt_aspect
clippy = rust_clippy_aspect
"""


TOOLS_BUILD = """\
load("@bazel_devtools//tools:defs.bzl", "bazel_devtools_formatters", "tool_binary")

package(default_visibility = ["//visibility:public"])

tool_binary(
    name = "clang_format",
    src = "@bazel_devtools_llvm_toolchain_llvm//:bin/clang-format",
)

tool_binary(
    name = "clang_tidy",
    src = "@bazel_devtools_llvm_toolchain_llvm//:bin/clang-tidy",
)

bazel_devtools_formatters(
    name = "formatters",
    clang_format = ":clang_format",
)
"""


ROOT_BUILD_BLOCK = """\
exports_files([
    ".bazel_devtools/basedpyright.json",
    ".bazel_devtools/ruff.toml",
    ".github/workflows/bazel-devtools.yml",
    ".pre-commit-config.yaml",
    ".clang-format",
    ".clang-tidy",
    ".ruff.toml",
    "basedpyright.json",
    "rustfmt.toml",
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


GITIGNORE_BLOCK = """\
/compile_commands.json
/pyrightconfig.json
/rust-project.json
/.cache/
/.ruff_cache/
/external
/.bazel_devtools/updates/
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
    branches: [master]

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


TEMPLATES = (
    Template(".bazel_devtools/ruff.toml", RUFF_POLICY, Ownership.MANAGED_FILE),
    Template(
        ".bazel_devtools/basedpyright.json",
        BASEDPYRIGHT_POLICY,
        Ownership.MANAGED_FILE,
    ),
    Template(".ruff.toml", RUFF_USER_CONFIG, Ownership.CREATE_ONLY),
    Template("basedpyright.json", BASEDPYRIGHT_USER_CONFIG, Ownership.CREATE_ONLY),
    Template("pyrightconfig.json", PYRIGHT_EDITOR_CONFIG, Ownership.CREATE_ONLY),
    Template(
        ".clang-format",
        CLANG_FORMAT_POLICY,
        Ownership.MANAGED_BLOCK,
        "clang-format-policy",
    ),
    Template(".clang-tidy", CLANG_TIDY_POLICY, Ownership.MANAGED_BLOCK, "clang-tidy-policy"),
    Template("rustfmt.toml", RUSTFMT_POLICY, Ownership.MANAGED_BLOCK, "rustfmt-policy"),
    Template("MODULE.bazel", MODULE_BLOCK, Ownership.MANAGED_BLOCK, "ide-dependencies"),
    Template(".bazelrc", BAZELRC_IMPORT_BLOCK, Ownership.MANAGED_BLOCK, "bazelrc-import"),
    Template(".gitignore", GITIGNORE_BLOCK, Ownership.MANAGED_BLOCK, "generated-ide-files"),
    Template(
        ".bazelrc.bazel_devtools",
        BAZELRC_DEVTOOLS_BLOCK,
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
        ASPECTS_BZL,
        Ownership.MANAGED_BLOCK,
        "aspects",
    ),
    Template(
        "tools/bazel_devtools/BUILD.bazel",
        TOOLS_BUILD,
        Ownership.MANAGED_BLOCK,
        "tools",
    ),
    Template("BUILD.bazel", ROOT_BUILD_BLOCK, Ownership.MANAGED_BLOCK, "root-aliases"),
)
