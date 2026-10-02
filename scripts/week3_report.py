"""Week 3 report: cost per attempt, cache hit rate, cold vs warm vs busted.

    python scripts/week3_report.py runs/w3

Reads every run record under the folder (re-validated by read_record).
Each attempt is classed by what the API reported, not by which dispatch it
was in, because a "first" dispatch can still hit a cache left by earlier
runs (DeepSeek keeps entries for hours to days, best effort):

    busted  config has cache_bust          (should show 0 cached tokens)
    cold    cached share of input < 10%
    warm    cached share of input >= 10%

Costs are reference_usd (off-peak list price, ADR-0013), so attempts made
at different times of day compare fairly. Billed totals are shown too.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean, median

from blindspots.record import read_record


def cls(r) -> str:
    if r.config.get("cache_bust"):
        return "busted"
    u = r.usage
    share = u.cached_input_tokens / u.input_tokens if u.input_tokens else 0.0
    return "warm" if share >= 0.10 else "cold"


def truncated(r) -> bool:
    return any(c.get("finish_reason") == "length" for c in r.transcript)


def second_witness_ok(r) -> bool:
    """Re-run the adapter cross-check on the raw JSON in the transcript."""
    for c in r.transcript:
        u = (c.get("response") or {}).get("usage") or {}
        cached = (u.get("prompt_tokens_details") or {}).get("cached_tokens")
        hit = u.get("prompt_cache_hit_tokens")
        if cached is not None and hit is not None and cached != hit:
            return False
    return True


def spread(xs: list[float]) -> str:
    if not xs:
        return "-"
    return (f"n={len(xs)}  mean ${mean(xs):.5f}  median ${median(xs):.5f}  "
            f"min ${min(xs):.5f}  max ${max(xs):.5f}")


def main(root: str) -> None:
    # Only files under a records/ folder: artifacts also hold harness report.json files.
    recs = [read_record(p) for p in sorted(Path(root).expanduser().rglob("*.json"))
            if "records" in p.parts]
    recs = [r for r in recs if r.usage.model_calls]
    print(f"{len(recs)} agent attempts\n")
    print("run            task                      class   outcome             "
          "in      cached  share  out   trunc  ref$      bust_ok  gold_shown")
    groups = defaultdict(list)
    for r in sorted(recs, key=lambda r: (r.instance_id, r.run_id)):
        u, k = r.usage, cls(r)
        groups[k].append(r)
        share = u.cached_input_tokens / u.input_tokens if u.input_tokens else 0
        loc = (r.diagnostics.get("localisation") or {}).get("all_gold_files_shown")
        bust = r.diagnostics.get("cache_bust_verified", "")
        print(f"{r.run_id:14} {r.instance_id:25} {k:7} {r.outcome.value:19} "
              f"{u.input_tokens:6} {u.cached_input_tokens:7} {share:5.0%} {u.output_tokens:5} "
              f"{'yes' if truncated(r) else '':6} {u.reference_usd:.5f}  {str(bust):8} {loc}")

    print("\nCost per attempt (reference $), by class:")
    for k in ("cold", "warm", "busted"):
        print(f"  {k:7} {spread([r.usage.reference_usd for r in groups[k]])}")

    warm = groups["warm"]
    if warm:
        hit = sum(r.usage.cached_input_tokens for r in warm)
        tot = sum(r.usage.input_tokens for r in warm)
        print(f"\nCache hit rate, warm attempts: {hit}/{tot} input tokens = {hit/tot:.1%}")
    allc = [r for r in recs if cls(r) != "busted"]
    if allc:
        hit = sum(r.usage.cached_input_tokens for r in allc)
        tot = sum(r.usage.input_tokens for r in allc)
        print(f"Cache hit rate, all caching-on attempts: {hit}/{tot} = {hit/tot:.1%}")

    print("\nPer task, caching-on vs busted (reference $):")
    by_task = defaultdict(lambda: {"on": [], "busted": []})
    for r in recs:
        by_task[r.instance_id]["busted" if cls(r) == "busted" else "on"].append(r.usage.reference_usd)
    for t, d in sorted(by_task.items()):
        on, b = d["on"], d["busted"]
        ratio = f"{mean(b)/mean(on):5.1f}x" if on and b and mean(on) else "  -  "
        print(f"  {t:25} on {spread(on)}\n  {'':25} busted {spread(b)}   ratio {ratio}")

    busted_bad = [r for r in groups["busted"] if r.diagnostics.get("cache_bust_verified") is not True]
    witness_bad = [r for r in recs if not second_witness_ok(r)]
    print(f"\nChecks: busted attempts with cache hits: {len(busted_bad)}; "
          f"cached_tokens disagreements in raw JSON: {len(witness_bad)}")
    res = sum(r.outcome.value == "resolved" for r in recs)
    billed = sum(r.usage.cost_usd for r in recs)
    print(f"Resolved {res}/{len(recs)}. Billed ${billed:.5f}"
          + (f"; cost per fix ${billed/res:.4f}" if res else "; no fixes"))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "runs/w3")
