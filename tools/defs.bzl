"""Public build helpers used by bootstrapped consuming repositories."""

load("@aspect_rules_lint//format:defs.bzl", "format_multirun")
load("//tools:tool_binary.bzl", _tool_binary = "tool_binary")

tool_binary = _tool_binary


def bazel_devtools_formatters(name, clang_format):
    """Declares the canonical formatter multirun used by the format driver."""
    format_multirun(
        name = name,
        python = "@bazel_devtools//tools:ruff",
        c = clang_format,
        cc = clang_format,
        # Target discovery and exclusions have already been resolved by the
        # Bazel query driver. This also keeps formatting usable in exported
        # source archives and disposable integration workspaces without .git.
        disable_git_attribute_checks = True,
        rust = "@rules_rust//rust/toolchain:current_rustfmt_toolchain",
    )
