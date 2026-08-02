"""Hermetic formatter-check aspects over source files owned by Bazel targets."""

_PYTHON_RULE_KINDS = ["py_binary", "py_library", "py_test"]
_CPP_RULE_KINDS = ["cc_binary", "cc_library", "cc_test"]
_PYTHON_EXTENSIONS = ["py", "pyi"]
_CPP_EXTENSIONS = ["c", "cc", "cpp", "cxx", "c++", "h", "hh", "hpp", "hxx", "inc"]


def _tags(ctx):
    return getattr(ctx.rule.attr, "tags", [])


def _owned_sources(ctx, extensions, attributes = ["srcs"]):
    sources = []
    for attribute in attributes:
        if hasattr(ctx.rule.attr, attribute):
            sources.extend(getattr(ctx.rule.files, attribute))
    return [file for file in sources if file.is_source and file.extension in extensions]


def _empty_validation():
    return [OutputGroupInfo(_validation = depset([]), bazel_devtools_format_checks = depset([]))]


def _run_check(ctx, mnemonic, binary, arguments, inputs, sources):
    marker = ctx.actions.declare_file(ctx.label.name + ".{}.ok".format(mnemonic.lower()))
    args = ctx.actions.args()
    args.add(binary)
    args.add(marker)
    args.add_all(arguments)
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
        inputs = depset(sources + inputs),
        mnemonic = mnemonic,
        outputs = [marker],
        progress_message = "Checking format for %{label}",
        tools = [binary],
    )
    return [
        OutputGroupInfo(
            _validation = depset([marker]),
            bazel_devtools_format_checks = depset([marker]),
        ),
    ]


def _ruff_format_impl(target, ctx):
    if target.label.workspace_name:
        return _empty_validation()
    tags = _tags(ctx)
    if "no-format" in tags or "no-ruff-format" in tags:
        return _empty_validation()
    if ctx.rule.kind not in ctx.attr._rule_kinds:
        return _empty_validation()
    sources = _owned_sources(ctx, _PYTHON_EXTENSIONS)
    if not sources:
        return _empty_validation()
    return _run_check(
        ctx,
        "RuffFormat",
        ctx.executable._binary,
        [
            "format",
            "--check",
            "--force-exclude",
            "--config",
            ctx.files._configs[0].path,
        ],
        ctx.files._configs,
        sources,
    )


def ruff_format_aspect(binary, configs, rule_kinds = _PYTHON_RULE_KINDS):
    """Creates a Ruff format-check aspect for Python targets."""
    return aspect(
        implementation = _ruff_format_impl,
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


def _clang_format_impl(target, ctx):
    if target.label.workspace_name:
        return _empty_validation()
    tags = _tags(ctx)
    if "no-format" in tags or "no-clang-format" in tags:
        return _empty_validation()
    if ctx.rule.kind not in ctx.attr._rule_kinds:
        return _empty_validation()
    sources = _owned_sources(ctx, _CPP_EXTENSIONS, ["srcs", "hdrs", "textual_hdrs"])
    if not sources:
        return _empty_validation()
    return _run_check(
        ctx,
        "ClangFormat",
        ctx.executable._binary,
        [
            "--dry-run",
            "--Werror",
            "--fallback-style=none",
            "--style=file:" + ctx.file._config.path,
        ],
        [ctx.file._config],
        sources,
    )


def clang_format_aspect(binary, config, rule_kinds = _CPP_RULE_KINDS):
    """Creates a clang-format check aspect for C and C++ targets."""
    return aspect(
        implementation = _clang_format_impl,
        attrs = {
            "_binary": attr.label(
                default = binary,
                executable = True,
                cfg = "exec",
            ),
            "_config": attr.label(
                default = config,
                allow_single_file = True,
            ),
            "_rule_kinds": attr.string_list(default = rule_kinds),
        },
        fragments = ["cpp"],
    )
