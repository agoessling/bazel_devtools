# bazel_devtools

`bazel_devtools` is an opinionated, Bazel-first development-tooling layer for
Linux repositories containing Python, C++, Rust, and TypeScript/TSX. Bazel
targets define the source boundary: checks run as aspects during `bazel test`,
and write-mode formatting touches only source files owned by selected Bazel
targets.

The default policy uses:

- Ruff for Python formatting and linting;
- BasedPyright in all mode for Python type checking;
- clang-format and clang-tidy for C and C++;
- rustfmt, Clippy, and rust-analyzer for Rust;
- Biome for TypeScript and TSX formatting and linting;
- TypeScript 5.9 through `rules_ts` with a strict inherited `tsconfig.user.json`;
- target-graph discovery, with generated and external files excluded by default;
- editor-owned language-server binaries with Bazel-generated project metadata.

Lint and type-check defaults start strict: Ruff enables every stable rule,
BasedPyright uses `all`, clang-tidy enables reviewed general-purpose families,
Clippy enables `all`, `pedantic`, and `nursery` with warnings denied, Biome
enables its stable recommended rules with warnings treated as failures, and
TypeScript enables `strict` plus additional unchecked-access and unused-code
diagnostics.
clang-tidy begins from `-*`, so vendor-specific families cannot enter the policy
implicitly, and records narrow platform, API-design, and high-noise exclusions,
including the diagnostic that requires redundant parentheses around
conventional mathematical operator precedence. Its resolved LLVM 22.1.6
inventory is regression tested so toolchain upgrades require policy review.
The reviewed high-noise exclusions include LLVM 22's unchecked-container-access
rule, which cannot offer `.at()` for C++20 spans and is pervasive even when
callers have already established the relevant invariant.
Clippy's `cargo` group is excluded because it invokes Cargo metadata and does
not describe a Bazel-native build.
The managed policy contains only compatibility exceptions; repository-specific
exceptions should be narrow and documented. The opinionated baseline also
allows assertions, standard-library `unittest` assertion helpers, CLI output,
Bazel-owned subprocesses, and Bazel-generated XML. `reportUnusedCallResult` is
disabled because intentionally discarded API-builder return values are common
and assigning each one to `_` adds little information.

Python targets use Bazel's explicit package-init mode. A real `__init__.py`
must be declared in the target graph, while a directory without one remains a
namespace package; Bazel does not synthesize empty package files in runfiles.

## Install in a repository

Until `bazel_devtools` is published in the Bazel Central Registry, pair the
module dependency with either a local checkout override for development or a
full-commit Git override for reproducible CI. See [the adoption guide](docs/adoption.md).

```starlark
# MODULE.bazel
bazel_dep(name = "bazel_devtools", version = "0.1.0")
local_path_override(
    module_name = "bazel_devtools",
    path = "../bazel_devtools",
)
```

```sh
bazel run @bazel_devtools//tools:setup -- plan --language python --language cpp
bazel run @bazel_devtools//tools:setup -- init --language python --language cpp
bazel test //...
bazel run //:install-hooks
bazel run //:format -- //...
bazel run //:ide-sync
```

Repeat `--language` to select any combination of `python`, `cpp`, `rust`, and
`typescript`. Omitting it during first-time setup installs all four
integrations. The selection is persisted for `doctor`, `upgrade`, formatting,
and IDE metadata generation, so an unused language does not pull its formatter
or toolchain into the consuming repository's configured target graph. Because
`plan` is read-only, repeat the same selection when running `init`.

Language selection avoids configuring and downloading unused compiler and
formatter toolchains during normal consumer commands. `bazel_devtools` is still
one Bazel module, so module resolution can include the rule-set metadata needed
to support all four languages even when only a subset is installed.

`setup plan` is read-only with respect to repository configuration and setup
state. It reports every file or block that initialization would add and exits
with status 2 when an existing policy needs an explicit migration. Setup will
not append duplicate clang-format, clang-tidy, or rustfmt policy keys, and it
will not silently bypass existing Ruff or Pyright configuration locations.
Repositories that relied on Bazel synthesizing `__init__.py` files must add
real files to the appropriate Python targets before adopting the generated
configuration.

Commit the files created by `setup init`. Ruff, BasedPyright, Biome, and
TypeScript use native configuration inheritance, so repository overrides
belong in `.ruff.toml`, `basedpyright.json`, `biome.json`, and
`tsconfig.user.json`. The root `tsconfig.json` is generated editor metadata;
do not put application policy in it.
TypeScript setup owns the toolchain and policy integration, while an
application continues to own its `package.json`, package-manager lockfile,
React version, and Bazel npm targets. Setup also publishes `//:tsconfig_base`
and `//:tsconfig` with the Bazel provider edges needed by sandboxed typecheck
actions. Build and bundler configuration remains application-owned. Files that
cannot inherit contain
narrowly scoped markers such as:

