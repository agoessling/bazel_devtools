from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import TypedDict, final, override

from tools.setup_lib import (
    SetupError,
    append_block,
    doctor,
    initialize,
    parse_blocks,
    plan_initialize,
    replace_block,
    upgrade,
)
from tools.templates import TEMPLATES, Ownership, Template


class _BasedPyrightPolicy(TypedDict):
    typeCheckingMode: str
    reportUnusedCallResult: str


class _StateEntry(TypedDict):
    base: str


class _State(TypedDict):
    installed_version: str | None
    entries: dict[str, _StateEntry]


def _load_policy(path: Path) -> _BasedPyrightPolicy:
    return json.loads(path.read_text())  # pyright: ignore[reportAny]


def _load_state(path: Path) -> _State:
    return json.loads(path.read_text())  # pyright: ignore[reportAny]


class ManagedBlockTest(unittest.TestCase):
    def test_round_trip_preserves_outside_bytes(self) -> None:
        original = "before\n\nafter\n"
        installed = append_block(original, "example", "old = true\n")
        block = parse_blocks(installed)["example"]
        updated = replace_block(installed, block, "new = true\n")

        self.assertTrue(updated.startswith(original))
        self.assertIn("new = true", updated)
        self.assertNotIn("old = true", updated)

    def test_rejects_duplicate_blocks(self) -> None:
        content = append_block("", "same", "one\n")
        content += append_block("", "same", "two\n")
        with self.assertRaisesRegex(SetupError, "duplicate"):
            parse_blocks(content)

    def test_rejects_unbalanced_blocks(self) -> None:
        with self.assertRaisesRegex(SetupError, "no end"):
            parse_blocks("# ##BAZEL_DEVTOOLS_MANAGED_BEGIN:broken##\n")

    def test_rejects_mismatched_blocks(self) -> None:
        with self.assertRaisesRegex(SetupError, "ended by marker"):
            parse_blocks(
                """# ##BAZEL_DEVTOOLS_MANAGED_BEGIN:first##
# ##BAZEL_DEVTOOLS_MANAGED_END:second##
"""
            )


