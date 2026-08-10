# Testing contract

The tiers are intentionally different. A release is supported only when the
relevant tier passes; a unit test alone is not evidence that a consumer module
can resolve and execute the toolchains.

| Tier | Command | Contract | Expected cadence |
| --- | --- | --- | --- |
| Fast | `bazel test //...` | self-hosted Ruff/format/BasedPyright checks, setup state machine, hook installer safety, pre-commit validation, actionlint, recursive Bazel option placement, repository loading | every change, Bazel 9 minimum and pinned version |
| Consumer | `bazel test //:integration_tests --test_output=errors` | scratch polyglot module, positive and negative checks, opt-outs, language isolation, formatter ownership, installed presubmit behavior, IDE metadata, pinned Neovim | every change on the pinned Bazel version |
| Profiling | `bazel test //:profiling_tests --test_output=streamed` | opt-in warm operation timings and Bazel JSON traces from an isolated scratch consumer | before and after performance work on a controlled machine |
| Release | `bazel test //:release_tests --test_output=errors` | fast and consumer tiers together | before a tag |
| Maintainer editor | `bazel run //e2e:probe_current_neovim -- --workspace "$PWD/examples/polyglot"` | the current personal Neovim config attaches BasedPyright, Ruff, clangd, rust-analyzer, ts_ls, and Biome | before a tag and after editor config changes |

The integration runner copies the full repository into `TEST_TMPDIR` and only
mutates that copy. Formatting violations cannot dirty the committed example.
It shares Bazel's download-only repository cache with the host, while keeping
the output/action root isolated. This preserves hermetic action results without
re-downloading LLVM, Rust, Python, and Neovim archives on every run.

The polyglot test proves:

- a minimal unconfigured consumer can preview and complete first-time setup;
- Python-only setup omits the C++, Rust, and TypeScript policy, aspects, formatters, and LLVM
  module extension;
- an existing brownfield policy blocks both plan and initialization without
  modifying the policy or writing setup state;
- a clean repository passes plain `bazel test //...`;
- manual tests are compiled and checked by that command but are not executed;
- Ruff import sorting sees Bazel-owned `PyInfo` dependency sources as
  first-party while continuing to lint only each target's direct sources;
- the LLVM 22.1.6 clang-tidy version and exact resolved policy inventory match
  the reviewed snapshot, required strict checks remain active,
  and alias-effective exclusions remain absent;
- representative enabled and excluded clang-tidy diagnostics behave according
  to the managed family policy;
- a C++ target using Bazel runfiles retains its target-local
  `BAZEL_CURRENT_REPOSITORY` define through clang-tidy compilation-context
  merging, including with a non-empty `implementation_deps` edge;
- a host-incompatible C target reachable only through a custom transitioned
  attribute is linted in its configured target platform while diagnostics from
  an external header dependency remain outside the supported-source boundary;
- each configured checker rejects its own diagnostic fixture;
- target tags suppress only the intended checker;
- independently generated C++-, Rust-, and TypeScript-only scratch workspaces build their
  selected formatter and pass plain `bazel test //...` without loading another
  language's aspect, policy, or toolchain configuration; the TypeScript fixture
  has no hand-written root config targets, proving setup supplies the complete
  `TsConfigInfo` dependency graph;
- format and IDE commands reject an explicitly requested language that was not
  installed;
- generated sources and non-target-owned files are not rewritten;
- write-mode formatting repairs all four languages in the scratch copy;
- editor metadata is valid, TypeScript contains exactly the Bazel-owned source
  graph, and loose or `no-ide` TypeScript files remain excluded;
- a pinned minimal Neovim can resolve all four project roots;
- generated pre-commit and GitHub configurations validate with their pinned
  tools;
- explicit hook installation is executable and a clean staged tree passes;
- formatting, lint, and type failures reject a commit without modifying its
  source file.

When adding a tool or policy rule, add one clean case, one diagnostic fixture,
one target opt-out case, and an editor metadata assertion if it changes the
project model.

## Profiling operations

The profiling target has no latency threshold and is not part of the release
suite. Shared CI hosts are too noisy for a useful performance gate. Instead,
the runner records end-to-end wall time and asks Bazel for a compressed JSON
trace for every measured command. It uses the pinned Bazel binary, a scratch
copy of the polyglot consumer, an isolated output root, and the host's
download-only repository cache when one is available.

The default warm suite measures setup doctor, TypeScript target-source
discovery, direct Biome formatting, end-to-end write-mode formatting,
TypeScript IDE sync, a cached `rules_ts` typecheck test, and the same typecheck
after a harmless source edit. The incremental sample forces TypeScript and the
configured Biome actions to execute without paying for a new Bazel server or
output root. The source-query and direct-Biome cases decompose the component
work in the end-to-end formatter. The optional `check_all` operation measures the
full polyglot contract.

Run more samples, select operations, or include isolated cold output roots
with test arguments:

```sh
bazel test //:profiling_tests --test_output=streamed \
  --test_arg=--runs=5

bazel test //:profiling_tests --test_output=streamed \
  --test_arg=--operation=typescript_check \
  --test_arg=--operation=typescript_format \
  --test_arg=--runs=10

bazel test //:profiling_tests --test_output=streamed \
  --test_arg=--mode=both \
  --test_arg=--operation=all \
  --test_arg=--runs=3
```

Cold samples use a new Bazel output user root for every invocation, so they
include server startup, repository extraction, module loading, analysis, and
actions. They can be much slower than warm samples and should not be compared
to warm latency.

The test's undeclared outputs contain `summary.json`, `summary.md`, and one
`*.json.gz` trace per sample. Compare summaries from the same machine and load
a trace in Perfetto or Chrome's trace viewer. The compressed files use Chrome's
JSON trace-event format and can also be post-processed by scripts.

For `bazel run` operations, the trace describes Bazel's build-and-launch work;
the wall time also includes the launched tool. The formatter launches its
pinned Biome runfile directly after one source query. Use the decomposed
source-query and direct-tool operations to attribute those portions.
