"""Run the harness on a set of tasks and write one record per task.

    python -m blindspots.run --run-id dev-gold-2 --source gold

Sources: gold, empty, noop (controls, $0) and agent:simple (Week 2 step 4:
the simple agent writes the patch, spending real money under the ADR-0014
limits). See ADR-0011.

    python -m blindspots.run --run-id dev-agent-1 --source agent:simple --instances django__django-13343
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
from datetime import datetime
from importlib.metadata import version
from pathlib import Path

from blindspots import harness
from blindspots.record import (
    Environment, Outcome, RunRecord, Timing, config_hash, write_record,
)

REPO = Path(__file__).resolve().parents[1]
DEFAULT_SPLIT = REPO / "splits" / "dev_split.json"
DEFAULT_WORKDIR = Path.home() / "bs-work"
HF_CACHE = Path.home() / ".cache/huggingface/datasets/SWE-bench___swe-bench_verified/default/0.0.0"

# Negative control (results.md entry #2): applies cleanly, changes no code.
NOOP_PATCH = (
    "diff --git a/BLINDSPOTS_NOOP.txt b/BLINDSPOTS_NOOP.txt\n"
    "new file mode 100644\n"
    "--- /dev/null\n"
    "+++ b/BLINDSPOTS_NOOP.txt\n"
    "@@ -0,0 +1 @@\n"
    "+Negative control: this patch changes no code.\n"
)
SOURCES = ("gold", "empty", "noop", "agent:simple")
AGENT_SOURCES = ("agent:simple",)


class RunnerError(RuntimeError):
    """A reason to refuse to start, or to refuse to trust the result."""


# ---------------------------------------------------------------- inputs

def load_instance_ids(split_path: Path) -> list[str]:
    return json.loads(Path(split_path).read_text())["instance_ids"]


def select_instances(split_ids: list[str], requested: list[str] | None) -> list[str]:
    """All tasks in the split, or the requested subset of it.

    A requested task that is not in the split is refused: the split file
    stays the single source of truth for which tasks exist.
    """
    if not requested:
        return split_ids
    outside = [i for i in requested if i not in split_ids]
    if outside:
        raise RunnerError(f"not in the split: {outside}")
    return [i for i in split_ids if i in requested]


def gold_patches(instance_ids: list[str]) -> dict[str, str]:
    """The reference fixes, read from the cached dataset (offline)."""
    from datasets import load_dataset  # imported late: needs the offline flag set first

    ds = load_dataset(harness.DATASET, split="test")
    found = {r["instance_id"]: r["patch"] for r in ds if r["instance_id"] in set(instance_ids)}
    missing = set(instance_ids) - found.keys()
    if missing:
        raise RunnerError(f"not in {harness.DATASET}: {sorted(missing)}")
    return found


def patches_for(source: str, instance_ids: list[str]) -> dict[str, str]:
    if source == "gold":
        return gold_patches(instance_ids)
    if source == "empty":
        return {i: "" for i in instance_ids}
    if source == "noop":
        return {i: NOOP_PATCH for i in instance_ids}
    raise RunnerError(f"unknown source {source!r}; expected one of {SOURCES}")


def write_predictions(path: Path, source: str, patches: dict[str, str]) -> Path:
    """JSONL: one object per line, the format the harness reads."""
    # The harness uses model_name_or_path as a folder name under logs/.
    # GitHub's artifact upload rejects ':' in paths, so "agent:simple"
    # becomes "agent-simple" there.
    name = source.replace(":", "-")
    with open(path, "w") as f:
        for iid, patch in patches.items():
            f.write(json.dumps({"instance_id": iid, "model_name_or_path": name,
                                "model_patch": patch}) + "\n")
    return path


# ---------------------------------------------------------------- checks

def preflight(workdir: Path, records_root: Path, run_id: str) -> None:
    """Refuse to start rather than produce a record that cannot be trusted."""
    if (Path(records_root) / run_id).exists():
        raise RunnerError(f"records for {run_id} already exist; use a new run ID")
    # The harness silently skips tasks that already have a report under the
    # same run ID. Old reports would then be read as new ones.
    if list((Path(workdir) / "logs").glob(f"**/{run_id}")):
        raise RunnerError(f"harness logs for {run_id} already exist; use a new run ID")


def docker_version() -> str | None:
    try:
        out = subprocess.run(["docker", "version", "--format", "{{.Server.Version}}"],
                             capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def git_commit() -> str:
    """HEAD of this repository, marked -dirty if there are uncommitted changes."""
    def git(*args):
        return subprocess.run(["git", "-C", str(REPO), *args],
                              capture_output=True, text=True).stdout.strip()
    commit = git("rev-parse", "HEAD") or "unknown"
    return commit + ("-dirty" if git("status", "--porcelain") else "")


def dataset_revision() -> str | None:
    """The cached revision folder, if exactly one exists."""
    revs = [p.name for p in HF_CACHE.glob("*") if p.is_dir()]
    return revs[0] if len(revs) == 1 else None


def capture_environment(docker: str | None) -> Environment:
    return Environment(
        blindspots_commit=git_commit(),
        swebench_version=version("swebench"),
        dataset_name=harness.DATASET,
        dataset_revision=dataset_revision(),
        python_version=platform.python_version(),
        docker_version=docker,
        machine="ci" if os.environ.get("GITHUB_ACTIONS") == "true" else "local",
    )


# ---------------------------------------------------------------- records

def build_records(run_id: str, source: str, patches: dict[str, str],
                  workdir: Path, env: Environment, config: dict,
                  run_start: datetime, run_end: datetime,
                  attempts: dict | None = None) -> list[RunRecord]:
    """One record per task. `attempts` (agent sources only) carries each task's
    usage, transcript, prompt hashes and any outcome decided before scoring."""
    logs = Path(workdir) / "logs"
    whole_run = Timing(started_at=run_start, finished_at=run_end)
    attempts = attempts or {}
    records = []
    for iid, patch in patches.items():
        common = dict(run_id=run_id, instance_id=iid, patch_source=source,
                      config=config, config_hash=config_hash(config),
                      patch=patch, environment=env)
        a = attempts.get(iid)
        if a is not None:
            common.update(model=config.get("model"), usage=a.usage, transcript=a.transcript,
                          prompt_hashes=a.prompt_hashes, diagnostics=a.diagnostics)
            if a.outcome is not None:
                # Decided before scoring: a limit, an API failure, or no usable edit.
                # The harness never saw this task.
                records.append(RunRecord(**common, outcome=a.outcome, tests=None,
                                         timing=Timing(started_at=a.started_at,
                                                       finished_at=a.finished_at),
                                         breach=a.breach, error=a.error))
                continue
        if not patch.strip():
            # The harness never evaluates empty patches (results.md entry #2).
            records.append(RunRecord(**common, outcome=Outcome.EMPTY_PATCH,
                                     tests=None, timing=whole_run))
            continue
        report = harness.find_task_file(logs, run_id, iid, "report.json")
        log = harness.find_task_file(logs, run_id, iid, "run_instance.log")
        timing = harness.parse_timing(log) if log else whole_run
        if report is None:
            records.append(RunRecord(
                **common, outcome=Outcome.HARNESS_ERROR, tests=None, timing=timing,
                harness_log=str(log) if log else None,
                error=f"no report.json; see harness.{run_id}.out"))
            continue
        outcome, suite = harness.read_report(report, iid, log)
        records.append(RunRecord(**common, outcome=outcome, tests=suite,
                                 timing=timing, harness_log=str(log)))
    return records


def check_against_summary(records: list[RunRecord], summary: dict) -> None:
    """Two independent readings of the same run must agree."""
    ours = {r.instance_id for r in records if r.outcome is Outcome.RESOLVED}
    theirs = set(summary.get("resolved_ids", []))
    if ours != theirs:
        raise RunnerError(f"records say resolved {sorted(ours)}, "
                          f"harness summary says {sorted(theirs)}")


# ---------------------------------------------------------------- agent

def run_agent(ids: list[str], workdir: Path, cache_bust: bool = False) -> dict:
    """Prepare every workspace first, so a Docker or commit problem stops the
    run before any money is spent; then one agent job per task."""
    from blindspots.accountant import Limits
    from blindspots.agent.attempt import attempt_all
    from blindspots.agent.workspace import WorkspaceError, load_tasks, prepare
    from blindspots.providers.base import ProviderError
    from blindspots.providers.deepseek import DeepSeek

    repos = Path(workdir) / "repos"
    try:
        tasks = load_tasks(ids)
        for t in tasks:
            prepare(t, repos)
        provider = DeepSeek()  # refuses here, at $0, if the key is missing
    except (WorkspaceError, ProviderError) as e:
        raise RunnerError(str(e)) from e

    def report(a):
        status = a.outcome.value if a.outcome else a.diagnostics.get("agent_status")
        print(f"  agent {a.instance_id:28} {status:18} ${a.usage.cost_usd:.5f}  "
              f"{a.usage.input_tokens:,} in / {a.usage.output_tokens:,} out")

    with provider:
        return attempt_all(tasks, provider, Limits(), repos, report, cache_bust=cache_bust)


# ---------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m blindspots.run", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-id", required=True, help="new, unique name for this run")
    ap.add_argument("--source", required=True, choices=SOURCES)
    ap.add_argument("--split", type=Path, default=DEFAULT_SPLIT)
    ap.add_argument("--workdir", type=Path, default=DEFAULT_WORKDIR)
    ap.add_argument("--max-workers", type=int, default=1)
    ap.add_argument("--instances", nargs="+", metavar="ID",
                    help="run only these tasks (must be in the split); default: all")
    ap.add_argument("--cache-bust", action="store_true",
                    help="agent sources only: a random marker at the start of every "
                         "prompt, so no call can hit the cache (Week 3)")
    args = ap.parse_args(argv)
    if args.cache_bust and args.source not in AGENT_SOURCES:
        raise RunnerError("--cache-bust only applies to agent sources")

    os.environ["HF_DATASETS_OFFLINE"] = "1"  # before anything imports datasets
    workdir = args.workdir.expanduser().resolve()
    records_root = workdir / "records"

    preflight(workdir, records_root, args.run_id)
    docker = docker_version()
    if docker is None:
        raise RunnerError("Docker is not reachable. Is Docker Desktop running?")

    ids = select_instances(load_instance_ids(args.split), args.instances)
    env = capture_environment(docker)
    config = {"patch_source": args.source, "dataset": env.dataset_name,
              "dataset_revision": env.dataset_revision,
              "swebench_version": env.swebench_version}
    print(f"{args.run_id}: {len(ids)} tasks, source={args.source}, commit={env.blindspots_commit}")

    attempts = None
    if args.source in AGENT_SOURCES:
        attempts = run_agent(ids, workdir, cache_bust=args.cache_bust)
        patches = {i: attempts[i].patch for i in ids}
        from blindspots.agent.attempt import agent_config
        from blindspots.accountant import Limits
        config.update(agent_config(Limits(), cache_bust=args.cache_bust))
    else:
        patches = patches_for(args.source, ids)

    # Only tasks with a patch go to the harness. Tasks whose outcome is
    # already decided (a limit, an API failure, no usable edit) do not.
    to_score = [i for i in ids if patches[i].strip()] if attempts is not None else ids
    start = datetime.now().astimezone()
    if to_score:
        if args.source == "gold":
            predictions = "gold"
        else:
            workdir.mkdir(parents=True, exist_ok=True)
            predictions = str(write_predictions(
                workdir / f"preds.{args.run_id}.jsonl", args.source,
                {i: patches[i] for i in to_score}))
        code = harness.run_harness(to_score, predictions, args.run_id, workdir,
                                   args.max_workers)
        print(f"harness exit code {code}; console output in {workdir}/harness.{args.run_id}.out")
    else:
        print("no patches to score; harness not run")
    end = datetime.now().astimezone()

    records = build_records(args.run_id, args.source, patches, workdir, env,
                            config, start, end, attempts)
    if to_score:
        check_against_summary(records, harness.read_summary(
            harness.find_summary(workdir, args.run_id)))
    for rec in records:
        path = write_record(rec, records_root)
        t = rec.timing
        cost = f"  ${rec.usage.cost_usd:.5f}" if rec.usage.model_calls else ""
        print(f"  {rec.instance_id:28} {rec.outcome.value:18} "
              f"eval={t.evaluation_s if t.evaluation_s is not None else '-'}{cost}  -> {path.name}")
    print(f"{len(records)} records in {records_root / args.run_id}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RunnerError as e:
        sys.exit(f"refused: {e}")
