"""Tests for the runner, using real harness output as fixtures."""

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest

from blindspots.record import Environment, Outcome
from blindspots.run import (
    NOOP_PATCH, RunnerError, build_records, check_against_summary,
    patches_for, preflight, select_instances, write_predictions,
)

FIX = Path(__file__).parent / "fixtures"
TASK = "django__django-13343"
T0 = datetime(2026, 9, 29, tzinfo=timezone.utc)
ENV = Environment(blindspots_commit="abc", swebench_version="5.0.2",
                  dataset_name="SWE-bench/SWE-bench_Verified", dataset_revision=None,
                  python_version="3.11.16", docker_version="29.6.2", machine="local")
CONFIG = {"patch_source": "noop"}


def harness_layout(tmp_path, run_id, model, fixture_dir):
    """Recreate the folder layout the harness writes, from fixture files."""
    d = tmp_path / "logs" / "run_evaluation" / run_id / model / TASK
    d.mkdir(parents=True)
    for name in ("report.json", "run_instance.log"):
        shutil.copy(FIX / fixture_dir / name, d / name)
    return tmp_path


def test_noop_run_becomes_an_unresolved_record(tmp_path):
    wd = harness_layout(tmp_path, "r1", "noop", "noop")
    [rec] = build_records("r1", "noop", {TASK: NOOP_PATCH}, wd, ENV, CONFIG, T0, T0)
    assert rec.outcome is Outcome.UNRESOLVED
    assert rec.timing.test_runtime_s == pytest.approx(16.8)
    assert rec.harness_log.endswith("run_instance.log")


def test_gold_run_becomes_a_resolved_record(tmp_path):
    wd = harness_layout(tmp_path, "r1", "gold", "gold")
    [rec] = build_records("r1", "gold", {TASK: "diff --git a/x b/x\n"}, wd, ENV,
                          {"patch_source": "gold"}, T0, T0)
    assert rec.outcome is Outcome.RESOLVED


def test_empty_patch_needs_no_harness_output(tmp_path):
    [rec] = build_records("r1", "empty", {TASK: ""}, tmp_path, ENV,
                          {"patch_source": "empty"}, T0, T0)
    assert rec.outcome is Outcome.EMPTY_PATCH and rec.tests is None


def test_missing_report_is_a_harness_error_not_a_guess(tmp_path):
    [rec] = build_records("r1", "noop", {TASK: NOOP_PATCH}, tmp_path, ENV, CONFIG, T0, T0)
    assert rec.outcome is Outcome.HARNESS_ERROR
    assert "no report.json" in rec.error


def test_summary_disagreement_is_refused(tmp_path):
    wd = harness_layout(tmp_path, "r1", "gold", "gold")
    recs = build_records("r1", "gold", {TASK: "diff\n"}, wd, ENV,
                         {"patch_source": "gold"}, T0, T0)
    check_against_summary(recs, {"resolved_ids": [TASK]})        # agrees
    with pytest.raises(RunnerError):
        check_against_summary(recs, {"resolved_ids": []})         # disagrees


def test_preflight_refuses_a_reused_run_id(tmp_path):
    preflight(tmp_path, tmp_path / "records", "r1")               # fresh: fine
    (tmp_path / "logs" / "run_evaluation" / "r1").mkdir(parents=True)
    with pytest.raises(RunnerError, match="harness logs"):
        preflight(tmp_path, tmp_path / "records", "r1")
    (tmp_path / "records" / "r2").mkdir(parents=True)
    with pytest.raises(RunnerError, match="records"):
        preflight(tmp_path, tmp_path / "records", "r2")


def test_predictions_file_format(tmp_path):
    path = write_predictions(tmp_path / "p.jsonl", "noop", patches_for("noop", [TASK, "b"]))
    lines = [json.loads(l) for l in path.read_text().splitlines()]
    assert [l["instance_id"] for l in lines] == [TASK, "b"]
    assert lines[0] == {"instance_id": TASK, "model_name_or_path": "noop",
                        "model_patch": NOOP_PATCH}


def test_unknown_source_is_refused():
    with pytest.raises(RunnerError):
        patches_for("agent", [TASK])


def test_select_instances():
    split = ["a", "b", "c"]
    assert select_instances(split, None) == split
    assert select_instances(split, ["c", "a"]) == ["a", "c"]   # split order kept
    with pytest.raises(RunnerError, match="not in the split"):
        select_instances(split, ["a", "z"])
