"""Run the agent on each task, one job per task (Week 2 step 4).

Each task gets its own Accountant, so every limit in ADR-0014 is per task.
Whatever happens, the attempt comes back as data for the run record:

    agent produced a patch         -> outcome decided later by the harness
    agent produced no edit blocks  -> empty_patch
    blocks did not apply           -> patch_apply_failed (our code, not the harness)
    a limit stopped the job        -> spend_ceiling / wall_clock_limit
    the model API failed           -> provider_error

Nothing is retried (ADR-0009).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from blindspots.accountant import Accountant, LimitBreached, Limits, outcome_for
from blindspots.agent import context as ctx
from blindspots.agent import simple
from blindspots.agent.workspace import Task, prepare
from blindspots.providers.base import ProviderError
from blindspots.record import Breach, Outcome, Usage

MODEL = "deepseek-flash"


@dataclass
class Attempt:
    instance_id: str
    patch: str
    outcome: Outcome | None          # None: the harness decides
    usage: Usage
    transcript: list[dict[str, Any]]
    prompt_hashes: dict[str, str]
    started_at: datetime
    finished_at: datetime
    breach: Breach | None = None
    error: str | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)


def agent_config(limits: Limits) -> dict[str, Any]:
    """Everything that shapes the agent's behaviour, for the config hash."""
    return {"agent": "simple", "model": MODEL, "settings": dict(simple.SETTINGS),
            "limits": limits.model_dump(),
            "selection": {"content_budget_bytes": ctx.CONTENT_BUDGET_BYTES,
                          "tree_budget_bytes": ctx.TREE_BUDGET_BYTES,
                          "max_files": ctx.MAX_FILES}}


def attempt(task: Task, provider, limits: Limits, repos_root: Path) -> Attempt:
    started = datetime.now(timezone.utc)
    repo = prepare(task, repos_root)
    acct = Accountant(provider, limits, model=MODEL)
    hashes = simple.prompt_hashes(simple.load_prompts())

    def done(**kw) -> Attempt:
        return Attempt(instance_id=task.instance_id, usage=acct.usage(),
                       transcript=acct.transcript(), prompt_hashes=hashes,
                       started_at=started, finished_at=datetime.now(timezone.utc), **kw)

    try:
        res = simple.solve(task, repo, acct)
    except LimitBreached as e:
        return done(patch="", outcome=outcome_for(e.breach), breach=e.breach, error=str(e))
    except ProviderError as e:
        return done(patch="", outcome=Outcome.PROVIDER_ERROR, error=str(e))

    diag = {"agent_status": res.status, "selection": res.selection, **res.diagnostics}
    if res.status == "patch":
        return done(patch=res.patch, outcome=None, diagnostics=diag)
    if res.status == "no_edits":
        return done(patch="", outcome=Outcome.EMPTY_PATCH, error=res.error, diagnostics=diag)
    return done(patch="", outcome=Outcome.PATCH_APPLY_FAILED, error=res.error, diagnostics=diag)


def attempt_all(tasks: list[Task], provider, limits: Limits, repos_root: Path,
                report: Callable[[Attempt], None] = lambda a: None) -> dict[str, Attempt]:
    out = {}
    for t in tasks:
        a = attempt(t, provider, limits, repos_root)
        report(a)
        out[t.instance_id] = a
    return out
