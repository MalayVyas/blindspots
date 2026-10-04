"""agent:mini: stock mini-swe-agent 2.4.6, our transport (ADR-0018).

mini's own SWE-bench config, prompts, agent loop, tool definition, action
parser, observation formatter and Docker environment are used unchanged.
Only the model call is ours: AccountedModel sends it through the token
accountant and the DeepSeek adapter, so cost, cache hits and limits are
measured exactly as for agent:simple.

    container started from the task image (preparation, not timed)
    -> DefaultAgent.run(issue): model call -> bash command(s) -> output -> ...
    -> "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT" + patch   (mini's submission)
    -> container removed (always, in a finally)

mini is installed without dependencies (scripts/install_mini.sh); nothing
here imports litellm, openai or textual.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from blindspots.accountant import (
    Accountant, LimitBreached, Limits, TranscriptMismatch, outcome_for)
from blindspots.agent import simple
from blindspots.agent.attempt import Attempt
from blindspots.agent.workspace import Task
from blindspots.providers.base import ProviderError, reply_message
from blindspots.record import Outcome

MODEL = "deepseek-flash"
MINI_VERSION = "2.4.6"
REQUIREMENTS = Path(__file__).resolve().parents[2] / "requirements-mini.txt"

# Same model settings as agent:simple (ADR-0018 decision 2); tool_choice is
# sent explicitly because tools are (ADR-0013).
SETTINGS = dict(simple.SETTINGS)
TOOL_CHOICE = "auto"

# Our limits for agent:mini [ESTIMATE — sizing in ADR-0018]. mini's own
# (250 steps, $3, no time limit) are looser and stay stock.
LIMITS = Limits(max_calls=75, max_input_tokens=5_000_000, max_output_tokens=40_000,
                max_wall_clock_s=1200.0, max_cost_usd=0.10)

# No network in the agent's container (ADR-0018 amendment, 2026-10-04).
# mini's own default is ["--rm"]; this keeps it and adds no network. In
# ci-mini-1, 2 of 5 attempts downloaded newer releases or cloned upstream
# and read the fix. Passed through mini's own DockerEnvironment setting.
RUN_ARGS = ["--rm", "--network", "none"]

# Commands that try to reach outside the task (the tripwire diagnostic).
OUTSIDE = re.compile(
    r"\b(?:pip3?|python3?\s+-m\s+pip|uv\s+pip)\s+(?:install|download)\b"
    r"|\bgit\s+(?:-\S+\s+)*(?:clone|fetch|pull)\b"
    r"|\bcurl\b|\bwget\b|\b(?:https?|ftp)://|\bgit@[\w.-]+:")


class MiniSetupError(RuntimeError):
    """mini is missing, or not exactly the pinned version: refuse at $0."""


# ---------------------------------------------------------------- install

def pinned_versions(path: Path = REQUIREMENTS) -> dict[str, str]:
    """name -> version for every `name==version` line in requirements-mini.txt,
    the one place these pins are written."""
    pins = dict(re.findall(r"^([A-Za-z0-9._-]+)==([^\s\\]+)", path.read_text(), re.M))
    if not pins:
        raise MiniSetupError(f"no pins found in {path}")
    return pins


def check_pins(installed: Callable[[str], str] = version) -> dict[str, str]:
    """Refuse unless every pinned package is installed at exactly its pin."""
    pins = pinned_versions()
    wrong = []
    for name, want in pins.items():
        try:
            have = installed(name)
        except PackageNotFoundError:
            have = "not installed"
        if have != want:
            wrong.append(f"{name} {have} (need {want})")
    if wrong:
        raise MiniSetupError("agent:mini needs the pinned packages: " + "; ".join(wrong)
                             + ". Run scripts/install_mini.sh")
    return pins


@lru_cache(maxsize=1)
def _mini() -> SimpleNamespace:
    """Import mini once, after the pin check, with no user config in reach.

    mini creates its global config folder and loads a .env from it on
    import; pointing it at a fresh empty folder keeps a stray setting from
    changing a run. Its startup banner is silenced.
    """
    check_pins()
    os.environ["MSWEA_SILENT_STARTUP"] = "1"
    os.environ["MSWEA_GLOBAL_CONFIG_DIR"] = tempfile.mkdtemp(prefix="bs-mini-config-")
    from minisweagent.agents.default import DefaultAgent
    from minisweagent.config import builtin_config_dir
    from minisweagent.environments.docker import DockerEnvironment
    from minisweagent.exceptions import FormatError
    from minisweagent.models.utils.actions_toolcall import (
        BASH_TOOL, format_toolcall_observation_messages, parse_toolcall_actions)
    return SimpleNamespace(
        DefaultAgent=DefaultAgent, DockerEnvironment=DockerEnvironment,
        FormatError=FormatError, BASH_TOOL=BASH_TOOL,
        format_observations=format_toolcall_observation_messages,
        parse_actions=parse_toolcall_actions,
        config_file=builtin_config_dir / "benchmarks" / "swebench.yaml")


# ---------------------------------------------------------------- config

def stock_config() -> dict[str, Any]:
    import yaml
    return yaml.safe_load(_mini().config_file.read_text(encoding="utf-8"))


def _sha(text: str | bytes) -> str:
    return hashlib.sha256(text if isinstance(text, bytes) else text.encode("utf-8")).hexdigest()


def prompt_hashes() -> dict[str, str]:
    """ADR-0008: what the model is shown. The stock config file as a whole,
    each of its four templates, and the bash tool schema sent with every call."""
    m = _mini()
    cfg = stock_config()
    return {
        "mini/swebench.yaml": _sha(m.config_file.read_bytes()),
        "mini/system_template": _sha(cfg["agent"]["system_template"]),
        "mini/instance_template": _sha(cfg["agent"]["instance_template"]),
        "mini/observation_template": _sha(cfg["model"]["observation_template"]),
        "mini/format_error_template": _sha(cfg["model"]["format_error_template"]),
        "mini/bash_tool": _sha(json.dumps(m.BASH_TOOL, sort_keys=True)),
    }


def mini_limits() -> dict[str, Any]:
    """mini's own limits as its agent will apply them (stock config over the
    class defaults), recorded beside ours."""
    _mini()  # pin check and clean config folder before mini is imported
    from minisweagent.agents.default import AgentConfig
    cfg = AgentConfig(**stock_config()["agent"]).model_dump()
    return {k: cfg[k] for k in ("step_limit", "cost_limit", "wall_time_limit_seconds",
                                "max_consecutive_format_errors")}


def agent_config(limits: Limits = LIMITS) -> dict[str, Any]:
    """Everything that shapes agent:mini, for the config hash."""
    env = stock_config()["environment"]
    return {"agent": "mini", "mini_version": MINI_VERSION, "model": MODEL,
            "settings": {**SETTINGS, "tool_choice": TOOL_CHOICE},
            "limits": limits.model_dump(), "mini_limits": mini_limits(),
            "environment": {**{k: env[k] for k in ("cwd", "timeout", "interpreter")},
                            "run_args": RUN_ARGS}}


# ---------------------------------------------------------------- model

class AccountedModel:
    """mini's Model protocol, with our transport. Everything except the HTTP
    call is mini's own code: tool schema, parser, observation formatter."""

    # The stock config's `model` section also holds litellm's transport
    # settings: model_name (a Claude model) and model_kwargs (drop_params,
    # parallel_tool_calls). Those are what "our transport" replaces, so they
    # are dropped here; the templates are kept unchanged.
    TRANSPORT_KEYS = ("model_name", "model_kwargs")

    def __init__(self, acct: Accountant, model_config: dict[str, Any]):
        self.acct = acct
        kept = {k: v for k, v in model_config.items() if k not in self.TRANSPORT_KEYS}
        self.config = SimpleNamespace(model_name=MODEL, **kept)
        self._m = _mini()

    def query(self, messages: list[dict], **kwargs) -> dict:
        # As the stock model: send everything except mini's bookkeeping key.
        prepared = [{k: v for k, v in m.items() if k != "extra"} for m in messages]
        c = self.acct.complete(prepared, tools=[self._m.BASH_TOOL],
                               tool_choice=TOOL_CHOICE, **SETTINGS)
        message = reply_message(c.response)
        calls = [SimpleNamespace(id=tc.get("id"),
                                 function=SimpleNamespace(**tc.get("function", {})))
                 for tc in message.get("tool_calls", [])]
        try:
            actions = self._m.parse_actions(
                calls, format_error_template=self.config.format_error_template,
                template_kwargs={"finish_reason": c.finish_reason})
        except self._m.FormatError as e:
            # As the stock model: the call was billed, so its cost travels
            # with the error (mini adds it to its own counter).
            e.messages[0]["extra"].update(cost=c.billed_usd)
            raise
        return {**message, "extra": {"actions": actions, "cost": c.billed_usd}}

    def format_message(self, **kwargs) -> dict:
        return kwargs

    def format_observation_messages(self, message: dict, outputs: list[dict],
                                    template_vars: dict | None = None) -> list[dict]:
        return self._m.format_observations(
            actions=message.get("extra", {}).get("actions", []), outputs=outputs,
            observation_template=self.config.observation_template,
            template_vars=template_vars)

    def get_template_vars(self, **kwargs) -> dict[str, Any]:
        return vars(self.config) | kwargs

    def serialize(self) -> dict:
        return {"info": {"config": {"model": {"model_name": MODEL, "transport": "blindspots"}}}}


