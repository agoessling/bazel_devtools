# Contributor instructions

## Scope

This file is for agents changing `bazel_devtools` itself. It is intentionally
not installed into consuming repositories.

`bazel_devtools` is an opinionated, Bazel-first tooling layer for Linux x86_64
repositories using Bazel 9 or newer. Bazel targets define the supported source
boundary; do not replace target-graph discovery with repository-wide file
scanning.

## Product contracts

- Keep Python, C++, and Rust checks strict by default. Do not silence a
  diagnostic, add an opt-out tag, or weaken a rule group merely to make a test
  pass. Group real-project findings by rule and ask for a policy decision when
  the signal-to-noise tradeoff is subjective.
- CI tools are pinned through Bazel. Editors may own their language-server
  binaries, while `bazel_devtools` owns the generated project metadata.
- Preserve user-owned content outside managed blocks. Setup and upgrade must
  remain idempotent, detect concurrent local/upstream changes, and report
  conflicts without overwriting local work.
- Prefer native tool configuration inheritance. Add a managed block only when
  the tool has no suitable extension mechanism.

## Changing installed policy

- `tools/templates.py` is the source of truth for files installed into a
  consumer repository.
- Keep the repository's dogfood policies under `.bazel_devtools/` synchronized
  with the corresponding consumer templates.
- After changing a template, update the committed example by running this from
  `examples/polyglot`:

  ```sh
  bazel run @bazel_devtools//tools:setup -- upgrade
  bazel run @bazel_devtools//tools:setup -- doctor
  ```

- Do not hand-edit `examples/polyglot/.bazel_devtools/state.json`. Do not patch
  installed managed blocks directly when the intended change belongs in the
  template.
- Document every global exclusion next to the rule and update the README or
  design notes when it changes the public policy.

## Testing

Use Bazel as the authoritative validation path:

```sh
# Fast repository dogfood and unit tests.
bazel test //... --test_output=errors

# Full scratch consumer, checker, formatter, metadata, and pinned-Neovim test.
bazel test //:integration_tests --test_output=errors

# Release gate.
bazel test //:release_tests --test_output=errors
```

Run the smallest relevant target while iterating. Run the consumer integration
test for changes to templates, aspects, toolchains, formatting, opt-outs, setup,
or IDE metadata. It is intentionally slower because it creates an isolated
polyglot workspace and output root.

The files under `e2e/testdata/violations/` are deliberately invalid data
fixtures. Each should violate only the checker named by the fixture and remain
clean under unrelated checkers. Do not add them to linted source targets or
bulk-format them. Integration formatting happens only in a scratch copy so the
committed fixtures and example remain unchanged.

## Editor boundary

The maintainer's personal Neovim configuration under `~/.config/nvim` is
outside this repository. The maintainer probe may read and exercise that
configuration, but do not modify it unless explicitly requested.
