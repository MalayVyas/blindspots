"""Results entry #10: agent:mini against agent:simple on the dev split.

    python scripts/entry10_report.py --records ~/bs-work/run-records \\
        --mini ci-mini-net-1 ci-mini-net-2 ci-mini-net-4 \\
        --two-day ci-mini-net-1 ci-mini-net-2 \\
        --deviation ci-mini-net-3 --void ci-mini-1 \\
        --simple ci-w3-cache-1 ci-w3-cache-2 ci-w3-cache-3 ci-w3-bust-1 \\
        --localisation ci-agent-1 ci-agent-2 ci-w3-cache-1 ci-w3-cache-2 \\
            ci-w3-cache-3 ci-w3-bust-1

Reads RUN_ID.tar.gz archives downloaded from the run-records release
(ADR-0017), e.g.

    gh release download run-records -R MalayVyas/blindspots -D ~/bs-work/run-records

Records are read from inside the archives and re-validated; nothing is
extracted, and a records folder inside the repository is refused. Which
runs are headline, deviation or void is set only by the arguments, so
swapping one run for another is a change of arguments, not of code.

    --mini          headline agent:mini runs (every figure in the entry)
    --two-day       subset of --mini run on separate UTC days, for the
                    two-day figure line
    --deviation     reported with its numbers, kept out of every figure
    --void          reported as a finding only (ci-mini-1: network)
    --simple        agent:simple comparator for resolve rate and cost
    --localisation  agent:simple runs for the gold-file-shown split

Cold/warm (ADR-0018 amendment): cold if call 1's cached tokens are at or
below the shared prefix (mini 128, simple 0). Costs are reference_usd
(off-peak list price, ADR-0013); billed totals are shown too.
Intervals: resolve rate, Wilson 95%; cost, bootstrap 95% resampling tasks
rather than attempts, fixed seed.
"""

from __future__ import annotations

import argparse
import hashlib
import math
import random
import shlex
import sys
import tarfile
from collections import defaultdict
from pathlib import Path

from blindspots.record import RunRecord

SEED = 10
DRAWS = 10_000
SHARED_PREFIX = {"agent:mini": 128, "agent:simple": 0}
REPO = Path(__file__).resolve().parent.parent


def load(records: Path, run_id: str) -> tuple[str, list[RunRecord]]:
    """Every agent record in RUN_ID.tar.gz, and the archive's SHA-256."""
    path = records / f"{run_id}.tar.gz"
    if not path.is_file():
        sys.exit(f"missing archive {path} (download it from the run-records release)")
    data = path.read_bytes()
    out = []
    with tarfile.open(path, "r:gz") as tar:
        for m in tar.getmembers():
            # Only files under a records/ folder: the archives also hold
            # harness report.json files.
            if m.isfile() and m.name.endswith(".json") and "records" in Path(m.name).parts:
                r = RunRecord.model_validate_json(tar.extractfile(m).read())
                if r.run_id != run_id:
                    sys.exit(f"{path}: record {m.name} has run_id {r.run_id}")
                if r.usage.model_calls:
                    out.append(r)
    if not out:
        sys.exit(f"{path}: no agent records")
    return hashlib.sha256(data).hexdigest(), out


def cached_call1(r: RunRecord) -> int:
    for c in r.transcript:
        u = (c.get("response") or {}).get("usage")
        if u:
            return u.get("prompt_cache_hit_tokens") or 0
    return 0


def temp(r: RunRecord) -> str:
    return "cold" if cached_call1(r) <= SHARED_PREFIX.get(r.patch_source, 0) else "warm"


def resolved(r: RunRecord) -> bool:
    return r.outcome.value == "resolved"


