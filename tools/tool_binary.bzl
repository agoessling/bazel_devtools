"""Expose a single executable file as a Bazel executable target."""


def _tool_binary_impl(ctx):
    output = ctx.actions.declare_file(ctx.label.name)
    ctx.actions.symlink(
        output = output,
        target_file = ctx.file.src,
        is_executable = True,
    )
    return [DefaultInfo(executable = output, files = depset([output]))]


tool_binary = rule(
    implementation = _tool_binary_impl,
    attrs = {
        "src": attr.label(
            allow_single_file = True,
            cfg = "exec",
            mandatory = True,
        ),
    },
    executable = True,
)
