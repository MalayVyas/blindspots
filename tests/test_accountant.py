"""Accountant tests. No network and no money: a fake provider stands in for
DeepSeek, and a fake clock stands in for time."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from blindspots import pricing
from blindspots.accountant import Accountant, LimitBreached, Limits, outcome_for, prompt_bytes
from blindspots.providers.base import ProviderError
from blindspots.providers.deepseek import build_request, parse_response
from blindspots.record import (
    Breach, Environment, Outcome, RunRecord, Timing, Usage, config_hash, read_record,
)

MODEL = "deepseek-flash"
MSGS = [{"role": "user", "content": "x" * 1000}]   # 1,000 bytes
ARGS = dict(max_tokens=100, temperature=0.0, thinking="disabled")
OFF_PEAK = datetime(2026, 10, 3, 2, 0, tzinfo=timezone.utc)   # a Saturday
PEAK = datetime(2026, 10, 5, 2, 0, tzinfo=timezone.utc)       # a Monday, 02:00 UTC


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class FakeProvider:
    """Answers every call with fixed usage; can advance the clock or fail."""

    def __init__(self, clock=None, prompt=300, hit=0, completion=50, seconds=1.0,
                 fail=None, started_at=OFF_PEAK):
        self.clock, self.prompt, self.hit = clock, prompt, hit
        self.completion, self.seconds, self.fail = completion, seconds, fail
        self.started_at = started_at
        self.sent = []   # every call that actually reached the "API"

    def complete(self, messages, *, model, max_tokens, temperature, thinking,
                 reasoning_effort=None, timeout_s=None):
        self.sent.append({"timeout_s": timeout_s, "max_tokens": max_tokens})
        if self.clock:
            self.clock.t += self.seconds
        if self.fail:
            raise ProviderError(self.fail)
        body = build_request(messages, model=model, max_tokens=max_tokens,
                             temperature=temperature, thinking=thinking)
        data = {"model": model,
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": self.prompt, "completion_tokens": self.completion,
                          "prompt_tokens_details": {
                              "prompt_cache_hit_tokens": self.hit,
                              "prompt_cache_miss_tokens": self.prompt - self.hit}}}
        return parse_response(data, request=body, model=model,
                              started_at=self.started_at, latency_s=self.seconds)


def acct(limits=Limits(), **fake):
    clock = FakeClock()
    return Accountant(FakeProvider(clock=clock, **fake), limits, model=MODEL, clock=clock)


# ---------------------------------------------------------------- normal use

def test_one_call_is_counted():
    a = acct()
    a.complete(MSGS, **ARGS)
    u = a.usage()
    assert (u.model_calls, u.input_tokens, u.output_tokens) == (1, 300, 50)
    assert u.cost_usd == pytest.approx(u.reference_usd)          # off-peak
    assert u.ceiling_usd == pytest.approx(2 * u.reference_usd)   # counted at peak
    assert len(a.transcript()) == 1


def test_remaining_wall_clock_is_passed_as_timeout():
    a = acct(Limits(max_wall_clock_s=100))
    a.complete(MSGS, **ARGS)   # takes 1 s on the fake clock
    a.complete(MSGS, **ARGS)
    assert [s["timeout_s"] for s in a.provider.sent] == [100, 99]


def test_ceiling_does_not_depend_on_time_of_day():
    a, b = acct(started_at=OFF_PEAK), acct(started_at=PEAK)
    a.complete(MSGS, **ARGS); b.complete(MSGS, **ARGS)
    assert a.usage().ceiling_usd == b.usage().ceiling_usd
    assert b.usage().cost_usd == pytest.approx(2 * a.usage().cost_usd)


def test_unknown_model_fails_at_start():
    with pytest.raises(pricing.UnknownModel):
        Accountant(FakeProvider(), Limits(), model="deepseek-chat")


# ---------------------------------------------------------------- the runaway loop
# October plan, Week 2 acceptance: "a deliberately broken loop hits the
# ceiling and aborts cleanly".

def run_forever(a):
    while True:          # the bug: no stop condition
        a.complete(MSGS, **ARGS)


def test_runaway_loop_stops_at_call_limit():
    a = acct(Limits(max_calls=5))
    with pytest.raises(LimitBreached) as e:
        run_forever(a)
    assert e.value.breach.limit == "calls" and e.value.breach.before_call
    assert len(a.provider.sent) == 5          # the 6th was never sent
    t = a.transcript()
    assert len(t) == 6 and "refused" in t[-1]  # 5 calls + the refused one


def test_runaway_loop_stops_at_cost_cap_and_never_passes_it():
    cap = 0.001
    a = acct(Limits(max_calls=10_000, max_cost_usd=cap, max_input_tokens=10**9,
                    max_output_tokens=10**9))
    with pytest.raises(LimitBreached) as e:
        run_forever(a)
    u = a.usage()
    assert e.value.breach.limit == "cost_usd" and e.value.breach.before_call
    assert u.ceiling_usd <= cap and u.cost_usd <= cap
    # and one more call's worst case would have passed it
    worst = pricing.worst_case_usd(MODEL, input_tokens=prompt_bytes(MSGS), output_tokens=100)
    assert u.ceiling_usd + worst > cap


def test_runaway_loop_stops_at_wall_clock():
    a = acct(Limits(max_calls=10_000, max_wall_clock_s=10), seconds=3)
    with pytest.raises(LimitBreached) as e:
        run_forever(a)
    # 3 s per call: calls end at 3, 6, 9, 12 s. The 4th overran during the call.
    assert e.value.breach.limit == "wall_clock_s"
    assert len(a.calls) == 4 and not e.value.breach.before_call


# ---------------------------------------------------------------- single limits

def test_prompt_too_big_is_refused_before_sending():
    a = acct(Limits(max_input_tokens=500))   # MSGS is 1,000 bytes
    with pytest.raises(LimitBreached) as e:
        a.complete(MSGS, **ARGS)
    assert e.value.breach.limit == "input_tokens"
    assert a.provider.sent == []


def test_reaching_a_limit_exactly_is_allowed():
    a = acct(Limits(max_output_tokens=150))
    a.complete(MSGS, **ARGS)                  # uses 50
    a.complete(MSGS, **ARGS)                  # 50 used + 100 reserved = 150: allowed
    assert len(a.provider.sent) == 2


def test_output_budget_refuses_when_reservation_would_pass_it():
    a = acct(Limits(max_output_tokens=120))
    a.complete(MSGS, **ARGS)                  # uses 50
    with pytest.raises(LimitBreached) as e:
        a.complete(MSGS, **ARGS)              # 50 + 100 > 120
    assert e.value.breach.limit == "output_tokens"
    assert len(a.provider.sent) == 1


def test_wrong_bound_is_caught_after_the_call():
    # The API reports more tokens than the byte bound allowed for.
    a = acct(Limits(max_input_tokens=1_200), prompt=5_000)
    with pytest.raises(LimitBreached) as e:
        a.complete(MSGS, **ARGS)
    assert e.value.breach.limit == "input_tokens" and not e.value.breach.before_call
    assert len(a.calls) == 1                  # paid for, so it stays in the transcript


def test_timeout_during_call_is_a_wall_clock_breach():
    a = acct(Limits(max_wall_clock_s=5), seconds=6, fail="request failed: ReadTimeout")
    with pytest.raises(LimitBreached) as e:
        a.complete(MSGS, **ARGS)
    assert e.value.breach.limit == "wall_clock_s"
    # We never saw its usage, so it is booked at its worst case.
    worst = pricing.worst_case_usd(MODEL, input_tokens=prompt_bytes(MSGS), output_tokens=100)
    assert a.usage().ceiling_usd == pytest.approx(worst)
    assert "timed_out" in a.transcript()[0]


def test_provider_error_with_time_left_is_not_disguised():
    a = acct(fail="HTTP 402: insufficient balance")
    with pytest.raises(ProviderError, match="402"):
        a.complete(MSGS, **ARGS)


# ---------------------------------------------------------------- run record

ENV = Environment(blindspots_commit="abc", swebench_version="5.0.2",
                  dataset_name="SWE-bench/SWE-bench_Verified", dataset_revision=None,
                  python_version="3.11.16", docker_version=None, machine="local")


def record_for(a, breach, outcome):
    config = {"model": MODEL, "limits": a.limits.model_dump()}
    now = datetime.now(timezone.utc)
    return RunRecord(run_id="t", instance_id="ceiling-test", patch_source="agent:test",
                     model=MODEL, config=config, config_hash=config_hash(config),
                     patch="", outcome=outcome, tests=None, usage=a.usage(),
                     timing=Timing(started_at=now, finished_at=now),
                     transcript=a.transcript(), breach=breach, environment=ENV)


def test_breach_becomes_a_valid_record(tmp_path):
    a = acct(Limits(max_calls=2))
    with pytest.raises(LimitBreached) as e:
        run_forever(a)
    rec = record_for(a, e.value.breach, outcome_for(e.value.breach))
    assert rec.outcome is Outcome.SPEND_CEILING and rec.usage.model_calls == 2
    assert len(rec.transcript) == 3


def test_record_refuses_breach_outcome_mismatch():
    a = acct()
    with pytest.raises(ValueError):
        record_for(a, Breach(limit="wall_clock_s", allowed=1, would_reach=2, before_call=True),
                   Outcome.SPEND_CEILING)
    with pytest.raises(ValueError):
        record_for(a, None, Outcome.SPEND_CEILING)


def test_schema_v1_records_still_load():
    rec = read_record(Path(__file__).parent / "fixtures" / "record_v1.json")
    assert rec.schema_version == 1 and rec.breach is None


def test_limits_change_the_config_hash():
    assert (config_hash({"limits": Limits().model_dump()})
            != config_hash({"limits": Limits(max_calls=6).model_dump()}))
