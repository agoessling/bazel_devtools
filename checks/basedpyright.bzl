"""A BasedPyright aspect over targets providing standard PyInfo."""

load("@rules_python//python:defs.bzl", "PyInfo")

_PYTHON_RULE_KINDS = ["py_binary", "py_library", "py_test"]
_PYTHON_EXTENSIONS = ["py", "pyi"]


def _empty_validation():
    return [OutputGroupInfo(_validation = depset([]), bazel_devtools_type_checks = depset([]))]


def _relative_from_output_to_execroot(output):
    directory_components = output.dirname.split("/")
    return "/".join([".."] * len(directory_components))


def _execroot_relative(prefix, path):
    if path == ".":
        return prefix
    return prefix + "/" + path


def _import_paths(target, ctx, prefix):
    paths = {
        prefix: True,
        _execroot_relative(prefix, ctx.bin_dir.path): True,
    }
    if PyInfo not in target:
        return paths.keys()
    for import_path in target[PyInfo].imports.to_list():
        if import_path == ctx.workspace_name or import_path == ".":
            paths[prefix] = True
        elif import_path.startswith(ctx.workspace_name + "/"):
            relative = import_path[len(ctx.workspace_name) + 1:]
            paths[_execroot_relative(prefix, relative)] = True
            paths[_execroot_relative(prefix, ctx.bin_dir.path + "/" + relative)] = True
        else:
            external = "external/" + import_path
            paths[_execroot_relative(prefix, external)] = True
            paths[_execroot_relative(prefix, ctx.bin_dir.path + "/" + external)] = True
    return sorted(paths.keys())


def _basedpyright_impl(target, ctx):
    if target.label.workspace_name:
        return _empty_validation()
    tags = getattr(ctx.rule.attr, "tags", [])
    if "no-typecheck" in tags or "no-basedpyright" in tags:
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
        transitive_sources = depset(
            transitive = [
                target[PyInfo].transitive_sources,
                target[PyInfo].transitive_pyi_files,
            ],
        )

    generated_config = ctx.actions.declare_file(
        ctx.label.name + ".basedpyright.json",
    )
    prefix = _relative_from_output_to_execroot(generated_config)
    ctx.actions.write(
        output = generated_config,
        content = json.encode_indent({
            "extends": _execroot_relative(prefix, ctx.file._config.path),
            "extraPaths": _import_paths(target, ctx, prefix),
        }, indent = "  ") + "\n",
    )

    marker = ctx.actions.declare_file(ctx.label.name + ".basedpyright.ok")
    args = ctx.actions.args()
    args.add(ctx.executable._binary)
    args.add(marker)
    args.add("--project")
    args.add(generated_config)
    args.add("--level")
    args.add("error")
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
            sources + ctx.files._configs + [generated_config],
            transitive = [transitive_sources],
        ),
        mnemonic = "BasedPyright",
        outputs = [marker],
        progress_message = "Type checking %{label} with BasedPyright",
        tools = [ctx.executable._binary],
    )
    return [
        OutputGroupInfo(
            _validation = depset([marker]),
            bazel_devtools_type_checks = depset([marker]),
        ),
    ]


def basedpyright_aspect(binary, config, configs = [], rule_kinds = _PYTHON_RULE_KINDS):
    """Creates a BasedPyright aspect using standard PyInfo for import resolution."""
    all_configs = [config] + configs
    return aspect(
        implementation = _basedpyright_impl,
        attr_aspects = ["deps"],
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
                default = all_configs,
                allow_files = True,
            ),
            "_rule_kinds": attr.string_list(default = rule_kinds),
        },
    )