```text
# ##BAZEL_DEVTOOLS_MANAGED_BEGIN:checks##
...
# ##BAZEL_DEVTOOLS_MANAGED_END:checks##
```

Edit inside a managed block only when an override is necessary. The setup state
records the installed template body, not a named policy profile, so upgrades
can distinguish pristine content from a local override.

For Clippy, append repeated `test
--@@rules_rust+//rust/settings:clippy_flag=-Aclippy::check_name` entries outside
the managed block. Those flags are applied after the strict baseline. Do not
enable Clippy's `restriction` group wholesale: it contains deliberately
contradictory policy checks; enable useful restriction lints individually.

## Target-level opt-outs

Tags are the public exception mechanism:

| Concern | Tags |
| --- | --- |
| all formatting | `no-format` |
| Python formatting | `no-ruff-format` |
| C/C++ formatting | `no-clang-format` |
| Rust formatting | `no-rustfmt` |
| TypeScript/TSX formatting | `no-biome-format` |
| Ruff, clang-tidy, or Biome lint | `no-lint` |
| TypeScript/TSX lint | `no-biome-lint` |
| BasedPyright | `no-typecheck` or `no-basedpyright` |
| Clippy | `no-clippy` or `no-lint` |
| editor project discovery | `no-ide` |

Prefer the narrowest tag and leave a comment explaining the exception.

## Presubmit and CI

Setup creates `.pre-commit-config.yaml` and a dedicated
`.github/workflows/bazel-devtools.yml`. Both run the same authoritative,
check-only command:

```sh
bazel test //... --test_output=errors
```

Install the local Git hook explicitly after setup:

```sh
bazel run //:install-hooks
```

The installer changes only `.git/hooks/pre-commit`, marks its hook as managed,
and refuses to replace an unrelated hook. The hook resolves the Bazel-pinned
pre-commit 4.6.0 executable on each run, so it remains valid after `bazel
clean`. Pre-commit temporarily isolates unstaged changes, while the local hook
itself never formats or stages files. If the formatting check fails, run
`bazel run //:format`, review the result, and stage it normally.

The generated GitHub workflow runs for pull requests and pushes to every
branch, uses read-only permissions, pins Actions by full commit, avoids saving
caches from pull requests, and cancels superseded runs.

## Upgrade

Update the `bazel_dep` or override, then run:

```sh
bazel run @bazel_devtools//tools:setup -- upgrade
bazel run @bazel_devtools//tools:setup -- doctor
bazel test //...
```

To change the installed integrations, pass the new complete selection to
`upgrade`, for example `upgrade --language python --language cpp`. Policy files
for a removed language are left in place but retired from setup management;
generated checks, formatters, and toolchain configuration stop referencing it.
If an upgrade reports a conflict, the persisted selection and active generated
configuration remain unchanged until the conflict is resolved and the command
is rerun.

Pristine managed content updates automatically. Local content is preserved. If
both the local copy and upstream template changed, setup writes a unified diff
under `.bazel_devtools/updates/` and exits with status 2. Apply or adapt the
change, rerun `upgrade`, and it will recognize the resolved upstream body. New
templates can be introduced without rerunning initialization, and retired
templates are left on disk while their ownership record is removed.

## Editors

Editors own their language-server executables; the repository owns their
project models. `bazel run //:ide-sync` writes:

- `pyrightconfig.json` for BasedPyright/Pyright;
- `compile_commands.json` for clangd;
- `rust-project.json` for rust-analyzer;
- `tsconfig.json` for the TypeScript language server.

The generated TypeScript config extends `tsconfig.user.json` and lists the
exact Bazel-owned `.ts` and `.tsx` sources of first-party targets, excluding
targets tagged `no-ide`. Its marker prevents sync from overwriting an
application-owned config during adoption.

The Pyright and TypeScript models contain explicit Bazel-owned source lists.
This keeps workspace diagnostics enabled without allowing language servers to
enumerate Bazel outputs, generated sources, or unrelated files.

This is editor-neutral. A pinned headless Neovim validates the metadata in CI,
and maintainers can exercise their real configuration with:

```sh
bazel run //e2e:probe_current_neovim -- \
  --workspace "$PWD/examples/polyglot"
```

See [the testing contract](docs/testing.md) and
[the design notes](docs/design.md) for the boundaries behind these commands.

## Developing bazel_devtools

The repository dogfoods its Python policy. Plain `bazel test //...` applies
Ruff lint, Ruff format-check, and BasedPyright to every repository-owned Python
target in addition to running the unit tests. Diagnostic fixtures are data
files rather than Python targets, so deliberately invalid examples stay outside
the self-check boundary.

## Status

This repository is pre-1.0. The supported platform is Linux x86_64 with Bazel
9 or newer. CI gates the minimum Bazel 9 patch and the repository-pinned Bazel;
new Bazel majors become release-gated after their first compatibility pass.
