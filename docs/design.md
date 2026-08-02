# Design contracts

`bazel_devtools` separates policy, target discovery, write-mode tools, and
editor metadata so each layer has one source of truth.

## Source ownership

Bazel's configured target graph is authoritative. Check aspects inspect direct
repository sources owned by supported rules. The formatter queries `srcs`,
`hdrs`, and `textual_hdrs` from selected targets and passes an explicit file
list to the pinned tools. Generated files, external repositories, and loose
files that are not owned by targets are excluded.

This makes `bazel run //:format -- //some/package/...` reviewable and prevents a
repository-wide filesystem walk from rewriting vendored or incidental files.

## Policy and overrides

Tool-native inheritance is preferred. `.bazel_devtools/ruff.toml` and
`.bazel_devtools/basedpyright.json` contain managed defaults; the root configs
are user-owned and extend them. Tools without useful inheritance receive a
small managed block in their normal configuration file.

The baseline is strict and explicit: enable the broadest coherent stable rule
set, then record exceptions by rule name with a reason. Avoid preview rules and
internally contradictory aggregate groups so a routine tool upgrade does not
silently redefine repository policy. The initial global exception is
BasedPyright's `reportUnusedCallResult`. Ruff exceptions document intentional
project choices around assertions, CLI output, Bazel subprocesses, generated
XML, namespace packages, and repository-level licensing; formatter-conflicting
rules are compatibility exclusions rather than style choices.

clang-tidy starts with its wildcard rule set but excludes checks that encode a
specific operating-system or runtime implementation policy, and checks whose
answer changes with Bazel's sandbox path. Clippy enables its general-purpose
strict groups but not `cargo`: that group shells out to Cargo metadata and is
therefore neither hermetic nor meaningful for a Bazel-native crate graph.

Python uses Bazel's explicit package-init mode. This keeps importability tied
to source files in the target graph, preserves intentional namespace packages,
and avoids analysis-time generation of empty `__init__.py` files.

Target tags are part of the public API. Repository-wide changes belong in the
user-owned config. A target-specific incompatibility belongs in the narrowest
supported opt-out tag.

## Upgrade state

`.bazel_devtools/state.json` stores the exact installed baseline and its digest
for every managed file or block. Upgrade is a three-way decision:

1. current equals old baseline: install the new baseline;
2. current equals new baseline: accept a manually resolved update;
3. both current and upstream changed: preserve current and emit a patch.

The overall installed version advances only after all conflicts are resolved.
State ownership, block identity, and baseline digests are validated before an
upgrade writes files. Files outside managed blocks are never rewritten.

First-time installation has a separate read-only planning phase. It reports
the exact create/update set and blocks ambiguous brownfield adoption before any
configuration or state is written. Existing Python policy must join the
managed inheritance chain explicitly. Existing clang-format, clang-tidy, and
rustfmt policy must be reviewed before setup introduces its managed block, so
initialization cannot create duplicate configuration keys accidentally.

## Presubmit boundary

Local pre-commit and hosted CI intentionally invoke the same plain `bazel test
//...` contract. The hook is check-only: it relies on pre-commit's staged-file
isolation but never formats or stages source files. Write-mode formatting stays
an explicit reviewable command. Hook installation is also explicit because
setup configuration belongs in the repository while `.git` is developer-local
state. The installer owns only hooks carrying its marker and refuses to replace
an unrelated hook.

Pre-commit is hash-pinned through the repository's Bazel Python dependency
graph. The installed hook rebuilds and resolves that executable before running
it, rather than embedding an output-tree path that `bazel clean` could remove.
The GitHub workflow is a managed whole file, uses minimal permissions, and pins
third-party Actions to immutable commits. Downstream changes such as a
different primary branch participate in the same three-way upgrade policy as
other managed files.

## Build and editor versions

CI tools are pinned through Bazel. Editors may use their own language-server
versions because the handoff formats (`pyrightconfig.json`,
`compile_commands.json`, and `rust-project.json`) are stable data contracts.
The Pyright handoff enumerates Bazel-owned source files explicitly; import
search paths remain separate in `extraPaths` and do not broaden the analysis
set.
When an editor upgrade exposes a mismatch, fix the generated model or document
a compatibility bound; do not silently depend on an editor's workspace scan.

## Deliberate limitations

- The initial release installs all three language integrations. Selecting a
  language subset is the next configuration feature, but must preserve the
  same stateful upgrade guarantees.
- IDE metadata synchronization is explicit rather than a background watcher.
- The real-user Neovim probe is a maintainer acceptance test because personal
  configuration cannot be hermetically reproduced in hosted CI.
