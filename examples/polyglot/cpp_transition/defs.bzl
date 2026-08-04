"""Fixture rule that reaches a C target only through a configuration transition."""


def _configured_transition_impl(_settings, _attr):
    return {
        "//command_line_option:platforms": str(Label("//cpp_transition:configured_platform")),
    }


_configured_transition = transition(
    implementation = _configured_transition_impl,
    inputs = [],
    outputs = ["//command_line_option:platforms"],
)


def _configured_artifact_impl(ctx):
    return [DefaultInfo(files = depset(ctx.files.configured_target))]


configured_artifact = rule(
    implementation = _configured_artifact_impl,
    attrs = {
        "configured_target": attr.label(
            cfg = _configured_transition,
            mandatory = True,
        ),
        "_allowlist_function_transition": attr.label(
            default = "@bazel_tools//tools/allowlists/function_transition_allowlist",
        ),
    },
)
