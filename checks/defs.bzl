"""Public factories for bazel_devtools target-graph checks."""

load(
    "//checks:typescript.bzl",
    _biome_format_aspect = "biome_format_aspect",
    _biome_lint_aspect = "biome_lint_aspect",
)
load(
    "//checks:cpp.bzl",
    _clang_format_aspect = "clang_format_aspect",
    _lint_clang_tidy_aspect = "lint_clang_tidy_aspect",
)
load(
    "//checks:python.bzl",
    _basedpyright_aspect = "basedpyright_aspect",
    _lint_ruff_aspect = "lint_ruff_aspect",
    _ruff_format_aspect = "ruff_format_aspect",
    _ruff_lint_aspect = "ruff_lint_aspect",
)
load(
    "//checks:rust.bzl",
    _rust_clippy_aspect = "rust_clippy_aspect",
    _rustfmt_aspect = "rustfmt_aspect",
)

basedpyright_aspect = _basedpyright_aspect
clang_format_aspect = _clang_format_aspect
lint_clang_tidy_aspect = _lint_clang_tidy_aspect
lint_ruff_aspect = _lint_ruff_aspect
ruff_format_aspect = _ruff_format_aspect
ruff_lint_aspect = _ruff_lint_aspect
rust_clippy_aspect = _rust_clippy_aspect
rustfmt_aspect = _rustfmt_aspect
biome_format_aspect = _biome_format_aspect
biome_lint_aspect = _biome_lint_aspect