@final
class SetupLifecycleTest(unittest.TestCase):
    temp: tempfile.TemporaryDirectory[str]
    workspace: Path

    def __init__(self, method_name: str = "runTest") -> None:
        super().__init__(method_name)
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name)
        (self.workspace / "MODULE.bazel").write_text('module(name = "fixture")\n', encoding="utf-8")

    @override
    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_init_is_idempotent_and_preserves_existing_user_file(self) -> None:
        (self.workspace / "user.toml").write_text("mine = true\n", encoding="utf-8")
        templates = (
            Template("managed.txt", "base\n", Ownership.MANAGED_FILE),
            Template("user.toml", "default\n", Ownership.CREATE_ONLY),
            Template("MODULE.bazel", "setting = True\n", Ownership.MANAGED_BLOCK, "setting"),
        )

        first = initialize(self.workspace, templates)
        snapshot = {
            path.relative_to(self.workspace): path.read_bytes()
            for path in self.workspace.rglob("*")
            if path.is_file()
        }
        second = initialize(self.workspace, templates)

        self.assertIn("managed.txt", first.created)
        self.assertEqual([], second.created)
        self.assertEqual([], second.changed)
        self.assertEqual("mine = true\n", (self.workspace / "user.toml").read_text())
        self.assertEqual(
            snapshot,
            {
                path.relative_to(self.workspace): path.read_bytes()
                for path in self.workspace.rglob("*")
                if path.is_file()
            },
        )
        doctor(self.workspace, templates)

    def test_default_templates_bootstrap_a_structurally_valid_repository(self) -> None:
        result = initialize(self.workspace)

        self.assertIn(".bazel_devtools/ruff.toml", result.created)
        self.assertIn(
            'select = ["ALL"]',
            (self.workspace / ".bazel_devtools/ruff.toml").read_text(),
        )
        self.assertIn(
            '"S101"',
            (self.workspace / ".bazel_devtools/ruff.toml").read_text(),
        )
        basedpyright = _load_policy(self.workspace / ".bazel_devtools/basedpyright.json")
        self.assertEqual("all", basedpyright["typeCheckingMode"])
        self.assertEqual("none", basedpyright["reportUnusedCallResult"])
        clang_tidy = (self.workspace / ".clang-tidy").read_text()
        self.assertIn("Checks: >-", clang_tidy)
        self.assertIn("-fuchsia-*", clang_tidy)
        self.assertIn("-llvm-header-guard", clang_tidy)
        self.assertIn(
            "##BAZEL_DEVTOOLS_MANAGED_BEGIN:checks##",
            (self.workspace / ".bazelrc.bazel_devtools").read_text(),
        )
        self.assertIn(
            "common --incompatible_default_to_explicit_init_py",
            (self.workspace / ".bazelrc.bazel_devtools").read_text(),
        )
        self.assertIn(
            "-Dclippy::pedantic",
            (self.workspace / ".bazelrc.bazel_devtools").read_text(),
        )
        self.assertNotIn(
            "-Dclippy::cargo",
            (self.workspace / ".bazelrc.bazel_devtools").read_text(),
        )
        self.assertIn(
            'actual = "@bazel_devtools//tools:format"',
            (self.workspace / "BUILD.bazel").read_text(),
        )
        self.assertIn(
            "id: bazel-devtools-check",
            (self.workspace / ".pre-commit-config.yaml").read_text(),
        )
        workflow = (self.workspace / ".github/workflows/bazel-devtools.yml").read_text()
        self.assertIn("run: bazel test //... --test_output=errors", workflow)
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn(
            'actual = "@bazel_devtools//tools:install-hooks"',
            (self.workspace / "BUILD.bazel").read_text(),
        )
        doctor(self.workspace)

    def test_plan_reports_init_without_modifying_the_workspace(self) -> None:
        snapshot = {
            path.relative_to(self.workspace): path.read_bytes()
            for path in self.workspace.rglob("*")
            if path.is_file()
        }

        result = plan_initialize(self.workspace)

        self.assertIn(".bazel_devtools/ruff.toml", result.created)
        self.assertIn("MODULE.bazel", result.changed)
        self.assertEqual([], result.conflicts)
        self.assertEqual(
            snapshot,
            {
                path.relative_to(self.workspace): path.read_bytes()
                for path in self.workspace.rglob("*")
                if path.is_file()
            },
        )

    def test_brownfield_policy_file_blocks_plan_and_init_without_writes(self) -> None:
        clang_tidy = self.workspace / ".clang-tidy"
        clang_tidy.write_text("Checks: 'modernize-*'\n", encoding="utf-8")

        result = plan_initialize(self.workspace)

        self.assertTrue(any("existing .clang-tidy" in issue for issue in result.conflicts))
        with self.assertRaisesRegex(SetupError, "existing \\.clang-tidy"):
            initialize(self.workspace)
        self.assertEqual("Checks: 'modernize-*'\n", clang_tidy.read_text())
        self.assertFalse((self.workspace / ".bazel_devtools/state.json").exists())

    def test_brownfield_python_policy_locations_require_explicit_migration(self) -> None:
        (self.workspace / "pyproject.toml").write_text(
            "[tool.ruff]\nline-length = 88\n[tool.pyright]\ntypeCheckingMode = 'strict'\n",
            encoding="utf-8",
        )
        (self.workspace / "ruff.toml").write_text("line-length = 88\n", encoding="utf-8")
        (self.workspace / "basedpyrightconfig.json").write_text("{}\n", encoding="utf-8")

        result = plan_initialize(self.workspace)

        self.assertTrue(any("pyproject.toml" in issue for issue in result.conflicts))
        self.assertTrue(any("ruff.toml" in issue for issue in result.conflicts))
        self.assertTrue(any("basedpyrightconfig.json" in issue for issue in result.conflicts))

    def test_brownfield_bazel_graph_collisions_require_explicit_migration(self) -> None:
        (self.workspace / "MODULE.bazel").write_text(
            'module(name = "fixture")\nbazel_dep(name = "toolchains_llvm", version = "1.8.0")\n',
            encoding="utf-8",
        )
        (self.workspace / "BUILD.bazel").write_text(
            'filegroup(name = "format")\n',
            encoding="utf-8",
        )
        tools = self.workspace / "tools/bazel_devtools"
        tools.mkdir(parents=True)
        (tools / "aspects.bzl").write_text("custom = True\n", encoding="utf-8")

        result = plan_initialize(self.workspace)

        self.assertTrue(any("toolchains_llvm" in issue for issue in result.conflicts))
        self.assertTrue(any("root BUILD targets" in issue for issue in result.conflicts))
        self.assertTrue(any("aspects.bzl" in issue for issue in result.conflicts))

    def test_brownfield_presubmit_files_require_explicit_migration(self) -> None:
        (self.workspace / ".pre-commit-config.yaml").write_text(
            "repos: []\n",
            encoding="utf-8",
        )
        workflow = self.workspace / ".github/workflows/bazel-devtools.yml"
        workflow.parent.mkdir(parents=True)
        workflow.write_text("name: Existing\n", encoding="utf-8")

        result = plan_initialize(self.workspace)

        self.assertTrue(any("bazel-devtools-check" in issue for issue in result.conflicts))
        self.assertTrue(any("managed CI path" in issue for issue in result.conflicts))
        with self.assertRaisesRegex(SetupError, "presubmit|pre-commit"):
            initialize(self.workspace)

    def test_doctor_rejects_removed_presubmit_hook(self) -> None:
        initialize(self.workspace)
        (self.workspace / ".pre-commit-config.yaml").write_text(
            "repos: []\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(SetupError, "missing the bazel-devtools-check hook"):
            doctor(self.workspace)

    def test_upgrade_blocks_conflicting_new_presubmit_files_before_writes(self) -> None:
        old = tuple(
            template
            for template in TEMPLATES
            if template.path
            not in {".pre-commit-config.yaml", ".github/workflows/bazel-devtools.yml"}
        )
        initialize(self.workspace, old)
        (self.workspace / ".pre-commit-config.yaml").write_text(
            "repos: []\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(SetupError, "presubmit adoption"):
            upgrade(self.workspace)

        self.assertFalse((self.workspace / ".github/workflows/bazel-devtools.yml").exists())

    def test_compatible_existing_python_entry_points_are_preserved(self) -> None:
        (self.workspace / ".ruff.toml").write_text(
            'extend = ".bazel_devtools/ruff.toml"\n\n[lint]\nignore = ["D100"]\n',
            encoding="utf-8",
        )
        (self.workspace / "basedpyright.json").write_text(
            '{"extends": ".bazel_devtools/basedpyright.json", "strict": ["src"]}\n',
            encoding="utf-8",
        )
        (self.workspace / "pyrightconfig.json").write_text(
            '{"extends": "basedpyright.json", "extraPaths": []}\n',
            encoding="utf-8",
        )

        result = initialize(self.workspace)

        self.assertIn("preserved existing .ruff.toml", result.messages)
        self.assertIn("preserved existing basedpyright.json", result.messages)
        doctor(self.workspace)

    def test_upgrade_replaces_pristine_content_and_preserves_outside_block(
        self,
    ) -> None:
        old = (
            Template("managed.txt", "old\n", Ownership.MANAGED_FILE),
            Template("MODULE.bazel", "old = True\n", Ownership.MANAGED_BLOCK, "setting"),
        )
        new = (
            Template("managed.txt", "new\n", Ownership.MANAGED_FILE),
            Template("MODULE.bazel", "new = True\n", Ownership.MANAGED_BLOCK, "setting"),
        )
        initialize(self.workspace, old)
        module = self.workspace / "MODULE.bazel"
        module.write_text(module.read_text() + "# outside\n", encoding="utf-8")

        result = upgrade(self.workspace, new)

        self.assertEqual([], result.conflicts)
        self.assertEqual("new\n", (self.workspace / "managed.txt").read_text())
        self.assertIn("new = True", module.read_text())
        self.assertTrue(module.read_text().endswith("# outside\n"))

    def test_upgrade_writes_patch_for_modified_managed_content(self) -> None:
        old = (Template("managed.txt", "old\n", Ownership.MANAGED_FILE),)
        new = (Template("managed.txt", "new\n", Ownership.MANAGED_FILE),)
        initialize(self.workspace, old)
        (self.workspace / "managed.txt").write_text("local\n", encoding="utf-8")

        result = upgrade(self.workspace, new)

        self.assertEqual(["managed.txt"], result.conflicts)
        self.assertEqual("local\n", (self.workspace / "managed.txt").read_text())
        patches = list((self.workspace / ".bazel_devtools/updates").glob("*.patch"))
        self.assertEqual(1, len(patches))
        self.assertIn("+new", patches[0].read_text())

    def test_upgrade_accepts_a_manually_resolved_conflict(self) -> None:
        old = (
            Template("managed.txt", "old\n", Ownership.MANAGED_FILE),
            Template("MODULE.bazel", "old = True\n", Ownership.MANAGED_BLOCK, "setting"),
        )
        new = (
            Template("managed.txt", "new\n", Ownership.MANAGED_FILE),
            Template("MODULE.bazel", "new = True\n", Ownership.MANAGED_BLOCK, "setting"),
        )
        initialize(self.workspace, old)
        (self.workspace / "managed.txt").write_text("local\n", encoding="utf-8")
        module = self.workspace / "MODULE.bazel"
        module.write_text(
            module.read_text().replace("old = True", "local = True"),
            encoding="utf-8",
        )
        first = upgrade(self.workspace, new)
        self.assertEqual(["managed.txt", "MODULE.bazel:setting"], first.conflicts)

        (self.workspace / "managed.txt").write_text("new\n", encoding="utf-8")
        module.write_text(
            module.read_text().replace("local = True", "new = True"),
            encoding="utf-8",
        )
        second = upgrade(self.workspace, new)

        self.assertEqual([], second.conflicts)
        state = _load_state(self.workspace / ".bazel_devtools/state.json")
        self.assertEqual("new\n", state["entries"]["managed.txt"]["base"])
        self.assertEqual("new = True\n", state["entries"]["MODULE.bazel"]["base"])

    def test_upgrade_installs_templates_added_by_a_new_release(self) -> None:
        old = (Template("managed.txt", "old\n", Ownership.MANAGED_FILE),)
        new = (
            *old,
            Template("new-managed.txt", "managed\n", Ownership.MANAGED_FILE),
            Template("new-user.txt", "user default\n", Ownership.CREATE_ONLY),
            Template("MODULE.bazel", "new = True\n", Ownership.MANAGED_BLOCK, "new-setting"),
        )
        initialize(self.workspace, old)

        result = upgrade(self.workspace, new)

        self.assertEqual([], result.conflicts)
        self.assertEqual("managed\n", (self.workspace / "new-managed.txt").read_text())
        self.assertEqual("user default\n", (self.workspace / "new-user.txt").read_text())
        self.assertIn("new = True", (self.workspace / "MODULE.bazel").read_text())
        doctor(self.workspace, new)

    def test_upgrade_adopts_a_preexisting_new_template_as_an_override(self) -> None:
        old = (Template("managed.txt", "old\n", Ownership.MANAGED_FILE),)
        new = (*old, Template("new-managed.txt", "default\n", Ownership.MANAGED_FILE))
        initialize(self.workspace, old)
        (self.workspace / "new-managed.txt").write_text("local\n", encoding="utf-8")

        result = upgrade(self.workspace, new)

        self.assertIn("adopted existing managed file new-managed.txt", result.messages)
        self.assertEqual("local\n", (self.workspace / "new-managed.txt").read_text())
        health = doctor(self.workspace, new)
        self.assertIn("local override in new-managed.txt", health.messages)

    def test_conflict_does_not_claim_the_new_version(self) -> None:
        old = (Template("managed.txt", "old\n", Ownership.MANAGED_FILE),)
        new = (Template("managed.txt", "new\n", Ownership.MANAGED_FILE),)
        initialize(self.workspace, old)
        state_path = self.workspace / ".bazel_devtools/state.json"
        state = _load_state(state_path)
        state["installed_version"] = "previous"
        state_path.write_text(json.dumps(state), encoding="utf-8")
        (self.workspace / "managed.txt").write_text("local\n", encoding="utf-8")

        result = upgrade(self.workspace, new)

        self.assertTrue(result.conflicts)
        state = _load_state(state_path)
        self.assertEqual("previous", state["installed_version"])

    def test_upgrade_retires_ownership_without_deleting_the_file(self) -> None:
        old = (
            Template("kept.txt", "kept\n", Ownership.MANAGED_FILE),
            Template("retired.txt", "retired\n", Ownership.MANAGED_FILE),
        )
        new = (Template("kept.txt", "kept\n", Ownership.MANAGED_FILE),)
        initialize(self.workspace, old)

        result = upgrade(self.workspace, new)

        self.assertEqual("retired\n", (self.workspace / "retired.txt").read_text())
        self.assertIn("retired management of retired.txt; left file unchanged", result.messages)
        state = _load_state(self.workspace / ".bazel_devtools/state.json")
        self.assertNotIn("retired.txt", state["entries"])

    def test_rerunning_init_does_not_rebase_a_local_override(self) -> None:
        old = (Template("managed.txt", "old\n", Ownership.MANAGED_FILE),)
        new = (Template("managed.txt", "new\n", Ownership.MANAGED_FILE),)
        initialize(self.workspace, old)
        (self.workspace / "managed.txt").write_text("local\n", encoding="utf-8")

        initialize(self.workspace, new)
        result = upgrade(self.workspace, new)

        self.assertEqual(["managed.txt"], result.conflicts)
        state = _load_state(self.workspace / ".bazel_devtools/state.json")
        self.assertEqual("old\n", state["entries"]["managed.txt"]["base"])

    def test_state_contains_operational_baseline(self) -> None:
        templates = (Template("managed.txt", "base\n", Ownership.MANAGED_FILE),)
        initialize(self.workspace, templates)
        state = _load_state(self.workspace / ".bazel_devtools/state.json")
        self.assertEqual("base\n", state["entries"]["managed.txt"]["base"])

    def test_doctor_rejects_a_corrupt_saved_baseline(self) -> None:
        templates = (Template("managed.txt", "base\n", Ownership.MANAGED_FILE),)
        initialize(self.workspace, templates)
        state_path = self.workspace / ".bazel_devtools/state.json"
        state = _load_state(state_path)
        state["entries"]["managed.txt"]["base"] = "tampered\n"
        state_path.write_text(json.dumps(state), encoding="utf-8")

        with self.assertRaisesRegex(SetupError, "corrupt baseline digest"):
            doctor(self.workspace, templates)

    def test_invalid_templates_are_rejected_before_any_files_are_created(self) -> None:
        templates = (
            Template("created.txt", "created\n", Ownership.MANAGED_FILE),
            Template("../escaped.txt", "escaped\n", Ownership.MANAGED_FILE),
        )

        with self.assertRaisesRegex(SetupError, "unsafe template path"):
            initialize(self.workspace, templates)

        self.assertFalse((self.workspace / "created.txt").exists())

    def test_upgrade_preflight_rejects_missing_paths_before_writing(self) -> None:
        old = (
            Template("first.txt", "old\n", Ownership.MANAGED_FILE),
            Template("second.txt", "old\n", Ownership.MANAGED_FILE),
        )
        new = (
            Template("first.txt", "new\n", Ownership.MANAGED_FILE),
            Template("second.txt", "new\n", Ownership.MANAGED_FILE),
        )
        initialize(self.workspace, old)
        (self.workspace / "second.txt").unlink()

        with self.assertRaisesRegex(SetupError, "second.txt was deleted"):
            upgrade(self.workspace, new)

        self.assertEqual("old\n", (self.workspace / "first.txt").read_text())


if __name__ == "__main__":
    unittest.main()
