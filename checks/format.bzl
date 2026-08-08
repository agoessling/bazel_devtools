"""Hermetic formatter-check aspects over source files owned by Bazel targets."""

load("//checks:propagation.bzl", "dependency_infos")

_PYTHON_RULE_KINDS = ["py_binary", "py_library", "py_test"]
_CPP_RULE_KINDS = ["cc_binary", "cc_library", "cc_test"]
_TYPESCRIPT_RULE_KINDS = ["ts_project", "ts_project_rule"]
_PYTHON_EXTENSIONS = ["py", "pyi"]
_CPP_EXTENSIONS = ["c", "cc", "cpp", "cxx", "c++", "h", "hh", "hpp", "hxx", "inc"]
_TYPESCRIPT_EXTENSIONS = ["ts", "tsx"]

_ClangFormatPropagationInfo = provider(
    fields = {
        "format_checks": "transitive clang-format validation outputs",
        "validation": "transitive validation outputs",
    },
)

_BiomeFormatPropagationInfo = provider(
    fields = {
        "format_checks": "transitive Biome format validation outputs",
        "validation": "transitive validation outputs",
    },
)


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


def _merge_clang_format_outputs(ctx, own = None):
    dependencies = dependency_infos(ctx.rule.attr, _ClangFormatPropagationInfo)
    validation = depset(
        transitive = [dependency.validation for dependency in dependencies] +
                     ([own._validation] if own else []),
    )
    format_checks = depset(
        transitive = [dependency.format_checks for dependency in dependencies] +
                     ([own.bazel_devtools_format_checks] if own else []),
    )
    return [
        OutputGroupInfo(
            _validation = validation,
            bazel_devtools_format_checks = format_checks,
        ),
        _ClangFormatPropagationInfo(
            format_checks = format_checks,
            validation = validation,
        ),
    ]


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


def _merge_biome_format_outputs(ctx, own = None):
    dependencies = dependency_infos(ctx.rule.attr, _BiomeFormatPropagationInfo)
    validation = depset(
        transitive = [dependency.validation for dependency in dependencies] +
                     ([own._validation] if own else []),
    )
    format_checks = depset(
        transitive = [dependency.format_checks for dependency in dependencies] +
                     ([own.bazel_devtools_format_checks] if own else []),
    )
    return [
        OutputGroupInfo(
            _validation = validation,
            bazel_devtools_format_checks = format_checks,
        ),
        _BiomeFormatPropagationInfo(
            format_checks = format_checks,
            validation = validation,
        ),
    ]


def _biome_format_impl(target, ctx):
    if target.label.repo_name or ctx.rule == None:
        return _empty_validation()
    tags = _tags(ctx)
    if "no-format" in tags or "no-biome-format" in tags:
        return _merge_biome_format_outputs(ctx)
    if ctx.rule.kind not in ctx.attr._rule_kinds:
        return _merge_biome_format_outputs(ctx)
    sources = _owned_sources(ctx, _TYPESCRIPT_EXTENSIONS)
    if not sources:
        return _merge_biome_format_outputs(ctx)
    own = _run_check(
        ctx,
        "BiomeFormat",
        ctx.executable._binary,
        [
            "format",
            "--config-path",
            ctx.file._config.path,
            "--max-diagnostics=none",
        ],
        ctx.files._configs,
        sources,
    )[0]
    return _merge_biome_format_outputs(ctx, own)


def biome_format_aspect(
        binary,
        config,
        configs = [],
        rule_kinds = _TYPESCRIPT_RULE_KINDS,
        attr_aspects = []):
    """Creates a Biome format-check aspect for TypeScript targets."""
    return aspect(
        implementation = _biome_format_impl,
        attr_aspects = attr_aspects,
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
            "_configs": attr.label_list(
                default = [config] + configs,
                allow_files = True,
            ),
            "_rule_kinds": attr.string_list(default = rule_kinds),
        },
    )


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
    if target.label.repo_name or ctx.rule == None:
        return _empty_validation()
    tags = _tags(ctx)
    if "no-format" in tags or "no-clang-format" in tags:
        return _merge_clang_format_outputs(ctx)
    if ctx.rule.kind not in ctx.attr._rule_kinds:
        return _merge_clang_format_outputs(ctx)
    sources = _owned_sources(ctx, _CPP_EXTENSIONS, ["srcs", "hdrs", "textual_hdrs"])
    if not sources:
        return _merge_clang_format_outputs(ctx)
    own = _run_check(
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
    )[0]
    return _merge_clang_format_outputs(ctx, own)


def clang_format_aspect(binary, config, rule_kinds = _CPP_RULE_KINDS, attr_aspects = []):
    """Creates a clang-format check aspect for C and C++ targets."""
    return aspect(
        implementation = _clang_format_impl,
        attr_aspects = attr_aspects,
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
