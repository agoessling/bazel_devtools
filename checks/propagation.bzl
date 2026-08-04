"""Shared aspect propagation policy for Bazel-owned source graphs."""


def _labels(value):
    value_type = type(value)
    if value_type == "Label":
        return [value]
    if value_type in ("list", "tuple"):
        return [item for item in value if type(item) == "Label"]
    return []


def first_party_dependency_attributes(propagation_ctx):
    """Returns non-tool dependency attributes that can reach first-party targets.

    Bazel invokes this callback before analyzing an aspect edge. Following the
    rule's actual label attributes, rather than a fixed set such as `deps`, lets
    checks reach configured targets behind arbitrary custom-rule transitions.
    Propagation stops after a direct external dependency, keeping third-party
    repositories outside the supported-source boundary.
    """
    if propagation_ctx.rule.label.repo_name:
        return []

    attributes = []
    for name in dir(propagation_ctx.rule.attr):
        metadata = getattr(propagation_ctx.rule.attr, name)
        if metadata.is_tool:
            continue
        for label in _labels(metadata.value):
            if label.repo_name == "":
                attributes.append(name)
                break
    return attributes


def dependency_infos(rule_attributes, provider):
    """Collects an aspect provider from propagated label attributes."""
    infos = []
    for name in dir(rule_attributes):
        value = getattr(rule_attributes, name)
        values = value if type(value) in ("list", "tuple") else [value]
        for target in values:
            if type(target) == "Target" and provider in target:
                infos.append(target[provider])
    return infos
