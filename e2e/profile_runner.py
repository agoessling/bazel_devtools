"""Profile representative bazel_devtools operations in a scratch consumer."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from getpass import getuser
from pathlib import Path
from typing import cast, final

from tools.bazel_wrapper import write_bazel_wrapper


@final
@dataclass(frozen=True)
class Operation:
    """One representative consumer operation."""

    name: str
    description: str
    arguments: tuple[str, ...]
    mutate_source: str | None = None


@final
@dataclass(frozen=True)
class Sample:
    """One measured command invocation."""

    operation: str
    mode: str
    iteration: int
    wall_seconds: float
    profile: str


_OPERATIONS = {
    operation.name: operation
    for operation in (
        Operation(
            name="setup_doctor",
            description="Validate installed setup policy and state.",
            arguments=("run", "@bazel_devtools//tools:setup", "--", "doctor"),
        ),
        Operation(
            name="typescript_source_query",
            description="Discover Bazel-owned TypeScript sources through the target graph.",
            arguments=(
                "query",
                "--noshow_progress",
                "--output=label",
                (
                    'kind("source file", filter(".*[.]tsx?$", labels(srcs, '
                    '((//...) except attr("tags", "no-ide", //...)))))'
                ),
            ),
        ),
        Operation(
            name="typescript_biome_format",
            description="Launch the pinned Biome formatter on explicit TypeScript sources.",
            arguments=(
                "run",
                "//tools/bazel_devtools:biome_cwd",
                "--",
                "format",
                "--write",
                "--config-path=biome.json",
                "--max-diagnostics=none",
                "typescript/greeting.ts",
                "typescript/greeting_view.tsx",
            ),
        ),
        Operation(
            name="typescript_format",
            description="Run end-to-end Bazel-owned TypeScript source formatting.",
            arguments=(
                "run",
                "//:format",
                "--",
                "--language",
                "typescript",
                "//typescript:greeting",
            ),
        ),
        Operation(
            name="typescript_ide_sync",
            description="Run TypeScript editor metadata synchronization.",
            arguments=("run", "//:ide-sync", "--", "--language", "typescript"),
        ),
        Operation(
            name="typescript_check",
            description="Measure a cached rules_ts typecheck and TypeScript check aspects.",
            arguments=("test", "//typescript:greeting_typecheck_test"),
        ),
        Operation(
            name="typescript_check_incremental",
            description="Re-run rules_ts and TypeScript check actions after a source edit.",
            arguments=("test", "//typescript:greeting_typecheck_test"),
            mutate_source="typescript/greeting.ts",
        ),
        Operation(
            name="check_all",
            description="Run the complete polyglot check contract.",
            arguments=("test", "//..."),
        ),
    )
}
_DEFAULT_OPERATIONS = tuple(name for name in _OPERATIONS if name != "check_all")


def _positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        msg = "must be at least 1"
        raise argparse.ArgumentTypeError(msg)
    return parsed


def _repository_cache() -> Path | None:
    override = os.environ.get("BAZEL_DEVTOOLS_REPOSITORY_CACHE")
    default = (
        Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
        / "bazel"
        / f"_bazel_{getuser()}"
        / "cache/repos/v1"
    )
    candidate = Path(override) if override else default
    return candidate.resolve() if candidate.is_dir() else None


def _summary_rows(samples: list[Sample]) -> list[dict[str, object]]:
    groups: dict[tuple[str, str], list[float]] = {}
    for sample in samples:
        groups.setdefault((sample.mode, sample.operation), []).append(sample.wall_seconds)
    rows: list[dict[str, object]] = []
    for (mode, operation), durations in groups.items():
        rows.append(
            {
                "mode": mode,
                "operation": operation,
                "runs": len(durations),
                "median_seconds": round(statistics.median(durations), 3),
                "mean_seconds": round(statistics.fmean(durations), 3),
                "min_seconds": round(min(durations), 3),
                "max_seconds": round(max(durations), 3),
            }
        )
    return rows


def _markdown_row(row: dict[str, object]) -> str:
    columns = (
        cast("str", row["mode"]),
        cast("str", row["operation"]),
        str(cast("int", row["runs"])),
        f"{cast('float', row['median_seconds']):.3f}",
        f"{cast('float', row['mean_seconds']):.3f}",
        f"{cast('float', row['min_seconds']):.3f}",
        f"{cast('float', row['max_seconds']):.3f}",
    )
    return f"| {' | '.join(columns)} |"


def _markdown(rows: list[dict[str, object]]) -> str:
    lines = [
        "# bazel_devtools profile summary",
        "",
        "| Mode | Operation | Runs | Median (s) | Mean (s) | Min (s) | Max (s) |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    lines.extend(_markdown_row(row) for row in rows)
    return "\n".join(lines) + "\n"


@final
class Profiler:
    """Own the scratch workspace, Bazel roots, and profile artifacts."""

    def __init__(self, *, full_profile: bool) -> None:
        source_workspace = Path(os.environ["BIT_WORKSPACE_DIR"]).resolve()
        source_repo = source_workspace.parents[1]
        temporary = Path(os.environ["TEST_TMPDIR"]).resolve()
        self.scratch_repo = temporary / "bazel_devtools-profile"
        if self.scratch_repo.exists():
            msg = f"profiling scratch repository already exists: {self.scratch_repo}"
            raise RuntimeError(msg)
        shutil.copytree(source_repo, self.scratch_repo)
        self.workspace = self.scratch_repo / "examples/polyglot"
        self.bazel = Path(os.environ["BIT_BAZEL_BINARY"]).resolve()
        self.temporary = temporary
        output = os.environ.get("TEST_UNDECLARED_OUTPUTS_DIR")
        self.results = Path(output).resolve() if output else temporary / "profile-results"
        self.results.mkdir(parents=True, exist_ok=True)
        self.repository_cache = _repository_cache()
        self.full_profile = full_profile
        self.source_baselines: dict[Path, str] = {}

    def _command_options(self) -> list[str]:
        options = ["--color=no", "--curses=no"]
        if self.repository_cache is not None:
            options.append(f"--repository_cache={self.repository_cache}")
        return options

    @staticmethod
    def _startup_options(output_root: Path) -> list[str]:
        # Pin output_base explicitly so a user bazelrc cannot redirect this
        # nested Bazel invocation back to the outer test server's output base.
        return [
            f"--output_user_root={output_root}",
            f"--output_base={output_root / 'output-base'}",
        ]

    def _environment(self, output_root: Path) -> dict[str, str]:
        startup = self._startup_options(output_root)
        command = self._command_options()
        wrapper_directory = self.temporary / "profile-bazel-wrappers" / output_root.name
        wrapper_directory.mkdir(parents=True, exist_ok=True)
        write_bazel_wrapper(
            wrapper_directory / "bazel",
            str(self.bazel),
            startup,
            command,
        )
        return {
            **os.environ,
            "BAZEL_DEVTOOLS_BAZEL_STARTUP_OPTIONS": " ".join(startup),
            "BAZEL_DEVTOOLS_BAZEL_COMMAND_OPTIONS": " ".join(command),
            "BAZEL_DEVTOOLS_WORKSPACE": str(self.workspace),
            "PATH": str(wrapper_directory) + os.pathsep + os.environ.get("PATH", ""),
        }

    def _mutate_source(self, operation: Operation, *, mode: str, iteration: int) -> None:
        if operation.mutate_source is None:
            return
        source = (self.workspace / operation.mutate_source).resolve()
        try:
            source.relative_to(self.workspace)
        except ValueError as error:
            msg = f"profiling mutation escaped the scratch workspace: {source}"
            raise RuntimeError(msg) from error
        if not source.is_file():
            msg = f"profiling mutation source does not exist: {source}"
            raise RuntimeError(msg)
        baseline = self.source_baselines.setdefault(
            source,
            source.read_text(encoding="utf-8"),
        )
        marker = f"// bazel_devtools profile sample: {mode}-{iteration}"
        source.write_text(baseline.rstrip() + "\n\n" + marker + "\n", encoding="utf-8")

    def run(
        self,
        operation: Operation,
        *,
        mode: str,
        iteration: int,
        output_root: Path,
        record: bool,
    ) -> Sample | None:
        profile = self.results / f"{mode}-{operation.name}-{iteration}.json.gz"
        command_options = self._command_options()
        if record:
            command_options.extend(
                (
                    f"--profile={profile}",
                    "--generate_json_trace_profile=yes",
                )
            )
            if self.full_profile:
                command_options.extend(("--noslim_profile", "--record_full_profiler_data"))
        command = [
            str(self.bazel),
            *self._startup_options(output_root),
            operation.arguments[0],
            *command_options,
            *operation.arguments[1:],
        ]
        if record:
            self._mutate_source(operation, mode=mode, iteration=iteration)
        label = f"{mode} {operation.name} #{iteration}"
        print(f">>> {label}", flush=True)
        started = time.perf_counter()
        result = subprocess.run(
            command,
            cwd=self.workspace,
            check=False,
            env=self._environment(output_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        elapsed = time.perf_counter() - started
        print(f"<<< {label}: exit {result.returncode} after {elapsed:.3f}s", flush=True)
        if result.returncode:
            output = result.stdout[-12000:]
            msg = f"profiling command failed: {' '.join(operation.arguments)}\n{output}"
            raise RuntimeError(msg)
        if not record:
            return None
        if not profile.is_file():
            msg = f"Bazel did not write the requested profile: {profile}"
            raise RuntimeError(msg)
        return Sample(
            operation=operation.name,
            mode=mode,
            iteration=iteration,
            wall_seconds=round(elapsed, 6),
            profile=profile.relative_to(self.results).as_posix(),
        )

    def write_summary(
        self,
        *,
        samples: list[Sample],
        operations: tuple[Operation, ...],
        mode: str,
        runs: int,
        warmups: int,
    ) -> str:
        rows = _summary_rows(samples)
        markdown = _markdown(rows)
        version = subprocess.run(
            [str(self.bazel), "--version"],
            check=False,
            capture_output=True,
            text=True,
        ).stdout.strip()
        payload: dict[str, object] = {
            "generated_at": datetime.now(tz=UTC).isoformat(),
            "bazel_version": version,
            "machine": {
                "platform": platform.platform(),
                "processor": platform.processor(),
                "cpu_count": os.cpu_count(),
            },
            "configuration": {
                "mode": mode,
                "runs": runs,
                "warmups": warmups,
                "full_profile": self.full_profile,
                "operations": [
                    {
                        "name": operation.name,
                        "description": operation.description,
                        "arguments": list(operation.arguments),
                        "mutate_source": operation.mutate_source,
                    }
                    for operation in operations
                ],
            },
            "summary": rows,
            "samples": [asdict(sample) for sample in samples],
        }
        (self.results / "summary.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (self.results / "summary.md").write_text(markdown, encoding="utf-8")
        return markdown


def _selected_operations(raw: list[str] | None) -> tuple[Operation, ...]:
    names = list(_DEFAULT_OPERATIONS) if raw is None else raw
    if "all" in names:
        if len(names) != 1:
            msg = "--operation=all cannot be combined with another operation"
            raise ValueError(msg)
        names = list(_OPERATIONS)
    return tuple(_OPERATIONS[name] for name in dict.fromkeys(names))


def _parse_arguments() -> tuple[str, int, int, tuple[Operation, ...], bool]:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("warm", "cold", "both"),
        default="warm",
        help="profile warmed operations, isolated cold output roots, or both",
    )
    parser.add_argument(
        "--runs",
        type=_positive_integer,
        default=3,
        help="measured samples per operation and mode (default: 3)",
    )
    parser.add_argument(
        "--warmups",
        type=_positive_integer,
        default=1,
        help="unmeasured warmup runs before warm samples (default: 1)",
    )
    parser.add_argument(
        "--operation",
        action="append",
        choices=(*_OPERATIONS, "all"),
        help="profile only this operation; repeatable, or use 'all'",
    )
    parser.add_argument(
        "--full-profile",
        action="store_true",
        help="retain unslimmed Bazel traces with full profiler data",
    )
    arguments = parser.parse_args()
    return (
        cast("str", arguments.mode),
        cast("int", arguments.runs),
        cast("int", arguments.warmups),
        _selected_operations(cast("list[str] | None", arguments.operation)),
        cast("bool", arguments.full_profile),
    )


def main() -> int:
    """Run selected profiling operations and publish trace artifacts."""
    try:
        mode, runs, warmups, operations, full_profile = _parse_arguments()
        profiler = Profiler(full_profile=full_profile)
        samples: list[Sample] = []
        if mode in {"warm", "both"}:
            warm_output_root = profiler.temporary / "profile-output-warm"
            for operation in operations:
                for warmup in range(1, warmups + 1):
                    profiler.run(
                        operation,
                        mode="warmup",
                        iteration=warmup,
                        output_root=warm_output_root,
                        record=False,
                    )
                for iteration in range(1, runs + 1):
                    sample = profiler.run(
                        operation,
                        mode="warm",
                        iteration=iteration,
                        output_root=warm_output_root,
                        record=True,
                    )
                    assert sample is not None
                    samples.append(sample)
        if mode in {"cold", "both"}:
            for operation in operations:
                for iteration in range(1, runs + 1):
                    output_root = (
                        profiler.temporary / f"profile-output-cold-{operation.name}-{iteration}"
                    )
                    sample = profiler.run(
                        operation,
                        mode="cold",
                        iteration=iteration,
                        output_root=output_root,
                        record=True,
                    )
                    assert sample is not None
                    samples.append(sample)
        markdown = profiler.write_summary(
            samples=samples,
            operations=operations,
            mode=mode,
            runs=runs,
            warmups=warmups,
        )
    except (OSError, RuntimeError, ValueError) as error:
        print(f"bazel_devtools profiler: {error}", file=sys.stderr)
        return 1
    print("\n" + markdown, end="")
    print(f"Profiles and summaries: {profiler.results}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
