"""Public factories for bazel_devtools target-graph checks."""

load(
    "@aspect_rules_lint//lint:clang_tidy.bzl",
    _lint_clang_tidy_aspect = "lint_clang_tidy_aspect",
)
load(
    "@rules_rust//rust:defs.bzl",
    _rust_clippy_aspect = "rust_clippy_aspect",
    _rustfmt_aspect = "rustfmt_aspect",
)
load(
    "@aspect_rules_lint//lint:ruff.bzl",
    _lint_ruff_aspect = "lint_ruff_aspect",
)
load("//checks:basedpyright.bzl", _basedpyright_aspect = "basedpyright_aspect")
load(
    "//checks:format.bzl",
    _clang_format_aspect = "clang_format_aspect",
    _ruff_format_aspect = "ruff_format_aspect",
)
load("//checks:ruff.bzl", _ruff_lint_aspect = "ruff_lint_aspect")

basedpyright_aspect = _basedpyright_aspect
clang_format_aspect = _clang_format_aspect
lint_clang_tidy_aspect = _lint_clang_tidy_aspect
lint_ruff_aspect = _lint_ruff_aspect
ruff_format_aspect = _ruff_format_aspect
ruff_lint_aspect = _ruff_lint_aspect
rust_clippy_aspect = _rust_clippy_aspect
rustfmt_aspect = _rustfmt_aspect
