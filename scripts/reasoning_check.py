"""Does DeepSeek's completion_tokens include the reasoning tokens? (entry #5 open item)

    python scripts/reasoning_check.py

One thinking-mode call whose reasoning is long and whose answer is tiny
("how many primes below 200? reply with only the number"). Then:

    completion_tokens ~ reasoning + a few  ->  output INCLUDES reasoning
    completion_tokens ~ a few              ->  output EXCLUDES reasoning

Prints the usage block exactly as DeepSeek sent it, BEFORE the adapter's
own consistency checks, so either answer is visible. Worst case about
half a cent. The raw response is saved to ~/bs-work/smoke/.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from blindspots import pricing
from blindspots.providers.deepseek import DeepSeek, build_request, parse_response

MODEL = "deepseek-flash"
MAX_TOKENS = 4000
MESSAGES = [{"role": "user", "content":
             "How many prime numbers are there below 200? "
             "Reply with only the number, nothing else."}]


def main() -> int:
    worst = pricing.worst_case_usd(MODEL, input_tokens=200, output_tokens=MAX_TOKENS)
    print(f"worst case ${worst:.4f}")
    body = build_request(MESSAGES, model=MODEL, max_tokens=MAX_TOKENS, temperature=0.0,
                         thinking="enabled", reasoning_effort="high")
    started = datetime.now(timezone.utc)
    with DeepSeek() as ds:
        # Straight to HTTP, so the raw usage is seen before any of our checks.
        resp = ds._http.post("/chat/completions", json=body)
    resp.raise_for_status()
    data = resp.json()

    out = Path.home() / "bs-work" / "smoke" / f"reasoning-check-{started:%Y%m%dT%H%M%SZ}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2))

    u = data["usage"]
    msg = data["choices"][0]["message"]
    completion = u["completion_tokens"]
    reasoning = (u.get("completion_tokens_details") or {}).get("reasoning_tokens")
    answer = (msg.get("content") or "").strip()
    thought = msg.get("reasoning_content") or ""
    print("raw usage:", json.dumps(u, indent=2))
    print(f"answer: {answer!r} ({len(answer)} characters)")
    print(f"reasoning text: {len(thought):,} characters")
    print(f"completion_tokens {completion}, reasoning_tokens {reasoning}")

    if reasoning is None:
        print("VERDICT: no reasoning_tokens field; cannot tell. Look at the raw usage above.")
    elif completion >= reasoning:
        print(f"VERDICT: completion_tokens INCLUDES reasoning "
              f"({completion} = {reasoning} reasoning + {completion - reasoning} answer).")
        print("  Our cost formula (all completion_tokens at the output price) is right.")
    else:
        print(f"VERDICT: completion_tokens EXCLUDES reasoning ({completion} < {reasoning}).")
        print("  Our adapter would refuse this response; the cost formula must change.")

    try:  # and what the adapter makes of it
        c = parse_response(data, request=body, model=MODEL, started_at=started, latency_s=0.0)
        print(f"adapter accepted it: billed ${c.billed_usd:.6f}, reference ${c.reference_usd:.6f}")
    except Exception as e:  # noqa: BLE001 - reporting, not handling
        print(f"adapter refused it: {e}")
    print(f"saved {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
