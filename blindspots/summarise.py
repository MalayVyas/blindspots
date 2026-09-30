"""Summarise run records as a Markdown table.

    python -m blindspots.summarise ~/bs-work/records/dev-gold-2

Every record is re-validated on reading (read_record), so a corrupted
or hand-edited record stops the summary instead of skewing it.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

from blindspots.record import RunRecord, read_record


def load(root: Path) -> list[RunRecord]:
    paths = sorted(Path(root).expanduser().rglob("*.json"))
    return [read_record(p) for p in paths]


def table(records: list[RunRecord]) -> str:
    f = lambda x: f"{x:.1f}" if x is not None else "–"
    rows = ["| Run | Task | Outcome | Eval (s) | Tests (s) | Teardown (s) | Cost ($) | Machine | Commit |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in records:
        t = r.timing
        cost = f"{r.usage.cost_usd:.5f}" if r.usage.model_calls else "–"
        rows.append(f"| {r.run_id} | {r.instance_id} | {r.outcome.value} | "
                    f"{f(t.evaluation_s)} | {f(t.test_runtime_s)} | {f(t.teardown_s)} | "
                    f"{cost} | {r.environment.machine} | {r.environment.blindspots_commit[:7]} |")
    counts = Counter(r.outcome.value for r in records)
    totals = ", ".join(f"{n} {k}" for k, n in sorted(counts.items()))
    spent = sum(r.usage.cost_usd for r in records)
    money = f" Model spend ${spent:.5f} (billed)." if spent else ""
    return "\n".join(rows) + f"\n\n**{len(records)} records:** {totals}.{money}\n"


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1:
        sys.exit("usage: python -m blindspots.summarise RECORDS_DIR")
    records = load(Path(args[0]))
    if not records:
        sys.exit(f"no records under {args[0]}")
    print(table(records))
    return 0


if __name__ == "__main__":
    sys.exit(main())
