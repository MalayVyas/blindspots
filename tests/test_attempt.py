"""Step 4: every way an agent attempt can end becomes a valid run record. $0."""

import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest

from blindspots.accountant import Limits
from blindspots.agent import attempt as att
from blindspots.providers.base import ProviderError
from blindspots.record import Outcome, read_record, write_record
from blindspots.run import build_records
from test_agent import GOOD_REPLY, FakeModel, repo, task  # noqa: F401  (repo is a fixture)
from test_run import ENV, FIX

T0 = datetime(2026, 10, 1, tzinfo=timezone.utc)


@pytest.fixture
def no_prepare(monkeypatch, repo):
    monkeypatch.setattr(att, "prepare", lambda t, root: repo)
    return repo


class Failing:
    def complete(self, *a, **k):
        raise ProviderError("HTTP 402: insufficient balance")


@pytest.mark.parametrize("provider, limits, outcome, status", [
    (FakeModel(GOOD_REPLY), Limits(), None, "patch"),
    (FakeModel("No idea."), Limits(), Outcome.EMPTY_PATCH, "no_edits"),
    (FakeModel("mypkg/calc.py\n<<<<<<< SEARCH\nnope\n=======\nx\n>>>>>>> REPLACE\n"),
     Limits(), Outcome.PATCH_APPLY_FAILED, "edit_failed"),
    (FakeModel(GOOD_REPLY), Limits(max_input_tokens=10), Outcome.SPEND_CEILING, None),
    (Failing(), Limits(), Outcome.PROVIDER_ERROR, None),
])
def test_every_ending_is_captured(no_prepare, tmp_path, provider, limits, outcome, status):
    a = att.attempt(task(no_prepare), provider, limits, tmp_path)
    assert a.outcome == outcome
    assert a.diagnostics.get("agent_status") == status
    assert a.prompt_hashes and a.finished_at >= a.started_at
    if outcome is Outcome.SPEND_CEILING:
        assert a.breach.limit == "input_tokens" and a.usage.model_calls == 0
        assert "refused" in a.transcript[-1]
    if outcome in (None, Outcome.EMPTY_PATCH, Outcome.PATCH_APPLY_FAILED):
        assert a.usage.model_calls == 1 and len(a.transcript) == 1
    assert (a.patch != "") == (outcome is None)
    if status is not None:
        assert a.diagnostics["image_environment_changes"] == []


def config():
    return {"patch_source": "agent:simple", **att.agent_config(Limits())}


def test_decided_outcomes_become_records_without_the_harness(no_prepare, tmp_path):
    atts = {}
    for iid, provider in [("a", FakeModel("No idea.")), ("b", Failing())]:
        a = att.attempt(task(no_prepare), provider, Limits(), tmp_path)
        a.instance_id = iid
        atts[iid] = a
    recs = build_records("r", "agent:simple", {"a": "", "b": ""}, tmp_path / "none",
                         ENV, config(), T0, T0, atts)
    assert [r.outcome for r in recs] == [Outcome.EMPTY_PATCH, Outcome.PROVIDER_ERROR]
    assert recs[0].usage.model_calls == 1 and recs[0].transcript
    assert recs[1].error.startswith("HTTP 402")
    for r in recs:                                   # survives a write and a re-read
        assert read_record(write_record(r, tmp_path / "records")) == r


def test_scored_patch_keeps_usage_and_diagnostics(no_prepare, tmp_path):
    TASK = "django__django-13343"
    a = att.attempt(task(no_prepare), FakeModel(GOOD_REPLY), Limits(), tmp_path)
    d = tmp_path / "logs" / "run_evaluation" / "r" / "agent:simple" / TASK
    d.mkdir(parents=True)
    for name in ("report.json", "run_instance.log"):
        shutil.copy(FIX / "noop" / name, d / name)
    [rec] = build_records("r", "agent:simple", {TASK: a.patch}, tmp_path, ENV,
                          config(), T0, T0, {TASK: a})
    assert rec.outcome is Outcome.UNRESOLVED          # verdict from the harness fixture
    assert rec.usage.model_calls == 1 and rec.prompt_hashes == a.prompt_hashes
    assert rec.diagnostics["localisation"]["all_gold_files_shown"]
    assert rec.model == "deepseek-flash"
    assert rec.config["limits"]["max_cost_usd"] == 0.10


def test_agent_config_changes_hash_when_limits_change():
    from blindspots.record import config_hash
    assert config_hash(att.agent_config(Limits())) != config_hash(att.agent_config(Limits(max_calls=6)))


def test_cache_bust_changes_hash_only_when_on():
    from blindspots.record import config_hash
    # Off: identical to the Week 2 config, so its hash is unchanged.
    assert att.agent_config(Limits()) == att.agent_config(Limits(), cache_bust=False)
    assert "cache_bust" not in att.agent_config(Limits())
    assert config_hash(att.agent_config(Limits())) != config_hash(att.agent_config(Limits(), cache_bust=True))


class WarmModel(FakeModel):
    """Reports 128 of 500 input tokens served from cache."""
    def complete(self, messages, **kw):
        c = super().complete(messages, **kw)
        u = c.usage.model_copy(update={"cache_hit_tokens": 128, "cache_miss_tokens": 372})
        return c.model_copy(update={"usage": u})


@pytest.mark.parametrize("provider, verified", [
    (FakeModel(GOOD_REPLY), True),     # 0 cache-hit tokens: the bust worked
    (WarmModel(GOOD_REPLY), False),    # any hit at all: flagged, not hidden
])
def test_cache_bust_is_verified_from_reported_hits(no_prepare, tmp_path, provider, verified):
    a = att.attempt(task(no_prepare), provider, Limits(), tmp_path, cache_bust=True)
    assert a.diagnostics["cache_bust_verified"] is verified
    assert len(a.diagnostics["cache_bust_marker"]) == 32


def test_unbusted_attempt_has_no_bust_diagnostics(no_prepare, tmp_path):
    a = att.attempt(task(no_prepare), FakeModel(GOOD_REPLY), Limits(), tmp_path)
    assert "cache_bust_verified" not in a.diagnostics
