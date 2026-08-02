"""Self-hosted Python checks for the bazel_devtools repository."""

load("//checks:basedpyright.bzl", "basedpyright_aspect")
load("//checks:format.bzl", "ruff_format_aspect")
load("//checks:ruff.bzl", "ruff_lint_aspect")

ruff = ruff_lint_aspect(
    binary = Label("//tools:ruff"),
    configs = [
        Label("//:.ruff.toml"),
        Label("//:.bazel_devtools/ruff.toml"),
    ],
)

basedpyright = basedpyright_aspect(
    binary = Label("//tools:basedpyright"),
    config = Label("//:basedpyright.json"),
    configs = [Label("//:.bazel_devtools/basedpyright.json")],
)

ruff_format = ruff_format_aspect(
    binary = Label("//tools:ruff"),
    configs = [
        Label("//:.ruff.toml"),
        Label("//:.bazel_devtools/ruff.toml"),
    ],
)
