"""Wrap the official SWE-bench harness (ADR-0010, ADR-0011).

The harness runs as a separate process through its documented command
line. Everything here either builds that command or reads what the
harness wrote: per-task report.json, per-task run_instance.log, and the
run summary file.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from blindspots.record import Outcome, SuiteResults, Timing

DATASET = "SWE-bench/SWE-bench_Verified"

# "2026-09-29 08:58:51,853 - INFO - ..."
_LOG_TIME = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - ")
_TEST_RUNTIME = re.compile(r"Test runtime: ([\d.]+) seconds")


class HarnessError(RuntimeError):
    """The harness's output is missing or ambiguous. Never guessed around."""


# ---------------------------------------------------------------- running

def harness_command(instance_ids: list[str], predictions: str, run_id: str,
                    max_workers: int = 1, dataset: str = DATASET) -> list[str]:
    """The exact command line, as a list (no shell, so no quoting problems)."""
    return [
        sys.executable, "-m", "swebench.harness.run_evaluation",
        "--dataset_name", dataset,
        "--predictions_path", predictions,
        "--max_workers", str(max_workers),
        "--run_id", run_id,
        "--instance_ids", *instance_ids,
    ]


def run_harness(instance_ids: list[str], predictions: str, run_id: str,
                workdir: Path, max_workers: int = 1, offline: bool = True,
                timeout_s: int = 3 * 3600) -> int:
    """Run the harness inside workdir; save its console output there.

    Returns the harness's exit code. The exit code is recorded but never
    trusted as a verdict (ADR-0010): verdicts come from report.json.
    """
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    if offline:
        env["HF_DATASETS_OFFLINE"] = "1"  # ADR-0010 addendum
    cmd = harness_command(instance_ids, predictions, run_id, max_workers)
    with open(workdir / f"harness.{run_id}.out", "w") as out:
        proc = subprocess.run(cmd, cwd=workdir, env=env, stdout=out,
                              stderr=subprocess.STDOUT, timeout=timeout_s)
    return proc.returncode


# ---------------------------------------------------------------- finding

def find_task_file(logs_root: Path, run_id: str, instance_id: str,
                   filename: str) -> Path | None:
    """Find one task's file under logs/ by search, never a hardcoded path.

    None if absent (the task never ran). More than one match is an error:
    the results could not be trusted.
    """
    matches = [p for p in Path(logs_root).rglob(f"{instance_id}/{filename}")
               if run_id in p.parts]
    if len(matches) > 1:
        raise HarnessError(f"{len(matches)} copies of {filename} for "
                           f"{instance_id} in run {run_id}: {matches}")
    return matches[0] if matches else None


def find_summary(workdir: Path, run_id: str) -> Path:
    """The run summary the harness writes as MODEL.RUN_ID.json in workdir."""
    matches = list(Path(workdir).glob(f"*.{run_id}.json"))
    if len(matches) != 1:
        raise HarnessError(f"expected 1 summary for {run_id}, found {matches}")
    return matches[0]


# ---------------------------------------------------------------- reading

def read_summary(path: Path) -> dict:
    return json.loads(Path(path).read_text())


def outcome_from_report(report: dict) -> tuple[Outcome, SuiteResults | None]:
    """Map one task's report.json entry to exactly one outcome.

    Order matters: a patch that did not apply has no meaningful test
    results, so that check comes before resolved/unresolved.
    """
    if report.get("infra_failure"):
        return Outcome.HARNESS_ERROR, None
    if report.get("patch_is_None") or not report.get("patch_exists"):
        return Outcome.EMPTY_PATCH, None
    if not report.get("patch_successfully_applied"):
        return Outcome.PATCH_APPLY_FAILED, None
    ts = report["tests_status"]
    suite = SuiteResults(
        fail_to_pass_passed=ts["FAIL_TO_PASS"]["success"],
        fail_to_pass_failed=ts["FAIL_TO_PASS"]["failure"],
        pass_to_pass_passed=ts["PASS_TO_PASS"]["success"],
        pass_to_pass_failed=ts["PASS_TO_PASS"]["failure"],
    )
    return (Outcome.RESOLVED if report["resolved"] else Outcome.UNRESOLVED), suite


def read_report(path: Path, instance_id: str) -> tuple[Outcome, SuiteResults | None]:
    data = json.loads(Path(path).read_text())
    if instance_id not in data:
        raise HarnessError(f"{path} has no entry for {instance_id}")
    return outcome_from_report(data[instance_id])


def parse_timing(log_path: Path) -> Timing:
    """Split one task's wall-clock into pull, evaluation, tests, teardown.

    Log timestamps carry no timezone. They are written by this machine's
    clock, so .astimezone() labels them with this machine's zone.
    """
    stamped: list[tuple[datetime, str]] = []
    for line in Path(log_path).read_text(errors="replace").splitlines():
        m = _LOG_TIME.match(line)
        if m:
            t = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S,%f").astimezone()
            stamped.append((t, line[m.end():]))
    if not stamped:
        raise HarnessError(f"no timestamped lines in {log_path}")

    def first(text: str) -> datetime | None:
        return next((t for t, msg in stamped if text in msg), None)

    start, end = stamped[0][0], stamped[-1][0]
    created = first("created:")
    stopping = first("Attempting to stop container")
    pulled = first("attempting to pull") is not None
    runtime = next((float(m.group(1)) for _, msg in stamped
                    if (m := _TEST_RUNTIME.search(msg))), None)

    secs = lambda a, b: round((b - a).total_seconds(), 3)
    return Timing(
        started_at=start,
        finished_at=end,
        image_pull_s=secs(start, created) if pulled and created else None,
        evaluation_s=secs(created, end) if created else None,
        test_runtime_s=runtime,
        teardown_s=secs(stopping, end) if stopping else None,
    )
