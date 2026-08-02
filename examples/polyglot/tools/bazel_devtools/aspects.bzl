# ##BAZEL_DEVTOOLS_MANAGED_BEGIN:aspects##
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
# ##BAZEL_DEVTOOLS_MANAGED_END:aspects##
