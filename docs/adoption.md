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
bazel run @bazel_devtools//tools:setup -- plan
```

The command does not write bazel_devtools configuration or state. A successful
plan lists files as `would create` or `would update` and exits with status 0.
An adoption issue is printed under `setup plan requires review` and exits with
status 2. `setup init` performs the same preflight and refuses to make partial
changes while those issues remain.

After resolving the plan:

```sh
bazel run @bazel_devtools//tools:setup -- init
bazel run @bazel_devtools//tools:setup -- doctor
bazel test //...
bazel run //:install-hooks
```

Commit the installed configuration and `.bazel_devtools/state.json`.
The hook installation is intentionally local Git state and is not committed.

## Migrate existing policy

Setup requires an explicit decision when its normal entry point would bypass an
existing policy:

- Move settings from `ruff.toml` or `[tool.ruff]` in `pyproject.toml` into
  `.ruff.toml`, retaining `extend = ".bazel_devtools/ruff.toml"`.
- Move settings from `basedpyrightconfig.json`, `pyrightconfig.json`, or
  Pyright sections in `pyproject.toml` into `basedpyright.json`, retaining
  `"extends": ".bazel_devtools/basedpyright.json"`. `pyrightconfig.json` is
  generated editor metadata after adoption.
- For an existing `.clang-format`, `.clang-tidy`, or `rustfmt.toml`, move the
  file aside, run setup, and merge intentional overrides into the generated
  managed block. Keep the original file available for review until the first
  clean test run.
- Reconcile existing `toolchains_llvm` or `hedron_compile_commands` module
  declarations with the generated `ide-dependencies` block. Also resolve root
  targets named `format`, `ide-sync`, `install-hooks`, or `pre-commit`, and any
  files already occupying `tools/bazel_devtools/`, before initialization.
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

## Presubmit behavior

The generated pre-commit hook runs all Bazel-owned checks against the staged
snapshot and does not rewrite or stage files. This is deliberate: automatic
formatting during a commit is unsafe when a file is only partially staged.
Repair formatting with `bazel run //:format`, inspect the changes, and retry
the commit. `git commit --no-verify` remains the standard emergency bypass;
the generated GitHub workflow still enforces the same command on pull requests.

The workflow assumes `master` is the primary branch. Change its push filter if
needed. Both presubmit files are managed as whole files because neither format
has a native inheritance mechanism. Local edits are preserved; if a later
bazel_devtools release also changes the template, `setup upgrade` emits a patch
for explicit reconciliation.
