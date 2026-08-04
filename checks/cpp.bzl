"""Public C and C++ check factories without loading other languages."""

load(
    "//third_party/aspect_rules_lint:clang_tidy.bzl",
    _lint_clang_tidy_aspect = "lint_clang_tidy_aspect",
)
load("//checks:format.bzl", _clang_format_aspect = "clang_format_aspect")
load(
    "//checks:propagation.bzl",
    _first_party_dependency_attributes = "first_party_dependency_attributes",
)

_CPP_RULE_KINDS = ["cc_binary", "cc_library"]
_CPP_FORMAT_RULE_KINDS = ["cc_binary", "cc_library", "cc_test"]


def clang_format_aspect(
        binary,
        config,
        rule_kinds = _CPP_FORMAT_RULE_KINDS,
        attr_aspects = _first_party_dependency_attributes):
    """Creates a first-party, graph-propagating C/C++ format aspect."""
    return _clang_format_aspect(
        binary = binary,
        config = config,
        rule_kinds = rule_kinds,
        attr_aspects = attr_aspects,
    )


def lint_clang_tidy_aspect(
        binary,
        configs = [],
        global_config = [],
        gcc_install_dir = [],
        deps = [],
        header_filter = "",
        lint_target_headers = False,
        angle_includes_are_system = True,
        verbose = False,
        rule_kinds = _CPP_RULE_KINDS,
        attr_aspects = _first_party_dependency_attributes):
    """Creates a first-party, graph-propagating clang-tidy aspect."""
    return _lint_clang_tidy_aspect(
        binary = binary,
        configs = configs,
        global_config = global_config,
        gcc_install_dir = gcc_install_dir,
        deps = deps,
        header_filter = header_filter,
        lint_target_headers = lint_target_headers,
        angle_includes_are_system = angle_includes_are_system,
        verbose = verbose,
        rule_kinds = rule_kinds,
        attr_aspects = attr_aspects,
    )
