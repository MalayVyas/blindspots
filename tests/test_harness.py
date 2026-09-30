"""Tests against real harness output from runs dev-gold-1, dev-noop-1 and
dev-empty-1 (task django__django-13343), copied into tests/fixtures."""

import json
import sys
from pathlib import Path

import pytest

from blindspots.harness import (
    HarnessError, find_summary, find_task_file, harness_command,
    outcome_from_report, parse_timing, read_report, read_summary,
)
from blindspots.record import Outcome

FIX = Path(__file__).parent / "fixtures"
TASK = "django__django-13343"


# ---- verdicts from real reports

def test_gold_report_is_resolved():
    outcome, suite = read_report(FIX / "gold" / "report.json", TASK)
    assert outcome is Outcome.RESOLVED
    assert (len(suite.fail_to_pass_passed), len(suite.fail_to_pass_failed)) == (1, 0)
    assert (len(suite.pass_to_pass_passed), len(suite.pass_to_pass_failed)) == (130, 0)


def test_noop_report_is_unresolved_for_the_right_reason():
    outcome, suite = read_report(FIX / "noop" / "report.json", TASK)
    assert outcome is Outcome.UNRESOLVED
    assert len(suite.fail_to_pass_failed) == 1   # the bug is still there
    assert len(suite.pass_to_pass_failed) == 0   # nothing else broke


def test_empty_summary_lists_all_five_as_empty():
    summary = read_summary(FIX / "empty.dev-empty-1.json")
    assert summary["completed_instances"] == 0
    assert TASK in summary["empty_patch_ids"]


def test_report_without_the_task_is_an_error():
    with pytest.raises(HarnessError):
        read_report(FIX / "gold" / "report.json", "django__django-99999")


# ---- the outcome order, on synthetic reports

BASE = {"patch_is_None": False, "patch_exists": True,
        "patch_successfully_applied": True, "resolved": False,
        "infra_failure": False,
        "tests_status": {k: {"success": [], "failure": ["t"]}
                         for k in ("FAIL_TO_PASS", "PASS_TO_PASS")}}


@pytest.mark.parametrize("change, expected", [
    ({"infra_failure": True}, Outcome.HARNESS_ERROR),
    ({"patch_exists": False}, Outcome.EMPTY_PATCH),
    ({"patch_successfully_applied": False}, Outcome.PATCH_APPLY_FAILED),
    ({}, Outcome.UNRESOLVED),
])
def test_outcome_order(change, expected):
    outcome, suite = outcome_from_report({**BASE, **change})
    assert outcome is expected
    assert (suite is None) == (expected is not Outcome.UNRESOLVED)


# ---- "patch_successfully_applied: False" is ambiguous; the log decides
# (results entry #8: a patch that applied cleanly and then crashed the tests)

NOT_APPLIED = {"patch_successfully_applied": False}


@pytest.mark.parametrize("log, expected", [
    ("... >>>>> Applied Patch:\nApplied patch x.py cleanly.\n...", Outcome.TESTS_ERRORED),
    ("... >>>>> Patch Apply Failed:\nerror: patch failed\n", Outcome.PATCH_APPLY_FAILED),
    ("... nothing recognisable ...", Outcome.HARNESS_ERROR),
    (None, Outcome.PATCH_APPLY_FAILED),
])
def test_not_applied_is_decided_by_the_log(log, expected):
    outcome, suite = outcome_from_report({**BASE, **NOT_APPLIED}, log)
    assert outcome is expected and suite is None


def test_real_logs_carry_the_applied_marker():
    for name in ("gold", "noop"):
        text = (FIX / name / "run_instance.log").read_text()
        assert ">>>>> Applied Patch" in text and ">>>>> Patch Apply Failed" not in text


# ---- timing from real logs (figures match results.md entry #2)

def test_gold_timing_cold_image():
    t = parse_timing(FIX / "gold" / "run_instance.log")
    assert t.image_pull_s == pytest.approx(198.3, abs=0.1)
    assert t.evaluation_s == pytest.approx(26.5, abs=0.1)
    assert t.test_runtime_s == pytest.approx(9.20)
    assert 15.0 <= t.teardown_s <= 16.0      # the harness's 15 s stop wait


def test_noop_timing_warm_image_has_no_pull():
    t = parse_timing(FIX / "noop" / "run_instance.log")
    assert t.image_pull_s is None
    assert t.test_runtime_s == pytest.approx(16.80)
    assert t.started_at.tzinfo is not None


# ---- finding files: exactly one, or an error

def test_find_task_file(tmp_path):
    for model in ("gold", "noop"):
        d = tmp_path / "run_evaluation" / "r1" / model / TASK
        d.mkdir(parents=True)
        (d / "report.json").write_text("{}")
    with pytest.raises(HarnessError):            # two copies: ambiguous
        find_task_file(tmp_path, "r1", TASK, "report.json")
    assert find_task_file(tmp_path, "r2", TASK, "report.json") is None


def test_find_summary(tmp_path):
    (tmp_path / "gold.r1.json").write_text("{}")
    assert find_summary(tmp_path, "r1").name == "gold.r1.json"
    with pytest.raises(HarnessError):
        find_summary(tmp_path, "r2")


def test_harness_command_shape():
    cmd = harness_command(["a", "b"], "gold", "r1")
    assert cmd[:3] == [sys.executable, "-m", "swebench.harness.run_evaluation"]
    assert cmd[-3:] == ["--instance_ids", "a", "b"]
    assert cmd[cmd.index("--run_id") + 1] == "r1"
