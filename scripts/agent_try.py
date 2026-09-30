"""Week 2 step 3: look at what the simple agent does on one dev task.

    python scripts/agent_try.py                         # dev task 1
    python scripts/agent_try.py --dry                   # stop before the model call ($0)
    python scripts/agent_try.py sphinx-doc__sphinx-8621

Copies the repository out of the task's Docker image (Docker Desktop must
be running), chooses files, makes ONE model call through the accountant
(ADR-0014 limits), and turns the reply into a patch. It does NOT run the
tests: scoring the patch is step 4, through the runner and the harness.

Saves everything (prompt, reply, patch, selection, usage) to
~/bs-work/agent-try/ for inspection. The gold patch is read only after
the call, for the localisation diagnostic.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("HF_DATASETS_OFFLINE", "1")  # before `datasets` is imported

from blindspots import pricing  # noqa: E402
from blindspots.accountant import Accountant, LimitBreached, Limits, prompt_bytes  # noqa: E402
from blindspots.agent import context as ctx, simple  # noqa: E402
from blindspots.agent.workspace import load_task, prepare, repo_files  # noqa: E402
from blindspots.run import DEFAULT_SPLIT, load_instance_ids  # noqa: E402

WORK = Path.home() / "bs-work"
MODEL = "deepseek-flash"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("instance", nargs="?", default=load_instance_ids(DEFAULT_SPLIT)[0])
    ap.add_argument("--dry", action="store_true", help="choose files and build the prompt only")
    args = ap.parse_args()
    if args.instance not in load_instance_ids(DEFAULT_SPLIT):
        raise SystemExit(f"refused: {args.instance} is not in the dev split")

    task = load_task(args.instance)
    repo = prepare(task, WORK / "repos")
    files = repo_files(repo)
    sel = ctx.select(repo, files, task.problem_statement)
    print(f"{task.instance_id}: {len(files)} tracked files; repo copy at {repo}")
    print(f"chosen ({sel.content_bytes:,} bytes):")
    for f in sel.files:
        print(f"  {f:60} {sel.scores[f]:6.1f}  {', '.join(sel.reasons[f][:3])}")
    if sel.skipped_for_budget:
        print(f"skipped for budget: {sel.skipped_for_budget[:5]}")

    prompts = simple.load_prompts()
    msgs = simple.build_messages(prompts, ctx.tree(files, sel.files),
                                 simple.render_files(repo, sel.files), task.problem_statement)
    est = prompt_bytes(msgs)
    worst = pricing.worst_case_usd(MODEL, input_tokens=est,
                                   output_tokens=simple.SETTINGS["max_tokens"])
    print(f"prompt: {est:,} bytes; worst case ${worst:.4f} (cap ${Limits().max_cost_usd})")
    if args.dry:
        return 0

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = WORK / "agent-try" / f"{task.instance_id}-{stamp}.json"
    out.parent.mkdir(parents=True, exist_ok=True)

    from blindspots.providers.deepseek import DeepSeek
    with DeepSeek() as ds:
        acct = Accountant(ds, Limits(), model=MODEL)
        try:
            res = simple.solve(task, repo, acct)
        except LimitBreached as e:
            print(f"STOPPED by the accountant: {e}")
            out.write_text(json.dumps({"breach": e.breach.model_dump(),
                                       "transcript": acct.transcript()}, indent=2))
            print(f"saved {out}")
            return 1

    u = acct.usage()
    print(f"\ncall: in {u.input_tokens:,} tokens (cached {u.cached_input_tokens:,}; "
          f"bytes/token {est / max(u.input_tokens, 1):.2f}), out {u.output_tokens}")
    print(f"cost: billed ${u.cost_usd:.5f}  reference ${u.reference_usd:.5f}")
    print(f"status: {res.status}" + (f" — {res.error}" if res.error else ""))
    loc = res.diagnostics["localisation"]
    print(f"localisation: gold files {loc['gold_files']}, shown {loc['gold_files_shown']}")
    print("\n--- patch ---\n" + (res.patch or "(none)"))
    out.write_text(json.dumps({
        "instance_id": task.instance_id, "status": res.status, "error": res.error,
        "patch": res.patch, "reply": res.reply, "selection": res.selection,
        "prompt_hashes": res.prompt_hashes, "diagnostics": res.diagnostics,
        "usage": u.model_dump(), "transcript": acct.transcript()}, indent=2))
    print(f"\nsaved {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
