# bazel_devtools

`bazel_devtools` is an opinionated, Bazel-first development-tooling layer for
Linux repositories containing Python, C++, and Rust. Bazel targets define the
source boundary: checks run as aspects during `bazel test`, and write-mode
formatting touches only source files owned by selected Bazel targets.

The default policy uses:

- Ruff for Python formatting and linting;
- BasedPyright in all mode for Python type checking;
- clang-format and clang-tidy for C and C++;
- rustfmt, Clippy, and rust-analyzer for Rust;
- target-graph discovery, with generated and external files excluded by default;
- editor-owned language-server binaries with Bazel-generated project metadata.

Lint and type-check defaults start strict: Ruff enables every stable rule,
BasedPyright uses `all`, clang-tidy starts from every check, and Clippy enables
`all`, `pedantic`, and `nursery` with warnings denied. clang-tidy excludes
platform/runtime policies (Fuchsia, LLVM libc, and Zircon) plus diagnostics
whose result depends on Bazel's sandbox path. Clippy's `cargo` group is excluded
because it invokes Cargo metadata and does not describe a Bazel-native build.
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
bazel run @bazel_devtools//tools:setup -- plan
bazel run @bazel_devtools//tools:setup -- init
bazel test //...
bazel run //:install-hooks
bazel run @bazel_devtools//tools:format -- //...
bazel run //:ide-sync
```

`setup plan` is read-only with respect to repository configuration and setup
state. It reports every file or block that initialization would add and exits
with status 2 when an existing policy needs an explicit migration. Setup will
not append duplicate clang-format, clang-tidy, or rustfmt policy keys, and it
will not silently bypass existing Ruff or Pyright configuration locations.
Repositories that relied on Bazel synthesizing `__init__.py` files must add
real files to the appropriate Python targets before adopting the generated
configuration.

Commit the files created by `setup init`. Ruff and BasedPyright use native
configuration inheritance, so repository overrides belong in `.ruff.toml` and
`basedpyright.json`. Files that cannot inherit contain narrowly scoped markers
such as:

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
| Ruff or clang-tidy lint | `no-lint` |
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

The generated GitHub workflow runs for pull requests and pushes to `master`,
uses read-only permissions, pins Actions by full commit, avoids saving caches
from pull requests, and cancels superseded runs. Repositories with another
primary branch should edit the branch filter; setup records that as a local
override and preserves it during upgrades unless the upstream template also
changes.

## Upgrade

Update the `bazel_dep` or override, then run:

```sh
bazel run @bazel_devtools//tools:setup -- upgrade
bazel run @bazel_devtools//tools:setup -- doctor
bazel test //...
```

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
- `rust-project.json` for rust-analyzer.

The Pyright model contains an explicit `include` list of Bazel-owned `.py` and
`.pyi` source files. This keeps workspace diagnostics enabled without allowing
BasedPyright to enumerate Bazel outputs, generated sources, or unrelated files.

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
