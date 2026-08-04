"""Public Python check factories without loading other language integrations."""

load(
    "@aspect_rules_lint//lint:ruff.bzl",
    _lint_ruff_aspect = "lint_ruff_aspect",
)
load("//checks:basedpyright.bzl", _basedpyright_aspect = "basedpyright_aspect")
load("//checks:format.bzl", _ruff_format_aspect = "ruff_format_aspect")
load("//checks:ruff.bzl", _ruff_lint_aspect = "ruff_lint_aspect")

basedpyright_aspect = _basedpyright_aspect
lint_ruff_aspect = _lint_ruff_aspect
ruff_format_aspect = _ruff_format_aspect
ruff_lint_aspect = _ruff_lint_aspect
