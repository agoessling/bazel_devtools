"""Public TypeScript and TSX check factories without loading other languages."""

load("//checks:format.bzl", _biome_format_aspect = "biome_format_aspect")
load(
    "//checks:propagation.bzl",
    "dependency_infos",
    _first_party_dependency_attributes = "first_party_dependency_attributes",
)

_TYPESCRIPT_RULE_KINDS = ["ts_project", "ts_project_rule"]
_TYPESCRIPT_EXTENSIONS = ["ts", "tsx"]

_BiomeLintPropagationInfo = provider(
    fields = {
        "lint_checks": "transitive Biome lint validation outputs",
        "validation": "transitive validation outputs",
    },
)


def _empty_validation():
    return [OutputGroupInfo(_validation = depset([]), bazel_devtools_lint_checks = depset([]))]


def _merge_biome_lint_outputs(ctx, own = None):
    dependencies = dependency_infos(ctx.rule.attr, _BiomeLintPropagationInfo)
    validation = depset(
        transitive = [dependency.validation for dependency in dependencies] +
                     ([own._validation] if own else []),
    )
    lint_checks = depset(
        transitive = [dependency.lint_checks for dependency in dependencies] +
                     ([own.bazel_devtools_lint_checks] if own else []),
    )
    return [
        OutputGroupInfo(
            _validation = validation,
            bazel_devtools_lint_checks = lint_checks,
        ),
        _BiomeLintPropagationInfo(
            lint_checks = lint_checks,
            validation = validation,
        ),
    ]


def _biome_lint_impl(target, ctx):
    if target.label.repo_name or ctx.rule == None:
        return _empty_validation()
    tags = getattr(ctx.rule.attr, "tags", [])
    if "no-lint" in tags or "no-biome-lint" in tags:
        return _merge_biome_lint_outputs(ctx)
    if ctx.rule.kind not in ctx.attr._rule_kinds or not hasattr(ctx.rule.attr, "srcs"):
        return _merge_biome_lint_outputs(ctx)
    sources = [
        file
        for file in ctx.rule.files.srcs
        if file.is_source and file.extension in _TYPESCRIPT_EXTENSIONS
    ]
    if not sources:
        return _merge_biome_lint_outputs(ctx)

    marker = ctx.actions.declare_file(ctx.label.name + ".biome_lint.ok")
    args = ctx.actions.args()
    args.add(ctx.executable._binary)
    args.add(marker)
    args.add(ctx.file._config)
    args.add_all(sources)
    ctx.actions.run_shell(
        command = """
set -eu
tool="$1"
marker="$2"
config="$3"
shift 3
"$tool" lint --config-path "$config" --error-on-warnings --max-diagnostics=none "$@"
touch "$marker"
""",
        arguments = [args],
        inputs = depset(sources + ctx.files._configs),
        mnemonic = "BiomeLint",
        outputs = [marker],
        progress_message = "Linting %{label} with Biome",
        tools = [ctx.executable._binary],
    )
    own = OutputGroupInfo(
        _validation = depset([marker]),
        bazel_devtools_lint_checks = depset([marker]),
    )
    return _merge_biome_lint_outputs(ctx, own)


def biome_lint_aspect(
        binary,
        config,
        configs = [],
        rule_kinds = _TYPESCRIPT_RULE_KINDS,
        attr_aspects = _first_party_dependency_attributes):
    """Creates a first-party, graph-propagating Biome lint aspect."""
    return aspect(
        implementation = _biome_lint_impl,
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


def biome_format_aspect(
        binary,
        config,
        configs = [],
        rule_kinds = _TYPESCRIPT_RULE_KINDS,
        attr_aspects = _first_party_dependency_attributes):
    """Creates a first-party, graph-propagating TypeScript format aspect."""
    return _biome_format_aspect(
        binary = binary,
        config = config,
        configs = configs,
        rule_kinds = rule_kinds,
        attr_aspects = attr_aspects,
    )
