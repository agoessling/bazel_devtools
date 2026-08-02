# Testing contract

The tiers are intentionally different. A release is supported only when the
relevant tier passes; a unit test alone is not evidence that a consumer module
can resolve and execute the toolchains.

| Tier | Command | Contract | Expected cadence |
| --- | --- | --- | --- |
| Fast | `bazel test //...` | self-hosted Ruff/format/BasedPyright checks, setup state machine, hook installer safety, pre-commit validation, actionlint, recursive Bazel option placement, repository loading | every change, Bazel 9 minimum and pinned version |
| Consumer | `bazel test //:integration_tests --test_output=errors` | scratch polyglot module, positive and negative checks, opt-outs, language isolation, formatter ownership, installed presubmit behavior, IDE metadata, pinned Neovim | every change on the pinned Bazel version |
| Release | `bazel test //:release_tests --test_output=errors` | fast and consumer tiers together | before a tag |
| Maintainer editor | `bazel run //e2e:probe_current_neovim -- --workspace "$PWD/examples/polyglot"` | the current personal Neovim config attaches BasedPyright, Ruff, clangd, and rust-analyzer | before a tag and after editor config changes |

The integration runner copies the full repository into `TEST_TMPDIR` and only
mutates that copy. Formatting violations cannot dirty the committed example.
It shares Bazel's download-only repository cache with the host, while keeping
the output/action root isolated. This preserves hermetic action results without
re-downloading LLVM, Rust, Python, and Neovim archives on every run.

The polyglot test proves:

- a minimal unconfigured consumer can preview and complete first-time setup;
- an existing brownfield policy blocks both plan and initialization without
  modifying the policy or writing setup state;
- a clean repository passes plain `bazel test //...`;
- each configured checker rejects its own diagnostic fixture;
- target tags suppress only the intended checker;
- Python-only, C++-only, and Rust-only target graphs still analyze;
- generated sources and non-target-owned files are not rewritten;
- write-mode formatting repairs all three languages in the scratch copy;
- editor metadata is valid and contains the expected target graph;
- a pinned minimal Neovim can resolve all three project roots;
- generated pre-commit and GitHub configurations validate with their pinned
  tools;
- explicit hook installation is executable and a clean staged tree passes;
- formatting, lint, and type failures reject a commit without modifying its
  source file.

When adding a tool or policy rule, add one clean case, one diagnostic fixture,
one target opt-out case, and an editor metadata assertion if it changes the
project model.