def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    if not n:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def bootstrap(recs: list[RunRecord], stat) -> tuple[float, float]:
    """95% percentile interval of stat over draws that resample tasks. A fresh
    generator per call, so each figure is reproducible on its own."""
    rng = random.Random(SEED)
    by_task = defaultdict(list)
    for r in recs:
        by_task[r.instance_id].append(r)
    tasks = sorted(by_task)
    vals = sorted(stat([r for t in rng.choices(tasks, k=len(tasks)) for r in by_task[t]])
                  for _ in range(DRAWS))
    return vals[int(0.025 * DRAWS)], vals[int(0.975 * DRAWS) - 1]


def per_attempt(recs):
    return sum(r.usage.reference_usd for r in recs) / len(recs)


def per_fix(recs):
    fixes = sum(map(resolved, recs))
    return sum(r.usage.reference_usd for r in recs) / fixes if fixes else math.inf


def usd(x: float) -> str:
    return "unbounded" if math.isinf(x) else f"${x:.5f}"


def summary(label: str, recs: list[RunRecord]) -> None:
    k, n = sum(map(resolved, recs)), len(recs)
    lo, hi = wilson(k, n)
    a_lo, a_hi = bootstrap(recs, per_attempt)
    f_lo, f_hi = bootstrap(recs, per_fix)
    billed = sum(r.usage.cost_usd for r in recs)
    ref = sum(r.usage.reference_usd for r in recs)
    hit = sum(r.usage.cached_input_tokens for r in recs)
    tot = sum(r.usage.input_tokens for r in recs)
    cold = sum(temp(r) == "cold" for r in recs)
    print(f"{label}")
    print(f"  resolved        {k}/{n} = {k/n:.1%}  (Wilson 95% {lo:.1%}-{hi:.1%})")
    print(f"  cost / attempt  {usd(per_attempt(recs))}  (bootstrap 95% {usd(a_lo)}-{usd(a_hi)})")
    print(f"  cost / fix      {usd(per_fix(recs))}  (bootstrap 95% {usd(f_lo)}-{usd(f_hi)})")
    print(f"  reference total ${ref:.5f}; billed ${billed:.5f}")
    print(f"  cache hits      {hit}/{tot} input tokens = {hit/tot:.1%}; cold attempts {cold}/{n}")
    calls = [r.usage.model_calls for r in recs]
    print(f"  calls           min {min(calls)}  max {max(calls)}  total {sum(calls)}")
    agent_s = [r.timing.agent_s for r in recs if r.timing.agent_s is not None]
    if agent_s:
        print(f"  agent_s         min {min(agent_s):.1f}  max {max(agent_s):.1f}")
    res_tasks = {r.instance_id for r in recs if resolved(r)}
    all_tasks = {r.instance_id for r in recs}
    print(f"  tasks resolved at least once: {len(res_tasks)}/{len(all_tasks)}"
          + (f"; never: {', '.join(sorted(all_tasks - res_tasks))}" if all_tasks - res_tasks else ""))
    print()


def table(recs: list[RunRecord]) -> None:
    print("run              task                      outcome         calls/max  in        "
          "cached%  call1$  temp  ref$      agent_s  gold_patched  outside_reach")
    for r in sorted(recs, key=lambda r: (r.instance_id, r.run_id)):
        u = r.usage
        cap = (r.config.get("limits") or {}).get("max_calls", "?")
        loc = r.diagnostics.get("localisation") or {}
        gold = loc.get("all_gold_files_patched", loc.get("all_gold_files_shown", ""))
        reach = r.diagnostics.get("outside_reach")
        agent_s = f"{r.timing.agent_s:7.1f}" if r.timing.agent_s is not None else "      -"
        print(f"{r.run_id:16} {r.instance_id:25} {r.outcome.value:15} {u.model_calls:3}/{cap:<5} "
              f"{u.input_tokens:9} {u.cached_input_tokens / u.input_tokens:7.1%} {cached_call1(r):6}  "
              f"{temp(r):5} {u.reference_usd:.5f}  {agent_s}  {str(gold):12}  "
              f"{len(reach) if reach is not None else '-'}")
    print()


