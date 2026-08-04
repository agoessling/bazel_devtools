# Patched aspect_rules_lint clang-tidy aspect

`clang_tidy.bzl` is vendored from `aspect-build/rules_lint` v2.7.2, commit
`a61a4f3`. The unmodified source has SHA-256
`79c584f94231d1f7038803a4445fd1a02157512cd9b58f46a8e2352a1bf94c11`.

The local change preserves a target's `CcCompilationContext.local_defines`
when the aspect augments that context with `implementation_deps`. Upstream
unconditionally calls `cc_common.merge_compilation_contexts` for every rule
that has the attribute, even when it is empty. That API treats every input as
a dependency and therefore does not preserve target-local defines. The real
compile still receives them, causing clang-tidy-only compiler errors for APIs
such as Bazel C++ runfiles and its `BAZEL_CURRENT_REPOSITORY` define.

The patched aspect avoids an empty merge and carries the original local
defines separately when a non-empty implementation dependency merge is
required. It also exposes upstream Bazel's `attr_aspects` setting through the
factory and declines lint actions for external-repository targets, allowing
bazel_devtools's public wrapper to propagate through first-party custom-rule
edges without linting third-party source.

The adapter also writes a one-entry compilation database for each lint action.
Unlike a fixed argument list, that database preserves Bazel's configured
compiler as argv[0], allowing Clang tooling to infer cross-target and GCC
system-header details. External repository include roots become system paths,
and `clang_tidy_filter.sh` removes non-compiler diagnostics whose primary file
is listed in a Bazel-owner manifest. `clang-diagnostic-error` is deliberately
retained so a broken compiler model cannot appear clean.

Relative loads and the lint-options label point back to the pinned
`@aspect_rules_lint` module; the remaining implementation and settings stay
upstream-owned. Remove this copy after the compilation-context,
configured-target, cross-toolchain, and external-header regressions pass with
the pinned upstream release.

The vendored source remains under the upstream Apache License 2.0 in
`LICENSE`.
