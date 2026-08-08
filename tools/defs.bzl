"""Public build helpers used by bootstrapped consuming repositories."""

load("@aspect_rules_lint//format:defs.bzl", "format_multirun")
load("//tools:tool_binary.bzl", _tool_binary = "tool_binary")

tool_binary = _tool_binary


def bazel_devtools_formatters(name, languages, clang_format = None):
    """Declares the canonical formatter multirun used by the format driver."""
    supported = ["python", "cpp", "rust", "typescript"]
    unknown = [language for language in languages if language not in supported]
    if unknown:
        fail("unsupported formatter languages: {}".format(", ".join(unknown)))
    if not languages:
        fail("at least one formatter language is required")
    if "cpp" in languages and not clang_format:
        fail("clang_format is required when C++ support is selected")
    formatters = {}
    if "python" in languages:
        formatters["python"] = "@bazel_devtools//tools:ruff"
    if "cpp" in languages:
        formatters["c"] = clang_format
        formatters["cc"] = clang_format
    if "rust" in languages:
        formatters["rust"] = "@rules_rust//rust/toolchain:current_rustfmt_toolchain"
    if formatters:
        format_multirun(
            name = name,
            # Target discovery and exclusions have already been resolved by the
            # Bazel query driver. This also keeps formatting usable in exported
            # source archives and disposable integration workspaces without .git.
            disable_git_attribute_checks = True,
            **formatters
        )
    else:
        # TypeScript write-mode formatting is dispatched directly by the
        # target-graph driver so rules_lint's JavaScript-only file matcher
        # cannot accidentally discard .ts and .tsx paths.
        native.filegroup(name = name)
