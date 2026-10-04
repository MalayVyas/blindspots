"""agent:mini (ADR-0018): stock mini-swe-agent, our transport. $0.

mini's own agent loop, parser, observation formatter and submission check run
for real. Only the model's HTTP call (a scripted fake behind our real
adapter functions) and the container (no Docker) are replaced.
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from blindspots.accountant import (
    Accountant, LimitBreached, Limits, TranscriptMismatch, prompt_bytes, rebuild_requests)
from blindspots.agent import mini, simple
from blindspots.agent.workspace import Task
from blindspots.providers.base import ProviderError, reply_message
from blindspots.providers.deepseek import build_request, parse_response
from blindspots.record import Outcome, config_hash, read_record, write_record
from blindspots.run import build_records
from test_run import ENV

FIX = Path(__file__).parent / "fixtures"
T0 = datetime(2026, 10, 4, tzinfo=timezone.utc)
PATCH = ("diff --git a/mypkg/calc.py b/mypkg/calc.py\n--- a/mypkg/calc.py\n"
         "+++ b/mypkg/calc.py\n@@ -1,2 +1,2 @@\n def add(a, b):\n-    return a - b\n"
         "+    return a + b\n")
GOLD = "diff --git a/mypkg/calc.py b/mypkg/calc.py\n--- a/mypkg/calc.py\n+++ b/mypkg/calc.py\n"


def task():
    return Task(instance_id="t-mini", repo="me/mypkg", base_commit="0" * 40, image="none",
                problem_statement="add() subtracts instead of adding.", gold_patch=GOLD)


# ---------------------------------------------------------------- fakes

def tool(command, call_id):
    return {"id": call_id, "type": "function",
            "function": {"name": "bash", "arguments": json.dumps({"command": command})}}


class ScriptedProvider:
    """Replies in order. Each reply is a list of bash commands (a tool-call
    reply), a string (a text reply with no tool call), or an exception."""

    def __init__(self, replies):
        self.replies, self.seen, self.n = list(replies), [], 0

    def complete(self, messages, *, model, max_tokens, temperature, thinking,
                 reasoning_effort=None, timeout_s=None, tools=None, tool_choice=None):
        reply = self.replies[self.n]
        if isinstance(reply, Exception):
            raise reply
        self.seen.append(json.loads(json.dumps(messages)))
        body = build_request(messages, model=model, max_tokens=max_tokens,
                             temperature=temperature, thinking=thinking,
                             tools=tools, tool_choice=tool_choice)
        self.n += 1
        if isinstance(reply, str):
            message = {"role": "assistant", "content": reply}
            finish = "stop"
        else:
            message = {"role": "assistant", "content": None,
                       "tool_calls": [tool(c, f"call_{self.n}_{i}") for i, c in enumerate(reply)]}
            finish = "tool_calls"
        prompt = 100 * len(messages)
        hit = 100 * len(self.seen[-2]) if len(self.seen) > 1 else 0   # the previous request is cached
        data = {"model": model, "choices": [{"message": message, "finish_reason": finish}],
                "usage": {"prompt_tokens": prompt, "completion_tokens": 40,
                          "prompt_cache_hit_tokens": hit, "prompt_cache_miss_tokens": prompt - hit,
                          "prompt_tokens_details": {"cached_tokens": hit}}}
        return parse_response(data, request=body, model=model, started_at=T0, latency_s=0.5)


def fake_env_factory(outputs=None, crash=False):
    """mini's real DockerEnvironment (so its own submission check runs), with
    no container. `stopped` records every stop()."""
    m = mini._mini()
    stopped = []

    class FakeEnv(m.DockerEnvironment):
        def _start_container(self):
            self.container_id = "fake-container"

        def execute(self, action, cwd="", *, timeout=None):
            if crash:
                raise RuntimeError("docker died")
            cmd = action["command"]
            if cmd == "submit":
                out = {"output": "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT\n" + (outputs or PATCH),
                       "returncode": 0, "exception_info": ""}
            elif cmd == "submit-empty":
                out = {"output": "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT\n",
                       "returncode": 0, "exception_info": ""}
            else:
                out = {"output": f"ran {cmd}\n", "returncode": 0, "exception_info": ""}
            self._check_finished(out)
            return out

        def stop(self):
            stopped.append(self.container_id)
            self.container_id = None

    def factory(t):
        env_cfg = {k: v for k, v in mini.stock_config()["environment"].items()
                   if k != "environment_class"}
        return FakeEnv(image=t.image, **env_cfg)

    return factory, stopped


def run_normal_attempt():
    provider = ScriptedProvider([["ls"], ["grep -n add mypkg/calc.py", "cat mypkg/calc.py"],
                                 ["submit"]])
    factory, stopped = fake_env_factory()
    return mini.attempt(task(), provider, env_factory=factory), provider, stopped


# ---------------------------------------------------------------- endings

def test_normal_run_submits_a_patch():
    a, provider, stopped = run_normal_attempt()
    assert a.outcome is None and a.patch == PATCH
    assert a.diagnostics["agent_status"] == "Submitted" and a.diagnostics["mini_calls"] == 3
    assert a.diagnostics["localisation"]["all_gold_files_patched"]
    assert a.usage.model_calls == 3 and a.agent_s >= 0
    assert set(a.prompt_hashes) >= {"mini/swebench.yaml", "mini/instance_template", "mini/bash_tool"}
    assert stopped == ["fake-container"]
    # Every request: tools sent, tool_choice explicit, parallel_tool_calls never.
    for c in a.transcript:
        settings = c["request_settings"]
        assert settings["tool_choice"] == "auto" and settings["tools"][0]["function"]["name"] == "bash"
        assert "parallel_tool_calls" not in settings and "request" not in c
    # The delta transcript rebuilds exactly what was sent.
    assert rebuild_requests(a.transcript) == provider.seen
    assert [c["reply_resent"] for c in a.transcript] == [False, True, True]
    # Two tool calls in one reply: both outputs come back as tool messages.
    assert [m["role"] for m in a.transcript[2]["new_messages"]] == ["tool", "tool"]


def test_history_is_append_only_so_the_prefix_can_be_cached():
    _, provider, _ = run_normal_attempt()
    for prev, cur in zip(provider.seen, provider.seen[1:]):
        assert cur[:len(prev)] == prev


def test_limit_breach_mid_run_is_spend_ceiling_and_stops_the_container(tmp_path):
    provider = ScriptedProvider([["ls"], ["ls"], ["ls"], ["submit"]])
    factory, stopped = fake_env_factory()
    a = mini.attempt(task(), provider, limits=mini.LIMITS.model_copy(update={"max_calls": 2}),
                     env_factory=factory)
    assert a.outcome is Outcome.SPEND_CEILING and a.breach.limit == "calls"
    assert a.usage.model_calls == 2 and a.patch == "" and a.agent_s >= 0
    refused = a.transcript[-1]["refused"]
    assert refused["new_messages"] and "messages" not in refused   # delta, not the full history
    assert stopped == ["fake-container"]
    [rec] = build_records("r", "agent:mini", {"t-mini": ""}, tmp_path / "none", ENV,
                          {"patch_source": "agent:mini", **mini.agent_config()}, T0, T0,
                          {"t-mini": a})
    assert rec.schema_version == 3 and rec.timing.agent_s == a.agent_s
    assert read_record(write_record(rec, tmp_path / "records")) == rec


def test_provider_error_mid_run_ends_the_attempt():
    provider = ScriptedProvider([["ls"], ProviderError("HTTP 402: insufficient balance")])
    factory, stopped = fake_env_factory()
    a = mini.attempt(task(), provider, env_factory=factory)
    assert a.outcome is Outcome.PROVIDER_ERROR and a.error.startswith("HTTP 402")
    assert a.usage.model_calls == 1 and stopped == ["fake-container"]


def test_no_tool_calls_three_times_is_empty_patch():
    # mini's FormatError path: the reply is NOT re-sent, only the error message.
    provider = ScriptedProvider(["I think it is fine.", "Still fine.", "Done."])
    factory, stopped = fake_env_factory()
    a = mini.attempt(task(), provider, env_factory=factory)
    assert a.outcome is Outcome.EMPTY_PATCH
    assert a.diagnostics["agent_status"] == "RepeatedFormatError"
    assert a.usage.model_calls == 3 and a.diagnostics["mini_cost_usd"] > 0
    assert [c["reply_resent"] for c in a.transcript] == [False, False, False]
    assert rebuild_requests(a.transcript) == provider.seen
    assert stopped == ["fake-container"]


def test_empty_submission_is_empty_patch():
    provider = ScriptedProvider([["submit-empty"]])
    factory, stopped = fake_env_factory()
    a = mini.attempt(task(), provider, env_factory=factory)
    assert a.outcome is Outcome.EMPTY_PATCH and a.diagnostics["agent_status"] == "Submitted"
    assert stopped == ["fake-container"]


def test_container_is_stopped_when_the_attempt_crashes():
    provider = ScriptedProvider([["ls"]])
    factory, stopped = fake_env_factory(crash=True)
    with pytest.raises(RuntimeError, match="docker died"):
        mini.attempt(task(), provider, env_factory=factory)
    assert stopped == ["fake-container"]


# ---------------------------------------------------------------- accountant

def acct(provider, mode="delta"):
    return Accountant(provider, mini.LIMITS, model="deepseek-flash", transcript=mode)


SYS = [{"role": "system", "content": "s"}, {"role": "user", "content": "task"}]
ARGS = dict(max_tokens=4096, temperature=0.0, thinking="disabled")
TOOLS = dict(tools=[{"type": "function", "function": {"name": "bash"}}], tool_choice="auto")


def test_a_changed_history_is_refused_before_sending():
    p = ScriptedProvider([["ls"], ["ls"]])
    a = acct(p)
    c = a.complete(SYS, **ARGS, **TOOLS)
    edited = [{"role": "system", "content": "EDITED"}, SYS[1], reply_message(c.response)]
    with pytest.raises(TranscriptMismatch, match="previous request"):
        a.complete(edited, **ARGS, **TOOLS)
    changed_reply = SYS + [{**reply_message(c.response), "content": "rewritten"}]
    with pytest.raises(TranscriptMismatch, match="re-sent changed"):
        a.complete(changed_reply, **ARGS, **TOOLS)
    assert len(p.seen) == 1                      # nothing was sent for either


def test_prefix_aware_estimate():
    p = ScriptedProvider([["ls"]])
    a = acct(p)
    c = a.complete(SYS, **ARGS, **TOOLS)         # reported input: 200 tokens
    nxt = SYS + [reply_message(c.response),
                 {"role": "tool", "tool_call_id": "call_1_0", "content": "x" * 1000}]
    assert a.estimate_input(nxt, TOOLS["tools"]) == (
        c.usage.input_tokens + prompt_bytes(nxt[len(SYS):]))
    # A history that does not start with the previous request: bytes, as before.
    other = [{"role": "user", "content": "y" * 50}]
    assert a.estimate_input(other, TOOLS["tools"]) == prompt_bytes(other, TOOLS["tools"])


def test_prompt_bytes_counts_tool_calls_and_survives_null_content():
    m = [{"role": "assistant", "content": None, "tool_calls": [tool("ls", "c1")]},
         {"role": "tool", "tool_call_id": "c1", "content": "out"}]
    assert prompt_bytes(m) == len(json.dumps(m[0]["tool_calls"])) + len("c1") + len("out")


# ---------------------------------------------------------------- agent:simple unchanged

def simple_fixed_messages():
    return simple.build_messages(
        simple.load_prompts(), tree="mypkg/\n  calc.py\n",
        files="### FILE: mypkg/calc.py\ndef add(a, b):\n    return {'x': a - b}  # é\n"
              "### END FILE: mypkg/calc.py",
        issue="add() subtracts instead of adding {see calc.py} — naïve bug")


def test_simple_request_is_byte_identical_to_before_the_adapter_change():
    base = json.loads((FIX / "simple_request_baseline.json").read_text())
    msgs = simple_fixed_messages()
    body = build_request(msgs, model="deepseek-flash", **simple.SETTINGS)
    assert json.dumps(body) == base["body_json"]
    assert prompt_bytes(msgs) == base["prompt_bytes"]           # its limit checks too
    assert simple.prompt_hashes(simple.load_prompts()) == base["prompt_hashes"]


def test_simple_full_transcript_is_unchanged_in_shape():
    p = ScriptedProvider(["no tools here"])
    a = Accountant(p, Limits(), model="deepseek-flash")         # default: full
    a.complete(simple_fixed_messages(), **ARGS)
    [entry] = a.transcript()
    assert "request" in entry and "new_messages" not in entry
    assert "tools" not in entry["request"]


# ---------------------------------------------------------------- install and config

def test_pins_come_from_requirements_file_and_all_three_are_checked():
    pins = mini.pinned_versions()
    assert pins == {"mini-swe-agent": "2.4.6", "jinja2": "3.1.6", "markupsafe": "3.0.4"}
    assert mini.check_pins() == pins
    for name in pins:
        with pytest.raises(mini.MiniSetupError, match=name):
            mini.check_pins(lambda n, bad=name: "0.0" if n == bad else pins[n])


def test_heavy_dependencies_are_never_imported():
    # A fresh interpreter: import the driver and run a whole attempt.
    code = ("import sys; sys.path.insert(0, 'tests'); import test_mini; "
            "a, _, _ = test_mini.run_normal_attempt(); assert a.outcome is None; "
            "bad = [m for m in ('litellm', 'openai', 'textual') if m in sys.modules]; "
            "assert not bad, bad; print('clean')")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         cwd=Path(__file__).parents[1])
    assert out.returncode == 0 and "clean" in out.stdout, out.stderr[-2000:]


def test_config_records_both_limit_sets_and_ours_are_tighter():
    cfg = mini.agent_config()
    ours, theirs = cfg["limits"], cfg["mini_limits"]
    assert ours["max_calls"] < theirs["step_limit"]
    assert ours["max_cost_usd"] < theirs["cost_limit"]
    assert theirs["wall_time_limit_seconds"] == 0 and ours["max_wall_clock_s"] == 1200.0
    assert cfg["settings"] == {**simple.SETTINGS, "tool_choice": "auto"}
    from blindspots.agent.attempt import agent_config
    assert config_hash(cfg) != config_hash(agent_config(Limits()))


def test_tools_need_an_explicit_tool_choice():
    with pytest.raises(ProviderError, match="together"):
        build_request(SYS, model="deepseek-flash", **ARGS, tools=TOOLS["tools"])
    with pytest.raises(ProviderError, match="tool_choice"):
        build_request(SYS, model="deepseek-flash", **ARGS, tools=TOOLS["tools"],
                      tool_choice="required")


def test_cache_bust_is_refused_for_mini():
    from blindspots.run import RunnerError, main
    with pytest.raises(RunnerError, match="agent:simple"):
        main(["--run-id", "x", "--source", "agent:mini", "--cache-bust"])


def test_transcript_mismatch_writes_a_crash_dump_then_aborts(tmp_path, monkeypatch):
    # A genuine mismatch: the model class hands mini an altered reply, which
    # mini re-sends on call 2; the accountant checks against the real one.
    real = mini.reply_message
    monkeypatch.setattr(mini, "reply_message", lambda r: {**real(r), "content": "tampered"})
    provider = ScriptedProvider([["ls"], ["submit"]])
    factory, stopped = fake_env_factory()
    crashes = tmp_path / "crashes" / "r"
    with pytest.raises(TranscriptMismatch, match="re-sent changed"):
        mini.attempt(task(), provider, env_factory=factory, crash_dir=crashes)
    dump = json.loads((crashes / "t-mini.crash.json").read_text())
    assert dump["error"].startswith("TranscriptMismatch")
    assert dump["usage"]["model_calls"] == 1 and dump["usage"]["cost_usd"] > 0
    assert len(dump["transcript"]) == 1 and "new_messages" in dump["transcript"][0]
    assert dump["agent_s"] >= 0
    assert len(provider.seen) == 1                 # call 2 was never sent
    assert stopped == ["fake-container"]
    # Outside records/: a summary of the records never sees it.
    from blindspots.summarise import load
    (tmp_path / "records").mkdir()
    assert load(tmp_path / "records") == []
