# Adopting bazel_devtools

## Pin the dependency

Use a local checkout while evaluating `bazel_devtools`:

```starlark
bazel_dep(name = "bazel_devtools", version = "0.1.0")
local_path_override(
    module_name = "bazel_devtools",
    path = "../bazel_devtools",
)
```

A local path is intentionally machine-specific. For shared development and CI,
pin a full Git commit rather than a branch:

```starlark
bazel_dep(name = "bazel_devtools", version = "0.1.0")
git_override(
    module_name = "bazel_devtools",
    commit = "<full-commit-sha>",
    remote = "https://github.com/agoessling/bazel_devtools.git",
)
```

Replace the commit placeholder with a published full SHA. Once the module is
available from the Bazel Central Registry, remove the override and keep the
released version in `bazel_dep`.

## Preview first-time setup

Run setup from a clean branch or worktree:

```sh
bazel run @bazel_devtools//tools:setup -- plan --language python --language cpp
```

The command does not write bazel_devtools configuration or state. A successful
plan lists files as `would create` or `would update` and exits with status 0.
An adoption issue is printed under `setup plan requires review` and exits with
status 2. `setup init` performs the same preflight and refuses to make partial
changes while those issues remain.

Repeat `--language` to select any combination of `python`, `cpp`, `rust`, and
`typescript`. Omitting it selects all four. Planning is read-only, so pass the
same language arguments to `init` after reviewing the plan.

After resolving the plan:

```sh
bazel run @bazel_devtools//tools:setup -- init --language python --language cpp
bazel run @bazel_devtools//tools:setup -- doctor
bazel test //...
bazel run //:install-hooks
```

Commit the installed configuration and `.bazel_devtools/state.json`.
The hook installation is intentionally local Git state and is not committed.
The language selection is committed in that state and reused by formatting,
IDE synchronization, `doctor`, and later upgrades. Change it with `setup
upgrade` plus the new complete set of repeated `--language` arguments.
If upgrade reports a conflict, it keeps the previous selection and generated
configuration active; resolve the reported patch and rerun the same command.
Enabling a language also stops before writing if its policy or toolchain paths
contain unmanaged declarations; reconcile them using the same migration rules
as first-time setup, then rerun upgrade.

## Migrate existing policy

Setup requires an explicit decision when its normal entry point would bypass an
existing policy:

- Move settings from `ruff.toml` or `[tool.ruff]` in `pyproject.toml` into
  `.ruff.toml`, retaining `extend = ".bazel_devtools/ruff.toml"`.
- Move settings from `basedpyrightconfig.json`, `pyrightconfig.json`, or
  Pyright sections in `pyproject.toml` into `basedpyright.json`, retaining
  `"extends": ".bazel_devtools/basedpyright.json"`. `pyrightconfig.json` is
  generated editor metadata after adoption.
- Make an existing `biome.json` extend
  `./.bazel_devtools/biome.json`. If the repository uses `biome.jsonc`, choose
  one root filename and consolidate the policy before setup so Biome has one
  unambiguous configuration chain.
- Make an existing `tsconfig.json` extend
  `./.bazel_devtools/tsconfig.json`; project and package configs may then extend
  the root config normally.
- For an existing `.clang-format`, `.clang-tidy`, or `rustfmt.toml`, move the
  file aside, run setup, and merge intentional overrides into the generated
  managed block. Keep the original file available for review until the first
  clean test run.
- Reconcile existing `toolchains_llvm` or `hedron_compile_commands` module
  declarations with the generated `ide-dependencies` block. Do the same for
  existing `aspect_rules_js` or `aspect_rules_ts` declarations when enabling
  TypeScript. Also resolve root targets named `format`, `ide-sync`,
  `install-hooks`, `pre-commit`, `tsconfig_base`, or `tsconfig`, and any files
  already occupying `tools/bazel_devtools/`, before initialization. TypeScript
  setup owns the latter two targets; an upgrade stops without writing if
  hand-written versions must be removed or renamed first.
- If `.pre-commit-config.yaml` already exists, merge the generated local hook
  with id `bazel-devtools-check`. Setup then preserves the whole file as a
  local override. If `.github/workflows/bazel-devtools.yml` already exists,
  move or reconcile that dedicated workflow before setup claims the path.
- `bazel run //:install-hooks` refuses to overwrite an existing unmanaged
  `.git/hooks/pre-commit`. Keep that hook and invoke `bazel test //...` from it,
  or explicitly replace it after reviewing its behavior. It also refuses a
  configured `core.hooksPath`; integrate the generated command into that hook
  directory manually.

Rerun `setup plan` after migration. It is safe only when each checker has one
unambiguous effective policy.

## Add a TypeScript or React target

The `typescript` integration pins `rules_js`, `rules_ts`, TypeScript, and Biome.
It deliberately does not generate application dependencies. Keep the
repository's `package.json`, `pnpm-lock.yaml`, and npm translation under normal
application ownership. Setup generates `//:tsconfig_base` and `//:tsconfig` as
public `ts_config` targets. Keeping these rules in the root package lets
`rules_ts` copy each config to the matching output-tree path. A package-level
strict typecheck config should extend the root file and declare the matching
provider dependency:

```starlark
ts_config(
    name = "tsconfig",
    src = "tsconfig.json",
    deps = ["//:tsconfig"],
)

ts_project(
    name = "app",
    # ...
    no_emit = True,
    tsconfig = ":tsconfig",
)
```

That package's `tsconfig.json` can use `"extends": "../tsconfig.json"`. The
physical `extends` chain serves editors and TypeScript, while the `deps` chain
gives Bazel every config file inside the action sandbox. The checked-in
`examples/polyglot/typescript` package is a typechecked React/TSX configuration
reference; it is intentionally not bundled or executed.

Keep a bundler's transform config separate from this inherited typecheck
graph. In `rules_esbuild` 0.27, the `tsconfig` attribute stages only one
physical config file and does not consume the `TsConfigInfo` dependency graph.
Passing the inherited package config can therefore omit its base file in the
transform action. For TSX that can also discard the inherited `react-jsx`
setting, select the classic JSX transform, and fail at runtime with `React is
not defined`.

Use a standalone file with every transform-relevant option inline and no
`extends`, for example:

```json
{
  "compilerOptions": {
    "jsx": "react-jsx",
    "target": "ES2022"
  }
}
```

Expose it as a separate `ts_config` such as `:tsconfig_esbuild`, and point the
`rules_esbuild` target's `tsconfig` attribute at that label. Continue using the
inherited `:tsconfig` above for strict `ts_project` type checks. Re-evaluate
this boundary when upgrading `rules_esbuild`; devtools does not own or pin the
application bundler.

This split keeps framework upgrades independent of tooling-policy upgrades:
setup can update strict checks without selecting a React version or replacing
the application's package-manager lockfile.

## Presubmit behavior

The generated pre-commit hook runs all Bazel-owned checks against the staged
snapshot and does not rewrite or stage files. This is deliberate: automatic
formatting during a commit is unsafe when a file is only partially staged.
Repair formatting with `bazel run //:format`, inspect the changes, and retry
the commit. `git commit --no-verify` remains the standard emergency bypass;
the generated GitHub workflow still enforces the same command on pull requests.

The workflow runs for pull requests and pushes to every branch, so setup does
not need to guess the repository's primary branch. Both presubmit files are
managed as whole files because neither format has a native inheritance
mechanism. Local edits are preserved; if a later bazel_devtools release also
changes the template, `setup upgrade` emits a patch for explicit
reconciliation.
