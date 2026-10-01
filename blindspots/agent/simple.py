"""The simplest agent (Week 2 step 3): one call, no roles, no loop.

    issue + trimmed tree + chosen files  ->  one model call  ->  edit blocks
    ->  our code builds the diff  ->  `git apply --check`  ->  patch

Prompt layout (step 3, decision 3), stable parts first so they can be cached:

    [1] system       prompts/simple/system.txt       same for every task
    [2] user         prompts/simple/context.txt      same for every repeat of a task
    [3] user         prompts/simple/issue.txt        same for every repeat of a task
    [4] user         prompts/simple/instruction.txt  the only role-specific part

Parts 1-3 are what December's five roles will share; each role changes only
part 4. Nothing that varies between runs (time, run ID) appears anywhere --
except the cache-bust marker below, which exists to break exactly that.

Cache busting (Week 3 item 4). DeepSeek caching is automatic and cannot be
switched off [PRIMARY -- context-caching guide], and it matches prompts from
the first token. So the "caching disabled" condition puts a fresh random
marker at the very start of the system message: no earlier prompt shares
even its first token block, so nothing can be served from cache. The marker
is per attempt, not per run, so attempts within one run cannot warm each
other either. Whether it worked is checked, not assumed: a busted attempt
must report zero cache-hit tokens on every call.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from blindspots.accountant import Accountant
from blindspots.agent import context as ctx
from blindspots.agent import edits
from blindspots.agent.workspace import Task, repo_files

PROMPT_DIR = Path(__file__).resolve().parents[2] / "prompts" / "simple"
PARTS = ("system", "context", "issue", "instruction")

# Call settings for Week 2 (ADR-0013: always explicit, part of the config hash).
SETTINGS = {"max_tokens": 4096, "temperature": 0.0, "thinking": "disabled"}


def load_prompts(prompt_dir: Path = PROMPT_DIR) -> dict[str, str]:
    return {p: (prompt_dir / f"{p}.txt").read_text(encoding="utf-8") for p in PARTS}


def prompt_hashes(prompts: dict[str, str]) -> dict[str, str]:
    """SHA-256 of each prompt file's text (ADR-0008: recorded in every run)."""
    return {f"simple/{p}": hashlib.sha256(t.encode("utf-8")).hexdigest()
            for p, t in sorted(prompts.items())}


def fill(template: str, **values: str) -> str:
    """Replace {name} placeholders in one pass. Not str.format: file contents
    and issues are full of braces, which format() would try to interpret."""
    return re.sub(r"\{(\w+)\}", lambda m: values.get(m.group(1), m.group(0)), template)


def render_files(repo_dir: Path, paths: list[str]) -> str:
    blocks = []
    for p in paths:
        text = (repo_dir / p).read_text(encoding="utf-8", errors="replace")
        blocks.append(f"### FILE: {p}\n{text}{'' if text.endswith(chr(10)) else chr(10)}"
                      f"### END FILE: {p}")
    return "\n\n".join(blocks)


def cache_bust_marker() -> str:
    """128 random bits. The random hex comes first so the prompt's first
    tokens differ; the explanation after it stops the model reading meaning
    into it."""
    return f"{secrets.token_hex(16)} (cache-bust marker: ignore this line)\n\n"


def build_messages(prompts: dict[str, str], tree: str, files: str,
                   issue: str, marker: str = "") -> list[dict[str, str]]:
    return [
        {"role": "system", "content": marker + prompts["system"]},
        {"role": "user", "content": fill(prompts["context"], tree=tree, files=files)},
        {"role": "user", "content": fill(prompts["issue"], issue=issue)},
        {"role": "user", "content": prompts["instruction"]},
    ]


@dataclass
class AgentResult:
    patch: str                      # "" if no usable edit
    status: str                     # "patch", "no_edits", "edit_failed", "diff_failed"
    error: str | None
    reply: str                      # the model's raw text, always kept
    selection: dict[str, Any]       # which files, why, and what was skipped
    prompt_hashes: dict[str, str]
    diagnostics: dict[str, Any] = field(default_factory=dict)


def solve(task: Task, repo_dir: Path, acct: Accountant, *,
          prompt_dir: Path = PROMPT_DIR, cache_bust: bool = False) -> AgentResult:
    """One attempt at one task. LimitBreached and ProviderError propagate:
    the runner turns them into spend_ceiling / wall_clock_limit /
    provider_error records with the accountant's partial transcript."""
    prompts = load_prompts(prompt_dir)
    hashes = prompt_hashes(prompts)
    all_files = repo_files(repo_dir)
    sel = ctx.select(repo_dir, all_files, task.problem_statement)
    marker = cache_bust_marker() if cache_bust else ""
    messages = build_messages(prompts, ctx.tree(all_files, sel.files),
                              render_files(repo_dir, sel.files), task.problem_statement,
                              marker)
    selection = {"files": sel.files, "content_bytes": sel.content_bytes,
                 "skipped_for_budget": sel.skipped_for_budget,
                 "reasons": {f: sel.reasons[f] for f in sel.files}}

    reply = acct.complete(messages, **SETTINGS).content

    def result(patch, status, error=None):
        # Localisation diagnostic: computed now, AFTER the call, from the gold
        # patch. It is stored, never shown to the model.
        diag = {"localisation": ctx.localisation(task.gold_patch, sel.files)}
        if cache_bust:
            diag["cache_bust_marker"] = marker.split()[0]
        return AgentResult(patch, status, error, reply, selection, hashes, diag)

    blocks = edits.parse(reply)
    if not blocks:
        return result("", "no_edits")
    try:
        changes = edits.apply(repo_dir, blocks)
    except edits.EditError as e:
        return result("", "edit_failed", str(e))
    patch = edits.to_diff(changes)
    if not patch:
        return result("", "no_edits", "edit blocks changed nothing")
    problem = edits.check_applies(repo_dir, patch)
    if problem:
        return result("", "diff_failed", f"our diff did not apply: {problem}")
    return result(patch, "patch")
