"""Week 2 step 1 acceptance: two real DeepSeek calls, costing well under a cent.

    python scripts/deepseek_smoke.py                      # thinking disabled
    python scripts/deepseek_smoke.py --thinking enabled   # thinking, low effort

Sends the same prompt twice. The prompt starts with a long stable prefix
(the text of blindspots/record.py), so the second call can hit the cache.
Prints what the API reported and saves both raw responses to
~/bs-work/smoke/ (outside the repository) for inspection.

What to look for:
1. Both calls succeed and the adapter accepts the usage fields: that
   proves the field locations and hit + miss == prompt.
2. Call 2 shows cache hits > 0. Not guaranteed: DeepSeek's cache is
   best-effort [PRIMARY — context caching guide]. Zero on call 2 is a
   finding to write down, not a bug to hide.
3. With --thinking enabled: reasoning_tokens <= completion_tokens. If
   the adapter refuses the response instead, completion_tokens does NOT
   include reasoning and the cost formula must change.
4. The costs match what the DeepSeek usage page shows for this time.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from blindspots import pricing
from blindspots.providers.deepseek import DeepSeek

REPO = Path(__file__).resolve().parents[1]
OUT = Path.home() / "bs-work" / "smoke"
HARD_CAP_USD = 0.01  # this script refuses to start if its worst case exceeds 1 cent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="deepseek-flash")
    ap.add_argument("--thinking", choices=["disabled", "enabled"], default="disabled")
    args = ap.parse_args()

    prefix = (REPO / "blindspots" / "record.py").read_text(encoding="utf-8")
    messages = [
        {"role": "system", "content": "You are reviewing this Python module.\n\n" + prefix},
        {"role": "user", "content": "In one sentence: what does write_record guarantee?"},
    ]
    thinking_args = ({"thinking": "enabled", "reasoning_effort": "low", "max_tokens": 2048}
                     if args.thinking == "enabled"
                     else {"thinking": "disabled", "max_tokens": 128})

    # Upper bound: prompt bytes as tokens (a byte-level tokenizer cannot
    # produce more tokens than bytes), every output token used, peak price.
    prompt_bytes = sum(len(m["content"].encode("utf-8")) for m in messages)
    worst = 2 * pricing.worst_case_usd(args.model, input_tokens=prompt_bytes,
                                       output_tokens=thinking_args["max_tokens"])
    print(f"worst case for 2 calls: ${worst:.5f} (cap ${HARD_CAP_USD})")
    if worst > HARD_CAP_USD:
        raise SystemExit("refused: worst case exceeds the cap")

    OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    with DeepSeek() as ds:
        for n in (1, 2):
            c = ds.complete(messages, model=args.model, temperature=0.0, **thinking_args)
            u = c.usage
            print(f"\ncall {n}: {c.latency_s:.1f}s  finish={c.finish_reason}  "
                  f"answered_by={c.response_model}  peak={c.peak}")
            print(f"  input {u.input_tokens} = hit {u.cache_hit_tokens} + miss {u.cache_miss_tokens}")
            print(f"  output {u.output_tokens} (reasoning {u.reasoning_tokens})")
            print(f"  billed ${c.billed_usd:.6f}   reference ${c.reference_usd:.6f}")
            print(f"  answer: {c.content.strip()[:200]}")
            path = OUT / f"{stamp}-{args.thinking}-call{n}.json"
            path.write_text(c.model_dump_json(indent=2), encoding="utf-8")
            print(f"  saved {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
