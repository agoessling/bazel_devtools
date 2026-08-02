# Changelog

## Unreleased

- Add Bazel-owned formatting and test-time checks for Python, C++, and Rust.
- Add safe setup, doctor, and stateful three-way upgrades using managed blocks.
- Add Bazel-generated project metadata and Neovim contract probes.
- Add scratch polyglot integration coverage, target opt-outs, generated-source
  boundaries, and language-isolated target graphs.
- Dogfood Ruff lint, Ruff format-check, and BasedPyright on the repository's
  own Python targets during plain `bazel test //...`.
- Make custom formatter and BasedPyright validation actions propagate tool
  failures to Bazel.
- Limit generated Pyright workspace models to Bazel-owned Python sources and
  exclude nested Bazel, cache, external-repository, and VCS directories.
- Start from strict, coherent Ruff, BasedPyright, clang-tidy, and Clippy
  policies; exclude only formatter conflicts, explicitly accepted project
  choices, non-portable C++ runtime policies, and Cargo-only metadata checks.
- Keep integration diagnostic fixtures clean under every checker except the
  one each fixture is intended to exercise.
- Add repository-local contributor guidance for agents working on
  `bazel_devtools` without installing agent instructions into consumer repos.
- Add a read-only setup plan, block ambiguous brownfield policy adoption before
  writes, and exercise first-time setup from an unconfigured scratch consumer.
- Document local-checkout and full-commit Git overrides for pre-registry use.
- Bootstrap a check-only, Bazel-pinned pre-commit hook and a managed GitHub
  presubmit workflow, with safe installation, actionlint, staged-failure, and
  upgrade coverage.

Releases use semantic Git tags. Before 1.0, a minor release may change the
opinionated default policy; upgrade preserves local overrides and reports any
three-way conflict for review.
