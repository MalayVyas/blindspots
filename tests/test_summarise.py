from datetime import datetime, timezone

import pytest

from blindspots.record import Environment, write_record
from blindspots.run import NOOP_PATCH, build_records
from blindspots.summarise import load, table

import shutil
from pathlib import Path

FIX = Path(__file__).parent / "fixtures"
TASK = "django__django-13343"


def harness_layout(root, run_id, model, fixture_dir):
    d = root / "logs" / "run_evaluation" / run_id / model / TASK
    d.mkdir(parents=True)
    for name in ("report.json", "run_instance.log"):
        shutil.copy(FIX / fixture_dir / name, d / name)
    return root

ENV = Environment(blindspots_commit="bd85364abc", swebench_version="5.0.2",
                  dataset_name="SWE-bench/SWE-bench_Verified", dataset_revision=None,
                  python_version="3.11.16", docker_version="29.6.2", machine="ci")
T0 = datetime(2026, 9, 29, tzinfo=timezone.utc)


def test_table_from_real_records(tmp_path):
    wd = harness_layout(tmp_path / "wd", "r1", "noop", "noop")
    [rec] = build_records("r1", "noop", {TASK: NOOP_PATCH}, wd, ENV,
                          {"patch_source": "noop"}, T0, T0)
    write_record(rec, tmp_path / "records")
    out = table(load(tmp_path / "records"))
    assert f"| r1 | {TASK} | unresolved | 36.7 | 16.8 | 15.5 | – | ci | bd85364 |" in out
    assert "**1 records:** 1 unresolved" in out


def test_corrupt_record_stops_the_summary(tmp_path):
    bad = tmp_path / "r1" / "x.json"
    bad.parent.mkdir(parents=True)
    bad.write_text('{"schema_version": 1}')
    with pytest.raises(Exception):
        load(tmp_path)