# ---------------------------------------------------------------- environment

def make_env(task: Task):
    """mini's DockerEnvironment on the task's own image (the one the harness
    uses), with the stock environment settings. Starting it is preparation.

    Adds one method, stop(): a synchronous `docker rm -f`. mini's cleanup()
    stops the container in the background and returns at once, so it cannot
    be checked that the container is gone."""
    m = _mini()

    class MiniEnv(m.DockerEnvironment):
        def stop(self) -> None:
            cid, self.container_id = self.container_id, None   # mini's __del__ then does nothing
            if cid:
                subprocess.run([self.config.executable, "rm", "-f", cid],
                               capture_output=True, timeout=120)

    env_cfg = {k: v for k, v in stock_config()["environment"].items()
               if k != "environment_class"}
    return MiniEnv(image=task.image, run_args=RUN_ARGS, **env_cfg)


# ---------------------------------------------------------------- one attempt

@dataclass
class MiniResult:
    patch: str
    exit_status: str
    mini_calls: int
    mini_cost_usd: float


def solve(task: Task, env, acct: Accountant) -> MiniResult:
    """mini's stock agent on one task. LimitBreached, ProviderError and
    TranscriptMismatch propagate (mini re-raises them after recording)."""
    m = _mini()
    cfg = stock_config()
    agent = m.DefaultAgent(AccountedModel(acct, cfg["model"]), env, **cfg["agent"])
    info = agent.run(task.problem_statement)
    return MiniResult(patch=info.get("submission") or "",
                      exit_status=info.get("exit_status") or "",
                      mini_calls=agent.n_calls, mini_cost_usd=agent.cost)


