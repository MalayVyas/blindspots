from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from blindspots.record import (
    Environment, Outcome, RunRecord, SuiteResults, Timing,
    config_hash, read_record, write_record,
)

CONFIG = {"patch_source": "gold", "swebench_version": "5.0.2"}
NOW = datetime(2026, 9, 29, tzinfo=timezone.utc)


def make(**overrides):
    fields = dict(
        run_id="test-run",
        instance_id="django__django-13343",
        patch_source="gold",
        config=CONFIG,
        config_hash=config_hash(CONFIG),
        patch="diff --git a/x b/x\n",
        outcome=Outcome.RESOLVED,
        tests=SuiteResults(fail_to_pass_passed=["t1"], fail_to_pass_failed=[],
                          pass_to_pass_passed=["t2"], pass_to_pass_failed=[]),
        timing=Timing(started_at=NOW, finished_at=NOW),
        environment=Environment(
            blindspots_commit="f58c8bd", swebench_version="5.0.2",
            dataset_name="SWE-bench/SWE-bench_Verified", dataset_revision=None,
            python_version="3.11.16", docker_version="29.6.2", machine="local"),
    )
    fields.update(overrides)
    return RunRecord(**fields)


def test_hash_ignores_key_order():
    assert config_hash({"a": 1, "b": 2}) == config_hash({"b": 2, "a": 1})


def test_round_trip(tmp_path):
    rec = make()
    path = write_record(rec, tmp_path)
    assert path == tmp_path / "test-run" / "django__django-13343.json"
    assert read_record(path) == rec


def test_never_overwrites(tmp_path):
    write_record(make(), tmp_path)
    with pytest.raises(FileExistsError):
        write_record(make(), tmp_path)


def test_rejects_wrong_hash():
    with pytest.raises(ValidationError, match="config_hash"):
        make(config_hash="0" * 64)


def test_rejects_misspelt_field():
    with pytest.raises(ValidationError):
        make(outcom="resolved")


def test_resolved_with_a_failing_test_is_rejected():
    bad = SuiteResults(fail_to_pass_passed=[], fail_to_pass_failed=["t1"],
                      pass_to_pass_passed=["t2"], pass_to_pass_failed=[])
    with pytest.raises(ValidationError, match="resolved requires"):
        make(tests=bad)


def test_unresolved_needs_tests():
    with pytest.raises(ValidationError, match="needs test results"):
        make(outcome=Outcome.UNRESOLVED, tests=None)


def test_empty_patch_record():
    rec = make(outcome=Outcome.EMPTY_PATCH, patch="", tests=None)
    assert rec.tests is None
