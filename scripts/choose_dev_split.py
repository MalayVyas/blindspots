"""Choose the 5-task dev split for Blindspots (ADR-0007, amended).

Rules, fixed before any selection is seen:
  * Candidates: SWE-bench Verified tasks that are NOT in Verified Mini.
  * Only repositories that Verified Mini uses (django, sphinx).
  * Excluded: the smoke-test canary django__django-11099, and tasks
    labelled ">4 hours" (too few to sample, and unlikely to teach
    anything in October).
  * Seats per repository follow Verified Mini's repository mix
    (largest-remainder rounding), with at least one seat per repository.
  * Within each repository, a seeded random draw. The seed is fixed
    here, so anyone can rerun this and get the same five tasks.

Reads only metadata columns: instance_id, repo, version, difficulty,
and the COUNT of FAIL_TO_PASS / PASS_TO_PASS tests. Never reads problem
statements, hints or patches. For the held-out Mini set it prints only
aggregate counts, never task IDs.

Run from WSL, inside the blindspots venv, WITHOUT HF_DATASETS_OFFLINE
(Mini has not been downloaded yet):

    python choose_dev_split.py
"""

import json
import random
from collections import Counter

from datasets import load_dataset

SEED = 20261001  # fixed before selection; do not change after seeing output
N_DEV = 5
VERIFIED = "SWE-bench/SWE-bench_Verified"
MINI = "MariusHobbhahn/swe-bench-verified-mini"
CANARY = "django__django-11099"
META = ["instance_id", "repo", "version", "difficulty"]


def n_tests(value):
    return len(json.loads(value)) if isinstance(value, str) else len(value)


mini_ds = load_dataset(MINI, split="test")
mini_ids = set(mini_ds["instance_id"])
mini_repos = Counter(mini_ds["repo"])

ver = load_dataset(VERIFIED, split="test")
has_difficulty = "difficulty" in ver.column_names
keep = [c for c in META if c in ver.column_names] + ["FAIL_TO_PASS", "PASS_TO_PASS"]
ver = ver.select_columns(keep)

rows = []
for r in ver:
    rows.append({
        "instance_id": r["instance_id"],
        "repo": r["repo"],
        "version": r.get("version"),
        "difficulty": r.get("difficulty", "n/a"),
        "n_f2p": n_tests(r["FAIL_TO_PASS"]),
        "n_p2p": n_tests(r["PASS_TO_PASS"]),
        "in_mini": r["instance_id"] in mini_ids,
    })

# --- Held-out set: aggregate counts only ------------------------------
mini_rows = [r for r in rows if r["in_mini"]]
print(f"Verified: {len(rows)} tasks. Mini: {len(mini_rows)} tasks "
      f"(matched in Verified: {len(mini_rows) == len(mini_ids)})")
print("Mini repositories:", dict(mini_repos))
print("Mini difficulty:  ", dict(Counter(r["difficulty"] for r in mini_rows)))
if not has_difficulty:
    print("NOTE: no 'difficulty' column in this dataset; sampling by repo only.")

# --- Candidate pool ----------------------------------------------------
pool = [r for r in rows
        if not r["in_mini"]
        and r["repo"] in mini_repos
        and r["instance_id"] != CANARY
        and r["difficulty"] != ">4 hours"]
print("\nCandidate pool by repository:", dict(Counter(r["repo"] for r in pool)))
print("Candidate pool by difficulty:", dict(Counter(r["difficulty"] for r in pool)))

# --- Seats per repository, proportional to Mini ------------------------
total = sum(mini_repos.values())
quota = {repo: N_DEV * n / total for repo, n in mini_repos.items()}
# Every Mini repository gets at least one seat, so the agent is never
# tuned against a single codebase.
seats = {repo: max(1, int(q)) for repo, q in quota.items()}
for repo in sorted(quota, key=lambda k: quota[k] - seats[k], reverse=True):
    if sum(seats.values()) >= N_DEV:
        break
    seats[repo] += 1
print("Seats per repository:", seats)

# --- Seeded draw -------------------------------------------------------
rng = random.Random(SEED)
chosen = []
for repo in sorted(seats):
    candidates = sorted((r for r in pool if r["repo"] == repo),
                        key=lambda r: r["instance_id"])
    chosen += rng.sample(candidates, seats[repo])

print(f"\nDev split (seed {SEED}):")
print(f"{'instance_id':<32} {'repo':<20} {'version':<8} {'difficulty':<16} F2P  P2P")
for r in chosen:
    print(f"{r['instance_id']:<32} {r['repo']:<20} {str(r['version']):<8} "
          f"{r['difficulty']:<16} {r['n_f2p']:>3}  {r['n_p2p']:>3}")

with open("dev_split.json", "w") as f:
    json.dump({"seed": SEED, "source": VERIFIED, "excluded": MINI,
               "instance_ids": [r["instance_id"] for r in chosen]}, f, indent=2)
print("\nWrote dev_split.json")