def outside_reach(transcript: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Tripwire: every command that tried to reach outside the task, with its
    exit status (from mini's <returncode> in the next observation; None if the
    attempt ended before the output came back). Refused and timed-out entries
    are scanned too: when a limit ends the attempt, the last outputs are there."""
    commands, codes = [], {}
    for n, entry in enumerate(transcript, 1):
        body = entry.get("refused") or entry.get("timed_out") or entry
        for m in body.get("new_messages", []):
            if m.get("role") == "tool":
                rc = re.search(r"<returncode>(-?\d+)</returncode>", m.get("content") or "")
                codes[m.get("tool_call_id")] = int(rc.group(1)) if rc else None
        if "response" in entry:
            for tc in entry["response"]["choices"][0]["message"].get("tool_calls") or []:
                try:
                    cmd = json.loads(tc["function"]["arguments"]).get("command", "")
                except (ValueError, KeyError, TypeError, AttributeError):
                    continue
                commands.append((n, tc.get("id"), cmd))
    return [{"call": n, "command": cmd, "returncode": codes.get(tid)}
            for n, tid, cmd in commands if OUTSIDE.search(cmd)]


def _files(patch: str) -> list[str]:
    return sorted(set(re.findall(r"^diff --git a/(\S+) b/", patch, re.M)))


def write_crash_dump(crash_dir: Path, task: Task, acct: Accountant, agent_s: float,
                     error: Exception) -> Path:
    """What an aborted attempt had spent and done, for the record it never got.

    Lives in its own folder, never under records/: summarise reads every
    .json below the folder it is given, and this is not a record."""
    crash_dir.mkdir(parents=True, exist_ok=True)
    path = crash_dir / f"{task.instance_id}.crash.json"
    if path.exists():   # never overwrite (ADR-0011); a second dump gets a suffix
        path = crash_dir / f"{task.instance_id}.{int(time.time())}.crash.json"
    path.write_text(json.dumps({
        "instance_id": task.instance_id, "error": f"{type(error).__name__}: {error}",
        "agent_s": agent_s, "usage": acct.usage().model_dump(),
        "transcript": acct.transcript()}, indent=2), encoding="utf-8")
    return path


def attempt(task: Task, provider, limits: Limits = LIMITS,
            env_factory: Callable[[Task], Any] = make_env,
            crash_dir: Path | None = None) -> Attempt:
    started = datetime.now(timezone.utc)
    hashes = prompt_hashes()
    env = env_factory(task)                      # container start: preparation, not timed
    try:
        t0 = time.monotonic()
        acct = Accountant(provider, limits, model=MODEL, transcript="delta")

        def done(agent_s: float, diagnostics: dict | None = None, **kw) -> Attempt:
            transcript = acct.transcript()
            diag = {**(diagnostics or {}), "outside_reach": outside_reach(transcript)}
            return Attempt(instance_id=task.instance_id, usage=acct.usage(),
                           transcript=transcript, prompt_hashes=hashes,
                           started_at=started, finished_at=datetime.now(timezone.utc),
                           agent_s=agent_s, diagnostics=diag, **kw)

        try:
            res = solve(task, env, acct)
        except LimitBreached as e:
            return done(time.monotonic() - t0, patch="", outcome=outcome_for(e.breach),
                        breach=e.breach, error=str(e))
        except ProviderError as e:
            return done(time.monotonic() - t0, patch="", outcome=Outcome.PROVIDER_ERROR,
                        error=str(e))
        except TranscriptMismatch as e:
            # Our bug, not an outcome: dump what was spent, then abort loudly.
            if crash_dir is not None:
                path = write_crash_dump(crash_dir, task, acct, time.monotonic() - t0, e)
                print(f"  crash dump: {path}")
            raise
        agent_s = time.monotonic() - t0

        # Read the gold patch only now, after the attempt, as agent:simple does.
        patched, gold = _files(res.patch), _files(task.gold_patch)
        diag = {"agent_status": res.exit_status, "mini_calls": res.mini_calls,
                "mini_cost_usd": res.mini_cost_usd,
                "localisation": {"patched_files": patched, "gold_files": gold,
                                 "all_gold_files_patched": set(gold) <= set(patched)}}
        if res.exit_status == "Submitted" and res.patch.strip():
            return done(agent_s, patch=res.patch, outcome=None, diagnostics=diag)
        # No submission (repeated format errors, or one of mini's own limits,
        # which cannot fire before ours) or an empty one.
        return done(agent_s, patch="", outcome=Outcome.EMPTY_PATCH, diagnostics=diag,
                    error=f"mini ended with {res.exit_status or 'no exit status'} "
                          "and no patch")
    finally:
        env.stop()
