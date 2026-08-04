"""A hermetic Ruff lint aspect over repository-owned Python sources."""

load("@rules_python//python:defs.bzl", "PyInfo")

_PYTHON_RULE_KINDS = ["py_binary", "py_library", "py_test"]
_PYTHON_EXTENSIONS = ["py", "pyi"]


def _empty_validation():
    return [OutputGroupInfo(
        _validation = depset([]),
        bazel_devtools_lint_checks = depset([]),
    )]


def _ruff_lint_impl(target, ctx):
    if target.label.workspace_name:
        return _empty_validation()
    tags = getattr(ctx.rule.attr, "tags", [])
    if "no-lint" in tags or "no-ruff" in tags:
        return _empty_validation()
    if ctx.rule.kind not in ctx.attr._rule_kinds:
        return _empty_validation()
    if not hasattr(ctx.rule.attr, "srcs"):
        return _empty_validation()

    sources = [
        file
        for file in ctx.rule.files.srcs
        if file.is_source and file.extension in _PYTHON_EXTENSIONS
    ]
    if not sources:
        return _empty_validation()

    transitive_sources = depset()
    if PyInfo in target:
        # Ruff lints only direct sources below, but import sorting inspects the
        # filesystem to distinguish first-party modules. Stage the Bazel-owned
        # dependency graph so sandboxed classification matches the workspace.
        transitive_sources = depset(
            transitive = [
                target[PyInfo].transitive_sources,
                target[PyInfo].transitive_pyi_files,
            ],
        )

    marker = ctx.actions.declare_file(ctx.label.name + ".ruff.ok")
    args = ctx.actions.args()
    args.add(ctx.executable._binary)
    args.add(marker)
    args.add("check")
    args.add("--force-exclude")
    args.add("--config")
    args.add(ctx.files._configs[0].path)
    args.add_all(sources)
    ctx.actions.run_shell(
        command = """
set -eu
tool="$1"
marker="$2"
shift 2
"$tool" "$@"
touch "$marker"
""",
        arguments = [args],
        inputs = depset(
            sources + ctx.files._configs,
            transitive = [transitive_sources],
        ),
        mnemonic = "RuffLint",
        outputs = [marker],
        progress_message = "Linting %{label} with Ruff",
        tools = [ctx.executable._binary],
    )
    return [OutputGroupInfo(
        _validation = depset([marker]),
        bazel_devtools_lint_checks = depset([marker]),
    )]


def ruff_lint_aspect(binary, configs, rule_kinds = _PYTHON_RULE_KINDS):
    """Creates a Ruff lint aspect for direct repository-owned Python sources."""
    return aspect(
        implementation = _ruff_lint_impl,
        attrs = {
            "_binary": attr.label(
                default = binary,
                executable = True,
                cfg = "exec",
            ),
            "_configs": attr.label_list(
                default = configs,
                allow_files = True,
            ),
            "_rule_kinds": attr.string_list(default = rule_kinds),
        },
    )