def tripwire(recs: list[RunRecord]) -> None:
    if all("outside_reach" not in r.diagnostics for r in recs):
        print("Tripwire: not recorded (these records predate it)\n")
        return
    hits = [(r, e) for r in recs for e in r.diagnostics.get("outside_reach") or []]
    print(f"Tripwire entries: {len(hits)} in {len({r.run_id + r.instance_id for r, _ in hits})} "
          "attempts (returncode is the pipeline's last command, not the network call)")
    for r, e in hits:
        print(f"  {r.run_id} {r.instance_id} call {e['call']} rc {e['returncode']}: {e['command'][:110]}")
    print()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--records", required=True, type=Path,
                    help="folder of RUN_ID.tar.gz files from the run-records release")
    for name in ("mini", "simple"):
        ap.add_argument(f"--{name}", nargs="+", required=True, metavar="RUN_ID")
    for name in ("two-day", "deviation", "void", "localisation"):
        ap.add_argument(f"--{name}", nargs="+", default=[], metavar="RUN_ID")
    a = ap.parse_args()

    print("$ python " + " ".join(shlex.quote(x) for x in sys.argv))
    print(f"bootstrap: seed {SEED}, {DRAWS:,} draws, resampling tasks\n")

    records = a.records.expanduser().resolve()
    if records == REPO or REPO in records.parents:
        sys.exit(f"refused: {records} is inside the repository; read archives from run-records")
    if not set(a.two_day) <= set(a.mini):
        sys.exit("--two-day must be a subset of --mini")
    if set(a.mini) & set(a.deviation + a.void):
        sys.exit("a run cannot be both headline and deviation/void")

    runs = {}
    for rid in dict.fromkeys(a.mini + a.simple + a.deviation + a.void + a.localisation):
        sha, recs = load(records, rid)
        runs[rid] = recs
        days = sorted({r.timing.started_at.date().isoformat() for r in recs})
        commits = sorted({r.environment.blindspots_commit[:7] for r in recs})
        sources = sorted({r.patch_source for r in recs})
        print(f"{rid:16} {len(recs)} records  {','.join(sources):13} UTC day {','.join(days)}  "
              f"commit {','.join(commits)}  sha256 {sha[:16]}")
    print()

    def pick(ids, source):
        recs = [r for i in ids for r in runs[i]]
        bad = {r.patch_source for r in recs} - {source}
        if bad:
            sys.exit(f"expected {source} records, found {bad}")
        return recs

    mini, simple = pick(a.mini, "agent:mini"), pick(a.simple, "agent:simple")
    mini_days = defaultdict(list)
    for i in a.mini:
        mini_days[runs[i][0].timing.started_at.date()].append(i)
    shared = {d: ids for d, ids in mini_days.items() if len(ids) > 1}
    if shared:
        print(f"WARNING: headline mini runs share a UTC day: {shared}\n")

    print("== Headline ==\n")
    table(mini)
    summary(f"agent:mini, {' + '.join(a.mini)}", mini)
    if a.two_day:
        summary(f"agent:mini, two-day line, {' + '.join(a.two_day)}", pick(a.two_day, "agent:mini"))
    summary(f"agent:simple, {' + '.join(a.simple)}", simple)
    tripwire(mini)

    if a.localisation:
        loc = pick(a.localisation, "agent:simple")
        print(f"== agent:simple by gold file shown ({' + '.join(a.localisation)}) ==")
        for shown in (True, False):
            g = [r for r in loc
                 if (r.diagnostics.get("localisation") or {}).get("all_gold_files_shown") is shown]
            print(f"  shown={shown!s:5}  resolved {sum(map(resolved, g))}/{len(g)}")
        print()

    for label, ids in (("Deviation (not in any figure)", a.deviation), ("Void (finding only)", a.void)):
        if ids:
            recs = [r for i in ids for r in runs[i]]
            print(f"== {label} ==\n")
            table(recs)
            summary(f"{' + '.join(ids)}", recs)
            tripwire(recs)


if __name__ == "__main__":
    main()
