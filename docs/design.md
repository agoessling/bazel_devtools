# Design contracts

`bazel_devtools` separates policy, target discovery, write-mode tools, and
editor metadata so each layer has one source of truth.

## Source ownership

Bazel's configured target graph is authoritative. Check aspects inspect direct
repository sources owned by supported rules. The formatter queries `srcs`,
`hdrs`, and `textual_hdrs` from selected targets and passes an explicit file
list to the pinned tools. Generated files, external repositories, and loose
files that are not owned by targets are excluded.

Ruff still checks only a target's direct Python sources, but its sandbox also
contains the `PyInfo` transitive source graph. Ruff's import sorter consults the
filesystem to distinguish first-party modules, so this analysis context keeps
hermetic import classification consistent without widening the checked source
boundary.

clang-tidy reconstructs the target's effective compiler arguments from
`CcInfo` and writes a per-source compilation database whose driver is Bazel's
configured compiler. Preserving the driver identity is essential for cross
toolchains because Clang derives the target and GCC system-header layout from
names such as `arm-none-eabi-gcc`. External-repository include roots are marked
as system paths. A Bazel-owner manifest filters policy diagnostics whose
primary location is an external header, including analyzer diagnostics with a
note in first-party code; compiler errors remain fatal because they invalidate
the analysis.

Target-local defines must remain local to downstream compilation but must not
disappear from the lint action. The pinned upstream aspect loses them when it
merges `implementation_deps`, so bazel_devtools carries those defines
separately through its vendored adapter. A C++ runfiles fixture exercises
`BAZEL_CURRENT_REPOSITORY` with a non-empty implementation dependency and
proves that ordinary compilation and clang-tidy see the same definition. The
vendored source and removal conditions live under
`third_party/aspect_rules_lint/`.

C and C++ check aspects derive their propagation attributes from each rule's
actual first-party, non-tool label edges. This includes custom attributes with
configuration transitions, not only conventional `deps`, so a source compiled
only in a transitioned configuration remains in the same Bazel-owned check
boundary exposed to IDE metadata. Propagation stops at external repositories;
the public aspect factories accept an explicit `attr_aspects` override for
consumers with a narrower graph policy.

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

clang-tidy begins with `-*` and then enables `clang-diagnostic`,
`clang-analyzer`, `bugprone`, `cert`, `concurrency`, `cppcoreguidelines`,
`google`, `misc`, `modernize`, `performance`, `portability`, and `readability`.
This keeps vendor-specific families out while retaining strict correctness,
security, portability, performance, and Google C++ guidance. The
`clang-diagnostic-*` selector does not turn on compiler warnings; it reports
only compiler diagnostics already enabled by the target's build flags. The one
compiler-diagnostic exclusion is `builtin-macro-redefined`: Bazel's host
toolchain deliberately defines `__DATE__`, `__TIME__`, and `__TIMESTAMP__` to
deterministic values before clang-tidy sees the compiler arguments. This is a
build-system reproducibility artifact outside project source control; every
other enabled compiler diagnostic remains an error.

The managed exclusions have narrow purposes:

- Fuchsia, macOS, WebKit, MPI, GCDAntipattern, and padding analyzer checks do
  not describe the supported Linux C++ boundary or impose target ABI layout;
- do-while, ownership annotation, recursion, constant built-in-array indexing,
  and non-private field checks make architectural choices that are not
  universally correct; magic-number and function-size checks are too noisy;
- Google Objective-C, TODO, and function-size checks are outside the C++ policy;
- `cppcoreguidelines-pro-bounds-avoid-unchecked-container-access` produces
  pervasive findings for ordinary indexed access even where size or other
  invariants are established. C++20 `std::span` has no `.at()` alternative,
  and forcing redundant checks or suppressions through performance-sensitive
  code adds noise without proportional defect detection;
- selected modernization rewrites change APIs or expression style without
  finding a defect, including mandatory trailing return types and the
  `readability-math-missing-parentheses` requirement for redundant parentheses
  around conventional mathematical operator precedence;
- enum-size and restricted-system-include checks impose ABI or deployment
  policy; and identifier length, automatic static-member conversion, and
  function-size checks are subjective design constraints.

Alias exclusions are paired where selected families expose the same check:
both C++ Core Guidelines and readability magic-number names, both C++ Core
Guidelines and misc public-member names, both Google and readability
function-size names, and both modernize and C++ Core Guidelines macro-to-enum
names are disabled. Conversely, strict diagnostics such as swappable
parameters, unchecked optionals, include cleaning, cognitive complexity,
C-array and pointer arithmetic, non-const globals, narrowing conversions, and
special-member rules intentionally remain active.

`e2e/testdata/cpp/clang_tidy_checks_22_1_6.txt` records the exact registered
check names resolved from the human-readable family policy. Integration tests
compare `--list-checks` against that evidence and fail when a toolchain upgrade
adds or removes a family member, requiring explicit review before updating the
snapshot. Clippy enables its general-purpose strict groups but not `cargo`:
that group shells out to Cargo metadata and is therefore neither hermetic nor
meaningful for a Bazel-native crate graph.

C++ formatting follows Google style with a 100-column limit and explicit right
pointer alignment (`Type *value`, `const Type &value`). clang-tidy applies the
Google trailing-underscore convention only to private and protected non-static
member data. LLVM classifies static const and constexpr members separately
as class constants, so names such as `kFrameRate` remain valid; public
struct-style fields enforce lower snake case while remaining unsuffixed.

Python uses Bazel's explicit package-init mode. This keeps importability tied
to source files in the target graph, preserves intentional namespace packages,
and avoids analysis-time generation of empty `__init__.py` files.

Target tags are part of the public API. Repository-wide changes belong in the
user-owned config. A target-specific incompatibility belongs in the narrowest
supported opt-out tag.

## Language selection

Setup renders one coherent template set from an explicit combination of
Python, C++, and Rust support. The canonical selection is persisted in setup
state and drives check aspects, formatter targets, policy files, toolchain
configuration, write-mode target discovery, and IDE synchronization. A
language-specific public `.bzl` facade avoids loading another language's rule
set merely to construct the selected aspects.

Changing the selection uses the normal upgrade state machine. Shared generated
blocks receive a three-way update, newly selected policy is adopted, and
deselected managed files are left on disk while setup retires ownership. This
preserves local work without leaving the deselected tools in the active Bazel
graph. The C++ module-dependency block remains managed with an empty body when
C++ is deselected, allowing setup to remove LLVM and compile-command tooling
without deleting user-owned `MODULE.bazel` content. A conflicted language
change does not modify generated configuration or publish the new selection;
the complete transition is retried after conflict resolution.
Newly enabled language policy receives the same brownfield collision preflight
as first-time setup. Existing user policy or toolchain declarations must be
explicitly reconciled before setup writes any part of the transition.

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
third-party Actions to immutable commits. It runs for pushes to every branch so
the generated configuration does not need repository-specific primary-branch
state.

Wildcard commands use `--build_manual_tests`. Manual tests therefore remain in
the build and aspect-check boundary but are not executed by `bazel test //...`.
Manual non-test targets keep Bazel's standard exclusion, which preserves the
safety boundary around explicitly invoked actions such as hardware flashing.

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

- A language subset prunes generated checks, formatter targets, and toolchain
  configuration, but `bazel_devtools` remains one Bazel module whose dependency
  resolution includes rule-set metadata for every supported integration.
- IDE metadata synchronization is explicit rather than a background watcher.
- The real-user Neovim probe is a maintainer acceptance test because personal
  configuration cannot be hermetically reproduced in hosted CI.
