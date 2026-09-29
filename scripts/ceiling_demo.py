"""Week 2 step 2 acceptance: a deliberately broken loop, real API, real money.

    python scripts/ceiling_demo.py                 # stopped by a $0.001 cost cap
    python scripts/ceiling_demo.py --limit wall    # stopped by a 5-second clock

The loop has no stop condition, like an agent whose termination check is
broken. Only the accountant can end it. Worst case is the cap itself:
$0.001, a tenth of a cent (peak-price dollars, ADR-0014).

Writes one run record (outcome spend_ceiling or wall_clock_limit, with the
partial transcript) to ~/bs-work/records/RUN_ID/, then reads it back
through the validator.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from blindspots.accountant import Accountant, LimitBreached, Limits, outcome_for
from blindspots.providers.deepseek import DeepSeek
from blindspots.record import RunRecord, Timing, config_hash, read_record, write_record
from blindspots.run import capture_environment, docker_version

RECORDS = Path.home() / "bs-work" / "records"
MODEL = "deepseek-flash"
# Long-ish output, so each call costs enough that the cap is reached in 2-3 calls.
MESSAGES = [{"role": "user", "content": "Count from 1 to 150, numbers separated by spaces."}]
MAX_TOKENS = 400


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", choices=["cost", "wall"], default="cost")
    args = ap.parse_args()

    # Loose on everything except the limit being demonstrated.
    limits = (Limits(max_calls=1000, max_cost_usd=0.001)
              if args.limit == "cost"
              else Limits(max_calls=1000, max_cost_usd=0.01, max_wall_clock_s=5.0))
    run_id = f"ceiling-{args.limit}-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    config = {"model": MODEL, "thinking": "disabled", "max_tokens": MAX_TOKENS, "temperature": 0.0,
              "limits": limits.model_dump(), "purpose": "ceiling acceptance test"}
    print(f"{run_id}: limits {limits.model_dump()}")

    started = datetime.now(timezone.utc)
    with DeepSeek() as ds:
        acct = Accountant(ds, limits, model=MODEL)
        try:
            while True:  # deliberately broken: nothing here ever stops the loop
                c = acct.complete(MESSAGES, max_tokens=MAX_TOKENS, temperature=0.0, thinking="disabled")
                u = acct.usage()
                print(f"  call {u.model_calls:3d}: {c.latency_s:4.1f}s  "
                      f"ceiling ${u.ceiling_usd:.6f}  billed ${u.cost_usd:.6f}")
        except LimitBreached as e:
            breach = e.breach
            print(f"STOPPED: {e}")
    finished = datetime.now(timezone.utc)

    rec = RunRecord(
        run_id=run_id, instance_id="ceiling-demo", patch_source="agent:ceiling-demo",
        model=MODEL, config=config, config_hash=config_hash(config), patch="",
        outcome=outcome_for(breach), tests=None, usage=acct.usage(),
        timing=Timing(started_at=started, finished_at=finished),
        transcript=acct.transcript(), breach=breach,
        environment=capture_environment(docker_version()))
    path = write_record(rec, RECORDS)
    back = read_record(path)  # re-validated on the way back in
    u = back.usage
    print(f"\nrecord: {path}")
    print(f"  outcome {back.outcome.value}; {u.model_calls} calls; "
          f"transcript entries {len(back.transcript)}")
    print(f"  tokens in {u.input_tokens} (cached {u.cached_input_tokens}), out {u.output_tokens}")
    print(f"  billed ${u.cost_usd:.6f}  reference ${u.reference_usd:.6f}  "
          f"ceiling ${u.ceiling_usd:.6f}  (cap ${limits.max_cost_usd})")
    print(f"  wall-clock {(finished - started).total_seconds():.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
