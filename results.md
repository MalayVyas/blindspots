# Blindspots — Results log

Every measured number goes here, dated, including failed and broken
runs. Entries are never deleted; corrections are added as new entries.

---

## Definitions — fixed before the first run

These are written down in advance so they cannot drift to flatter a
result later.

### What counts as a bug fixed

A task is **resolved** when, after applying the generated patch and
running the official SWE-bench evaluation harness:

- every `FAIL_TO_PASS` test passes, and
- every `PASS_TO_PASS` test still passes.

Anything else is a failure. Specifically, these are **failures, not
exclusions**, and each is counted and reported separately:

| Outcome | Counted as |
| --- | --- |
| Patch does not apply | failure |
| Agent produced no patch | failure |
| Job hit the spend ceiling | failure |
| Job hit the wall-clock limit | failure |
| Harness errored | failure |
| Model API failed (network, HTTP error, bad response) | failure |
| Patch applied, but the test run produced no results (crash, timeout) | failure |

A run that excludes its failures is not a measurement.

### Cost per fix

> total spend across **all attempted tasks** ÷ tasks resolved

The cost of failed attempts stays in the numerator. A configuration
that solves one task cheaply and fails ninety-nine does not get to
look efficient.

Cost per fix is always reported next to the raw resolve rate, never
alone. The headline presentation is a cost-versus-resolve-rate
frontier across every configuration measured.

### What every entry must carry

- **Date**
- **Commit hash** of the code that produced it
- **Prompt hashes** (see ADR-0008 — runs with differing prompt hashes
  are not comparable)
- **Configuration**: model per role, iteration caps, review rounds
- **Task sample**: dev split or test set, by task ID
- **Seed**, and how many seeds the entry summarises
- **Numbers**: resolved / attempted, cost, tokens in / out / cached,
  cache hit rate, wall-clock
- **Confidence interval** — bootstrap, on every reported figure
- **Notes**: what broke, what surprised you, what to try next

### Run records

Every individual run writes a JSON record to disk: task ID, config
hash, prompt hashes, model, tokens in / out / cached, cost,
wall-clock, the patch, the full transcript, and the outcome. Entries
in this file are summaries over those records; the records are the
evidence.

From schema 3 (Week 4), wall-clock is two figures: the harness's
own timing (`timing.started_at`/`finished_at` and the evaluation
breakdown) and, for agent records, `timing.agent_s` — the agent's
attempt alone, workspace preparation excluded. Failed attempts
carry it too: their time counts, like their cost.

This starts with run number one. Beyond making cost per fix
computable, every failed patch becomes labelled data for the reviewer
benchmark in January — gold patches are the positive class, failures
the negative class — and that dataset is free if captured from the
start and expensive to reconstruct later.

---

## Entries

## Entry #0 — Week 0 spike: can a free GitHub runner score a SWE-bench task?

**Date:** 2026-09-26
**Answer:** Yes, with a large margin.
**Setup:** swebench 5.0.2, dataset SWE-bench/SWE-bench_Verified, task
django__django-11099 (outside Verified Mini), gold patch, 1 worker,
ubuntu-24.04 standard runner. No model called. Cost: $0.

| | Run 1 | Run 2 |
| --- | --- | --- |
| Run | 36217970815 | 36218467955 |
| Resolved (harness report.json) | true | true |
| FAIL_TO_PASS / PASS_TO_PASS | 3/3, 19/19 | 3/3, 19/19 |
| Runner disk free at start | 92.3 GB | 92.3 GB |
| Peak disk added | 3.91 GB | 3.92 GB |
| Image, uncompressed | 2.87 GB | 2.87 GB |
| Image pull | 35 s | 37 s |
| Harness evaluation | 27 s | 27 s |
| Workflow steps (excl. runner start) | 83 s | 92 s |

All figures [MEASURED], two runs, one task.

**Findings**
- GitHub documents 14 GB of SSD for this runner [PRIMARY]; we observed
  92 GB free [MEASURED]. Plan against the documented 14 GB: one task
  still fits more than 3 times over.
- Each matrix job runs on its own runner, so per-task disk is what
  matters, not the total for all 50 [JUDGEMENT].
- The free_disk fallback is not needed [JUDGEMENT].
- Run 1 was marked failed by the workflow's own summary step (wrong
  report path), although the harness resolved the task. Fixed in
  run 2 by searching for report.json instead of hardcoding a path.

**Limits:** one small Django task. Heavier repos may need more disk
and time; Week 1's five dev tasks will show the range.
---

## Entry #1 — Local harness smoke test (WSL2 + Docker Desktop)

**Date:** 2026-09-26
**Question:** Does the pinned harness score a task on the local
machine, and what does a local evaluation cost in wall-clock?
**Answer:** Yes. A warm local evaluation takes the same time as CI;
all the extra time is one-off image download plus a fixable
~45 s startup check.
**Setup:** swebench 5.0.2, Python 3.11.16 in a uv venv
(`~/.venvs/blindspots`), WSL2 Ubuntu, Docker Desktop with its image
store on E:. Dataset SWE-bench/SWE-bench_Verified, cached revision
`78f471bf655a3137b2e8a75af1501690ec009ec3`. Task django__django-11099
(outside Verified Mini), gold patch, 1 worker. Repo at commit
aaaf4a3 (no project code involved). No model called. Cost: $0.

| | smoke-1 | smoke-2 (attempt 1) | smoke-2 | smoke-3 |
| --- | --- | --- | --- | --- |
| Condition | cold: no image, no dataset cache | Docker Desktop not running | warm | warm, `HF_DATASETS_OFFLINE=1` |
| Outcome | resolved | **harness error** | resolved | resolved |
| FAIL_TO_PASS / PASS_TO_PASS | 3/3, 19/19 | — | resolved per summary | resolved per summary |
| Instance step (pull + eval) | 4 min 03 s | — | 29 s | 30 s |
| Total wall-clock (`real`) | 6 min 55 s | 53 s, then crash | 1 min 17 s | 33 s |
| Time outside instance step | ~2 min 52 s | 53 s | ~48 s | ~3 s |
| E: used (`df -h`, 1 GB steps) | 63 → 66 GB | — | — | — |

Wall-clock and outcomes [MEASURED], one run per column. "Time outside
instance step" is `real` minus the instance step [ESTIMATE —
subtraction of two measurements].

**Findings**
- **Local warm evaluation matches CI:** 29–30 s locally against 27 s
  on the GitHub runner [MEASURED]. Docker Desktop's disk on E: is not
  a bottleneck.
- **Cold-run time is dominated by the one-off image pull** (~2.9 GB
  over a home connection) and the dataset download (6.3 MB at
  ~123 kB/s) [MEASURED]. Paid once per task image.
- **~45 s of fixed overhead per invocation is the Hugging Face Hub
  online check.** Offline mode cut `real` from 77 s to 33 s with the
  instance step unchanged [MEASURED]. The offline log shows the
  harness loading the dataset three times per invocation [MEASURED —
  log output], which plausibly multiplies the check [JUDGEMENT].
- **The engine must be running.** With Docker Desktop stopped, the
  harness fails at client creation with `FileNotFoundError` on the
  Docker socket — an environment failure, not a harness bug. Under
  the definitions above it would count as a failure, so run
  scripts should check `docker version` before starting.

**Consequences (for decisions.md, ADR-0010)**
- Local runs use `HF_DATASETS_OFFLINE=1` once the dataset is cached.
  Side benefit: the dataset revision cannot change underneath a run.
  Candidate: pin the dataset revision explicitly, locally and in CI.
- Local harness environment: uv-managed Python 3.11 venv, matching
  CI's Python version.

**Limits:** one small task, one run per condition. `docker info`
(CPUs and memory visible to containers) not yet recorded. The
5-task dev split gold/empty check (plan item 5) becomes Entry #2.

---

## Entry #2 — Dev split: gold, empty and no-op patches (Week 1 steps 3–4)

**Date:** 2026-09-29
**Question:** Does the scoreboard say yes to correct fixes and no to
non-fixes, on the five dev tasks?
**Answer:** Yes. Gold 5/5 resolved; empty 0/5; no-op 0/5, with every
FAIL_TO_PASS test failing and every PASS_TO_PASS test passing.
**Setup:** as entry #1 (swebench 5.0.2, Python 3.11.16, WSL2 +
Docker Desktop 29.6.2, `HF_DATASETS_OFFLINE=1`, dataset revision
`78f471bf…`). Tasks from `splits/dev_split.json` (commit f58c8bd).
1 worker, tasks run one at a time. No model called. Cost: $0.

### Gold patches (run `dev-gold-1`)

| Task | Resolved | Image pull | Evaluation |
| --- | --- | --- | --- |
| django__django-13343 | true | 198.3 s | 26.5 s |
| django__django-13809 | true | 123.5 s | 69.5 s |
| django__django-14017 | true | 114.5 s | 25.6 s |
| sphinx-doc__sphinx-8621 | true | 92.5 s | 21.2 s |
| sphinx-doc__sphinx-9658 | true | 110.8 s | 24.0 s |

Total wall-clock 810.8 s; pulls 639.6 s (79%) + evaluations 166.8 s
+ ~4 s startup [MEASURED — `time` and per-task timestamps in
`run_instance.log`; the two agree].

### Negative controls

| Control | Run | Result | Wall-clock |
| --- | --- | --- | --- |
| Empty patch | `dev-empty-1` | 0/5; all 5 counted as empty, none evaluated | 4.7 s |
| No-op patch (adds one text file) | `dev-noop-1` | 0/5; all applied | 247.7 s |

| Task | FAIL_TO_PASS pass/fail | PASS_TO_PASS pass/fail |
| --- | --- | --- |
| django__django-13343 | 0/1 | 130/0 |
| django__django-13809 | 0/1 | 245/0 |
| django__django-14017 | 0/2 | 147/0 |
| sphinx-doc__sphinx-8621 | 0/2 | 31/0 |
| sphinx-doc__sphinx-9658 | 0/1 | 24/0 |

All figures [MEASURED], one run each.

### Disk

E: used 66 → 78 GB after five new images [MEASURED — `df`, whole
GB]: ~2.4 GB per new task image [ESTIMATE]. `docker images` reports
4.05–4.35 GB per image, but those sizes include shared layers and do
not add up; `df` is the figure to plan with. Extrapolation: all 50
Mini tasks ≈ 100–150 GB locally [ESTIMATE] — well above the "5 GB"
in Mini's README, which predates per-task images in harness 5.x
[JUDGEMENT]. CI is unaffected (fresh runner per job).

### Findings
- **The scoreboard discriminates for the right reason.** No-op
  patches applied, FAIL_TO_PASS failed and PASS_TO_PASS passed — the
  "no" came from the unfixed bug, not a broken environment.
- **Empty patches are never evaluated** — the harness counts them
  and skips them [PRIMARY — swebench 5.0.2 source; MEASURED — 0
  completed in 4.7 s]. An empty-patch check alone cannot show that
  scoring works; the no-op control is required.
- **No flaky tests seen:** all 577 PASS_TO_PASS tests passed under
  both gold and no-op [MEASURED, two runs — too few to rule
  flakiness out].
- **Cold local cost is dominated by image pulls** (79%); warm
  evaluation is 21–70 s per task, apparently rising with test count
  [JUDGEMENT, n=5].

**Open:** no-op averaged ~49 s per task against 33 s for gold
evaluations, both with images already local. Cause not investigated.

**Partly answered 2026-09-29** (from `run_instance.log`, task
django__django-13343): the harness's own test runtime was 9.2 s for
gold and 16.8 s for no-op, so failing tests ran longer. Both runs
then spent 15.5 s waiting for the container to stop — the harness
calls `docker stop --time=15` and the container does not exit early
[PRIMARY — swebench 5.0.2 `docker_utils.py`; MEASURED, one task].
That is 58% of this task's gold evaluation. Not fixable without
modifying the pinned harness (ADR-0010); accepted as fixed overhead,
~15 s per evaluation. Per-task figures are now captured automatically
(`test_runtime_s`, `teardown_s` in the run record).

**Correction 2026-09-29 (entry #3):** "failing tests ran longer" does
not hold. In run 2 no-op test runtimes were *below* gold on all five
tasks (e.g. django-13343: 7.3 s vs 9.9 s). Run 1's 16.8 s vs 9.2 s was
a single-sample difference within run-to-run variation. The teardown
finding stands (15.3–15.4 s on 10 of 10 tasks).

**Limits:** one run per condition; five tasks.

---

## Entry #3 — Runner acceptance test: first results computed from run records

**Date:** 2026-09-29
**Question:** Does `python -m blindspots.run` reproduce entry #2, and
write one valid record per task?
**Answer:** Yes. 15 records: gold 5/5 resolved, no-op 5/5 unresolved,
empty 5/5 empty_patch — identical verdicts to entry #2. Every record
re-validated on reading; every run cross-checked against the harness
summary; no `-dirty` commits.
**Setup:** runs `dev-gold-2`, `dev-noop-2`, `dev-empty-2`; commit
bd85364; otherwise as entry #2. Images already local. Cost: $0.
**Source:** all figures read from `~/bs-work/records/` by
`read_record` — none typed by hand.

### Per-task timing, run 2 (seconds)

| Task | Gold eval | Gold tests | No-op eval | No-op tests | Teardown |
| --- | --- | --- | --- | --- | --- |
| django__django-13343 | 27.9 | 9.9 | 23.8 | 7.3 | 15.3–15.4 |
| django__django-13809 | 63.6 | 46.0 | 62.1 | 45.5 | 15.3 |
| django__django-14017 | 26.6 | 8.9 | 24.2 | 7.7 | 15.3 |
| sphinx-doc__sphinx-8621 | 21.4 | 5.0 | 20.1 | 4.1 | 15.3 |
| sphinx-doc__sphinx-9658 | 20.2 | 3.7 | 18.8 | 2.8 | 15.3 |
| **Total** | **159.7** | **73.5** | **149.0** | **67.4** | **~76.5 each** |

All [MEASURED], one run per source.

### Gold evaluation, run 1 vs run 2

| Task | Run 1 (entry #2) | Run 2 | Difference |
| --- | --- | --- | --- |
| django__django-13343 | 26.5 | 27.9 | +1.4 |
| django__django-13809 | 69.5 | 63.6 | −5.9 |
| django__django-14017 | 25.6 | 26.6 | +1.0 |
| sphinx-doc__sphinx-8621 | 21.2 | 21.4 | +0.2 |
| sphinx-doc__sphinx-9658 | 24.0 | 20.2 | −3.8 |

[MEASURED — first repeat measurement of the same tasks]

### Findings
- **Teardown is a fixed ~15.3 s per evaluation** (10 of 10 tasks,
  15.3–15.4 s) — about half of all evaluation time. Cause: the
  harness's `docker stop --time=15` (entry #2).
- **Evaluation ≈ the task's test runtime + ~17 s** (teardown plus
  ~1–2.5 s for container start, patch and grading). The slowest dev
  task, django-13809, is slow because of its tests (~46 s), not
  overhead.
- **Run-to-run variation in evaluation time: up to ~6 s per task**
  across two gold runs [MEASURED, n=2]. Too few runs for an interval;
  enough to rule out drawing timing conclusions from one run.
- **Verdicts were identical across runs** — 10 of 10 evaluated tasks
  gave the same outcome as entry #2 [MEASURED, n=2 per task].

**Limits:** two runs per task; timing only. No model called, so no
cost or token figures yet.

---

## Entry #4 — First CI benchmark: gold on the dev split (Week 1 step 6)

**Date:** 2026-09-29
**Question:** Does the benchmark workflow reproduce local verdicts on
GitHub's runners, with one record per task?
**Answer:** Yes. 5/5 resolved — identical to entries #2 and #3.
**Run:** github.com/MalayVyas/blindspots/actions/runs/36506913529
(`ci-gold-1`, commit cc6492a, ubuntu-24.04 standard runners, one
runner per task). Cost: $0.
**Dataset revision confirmed (ADR-0012 assumption):** Hugging Face
accepted the pinned revision `78f471bf655a3137b2e8a75af1501690ec009ec3`,
and the CI record's `dataset_revision` is the same ID — local and CI
score identical task definitions [MEASURED — record environment block].
**Environment differences:** Python 3.11.16 on both; Docker 28.0.4 on
CI vs 29.6.2 locally.

| Task | Eval (s) | Tests (s) | Teardown (s) | Job (s) |
| --- | --- | --- | --- | --- |
| django__django-13343 | 23.4 | 7.0 | 15.2 | 95 |
| django__django-13809 | 53.7 | 37.5 | 15.2 | 128 |
| django__django-14017 | 21.3 | 5.1 | 15.3 | 96 |
| sphinx-doc__sphinx-8621 | 19.5 | 3.7 | 15.2 | 109 |
| sphinx-doc__sphinx-9658 | 18.5 | 2.8 | 15.1 | 94 |

All [MEASURED], one run. Whole workflow ~3 min, trigger to summary.

### Findings
- **Local and CI verdicts agree** on all 5 tasks.
- **CI test runtimes were 20–40% below local** on all 5 tasks (e.g.
  django-13809: 37.5 s vs 46.0 s) [MEASURED, one run each]. Plausible
  cause: native Linux Docker vs WSL2 + Docker Desktop [JUDGEMENT,
  untested]. Timing comparisons must therefore never mix machines;
  the `machine` field in every record makes that checkable.
- **Teardown is machine-independent:** 15.1–15.3 s, now 15 of 15
  evaluations across two machines.
- **Parallel matrix:** total time is set by the slowest task
  (django-13809, 2 min 8 s), not the sum.

**Limits:** one CI run; artifacts expire after 90 days (ADR-0012 open
item — not a published result, so no permanent copy yet).

---

## Entry #5 — First model calls: DeepSeek adapter smoke test (Week 2 step 1)

**Date:** 2026-09-29
**Question:** Does the DeepSeek adapter read tokens, cache fields and
cost back correctly, and does the cache actually hit?
**Answer:** Yes. 6 calls succeeded (2 more failed before the request was
sent). Cache hit + miss = input tokens on every call, and billed cost
matched a hand calculation on all six. Total spend about $0.0010.
**Setup:** `scripts/deepseek_smoke.py`, commit 2a95814 (runs made on
the same code just before it was committed), `deepseek-flash`,
temperature 0, prompt = `blindspots/record.py` (~1,400 tokens) plus a
one-line question, sent twice per run. Price table
`deepseek-2026-09-29`. Local WSL2.

| Run (UTC) | Thinking | Peak | Call | Input = hit + miss | Output (reasoning) | Billed | Reference |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 03:07 | enabled, low | yes | 1 | 1,449 = 0 + 1,449 | 86 (24) | $0.000538 | $0.000269 |
| | | | 2 | 1,449 = 1,280 + 169 | 70 (27) | $0.000142 | $0.000071 |
| 05:23 | enabled, low | no | 1 | 1,449 = 1,280 + 169 | 126 (54) | $0.000105 | $0.000105 |
| | | | 2 | 1,449 = 1,280 + 169 | 67 (11) | $0.000069 | $0.000069 |
| 05:24 | disabled | no | 1 | 1,424 = 1,280 + 144 | 39 (0) | $0.000049 | $0.000049 |
| | | | 2 | 1,424 = 1,280 + 144 | 48 (0) | $0.000054 | $0.000054 |

All [MEASURED], one run per row. Costs checked by hand against the
price table.

### Findings
- **The cache hits on repeat calls and lasted at least 2 h 16 min.**
  The first call at 05:23 hit a prefix last sent at 03:07.
- **Every hit was exactly 1,280 tokens (20 × 64),** consistent with a
  64-token cache unit [JUDGEMENT, 5 observations].
- **Thinking mode adds 25 input tokens** to identical messages, and
  the cache is shared between the two modes.
- **Output isn't deterministic at temperature 0, in either mode.**
  Output tokens varied 39–48 with thinking off and 67–126 with it on.
  Reasoning tokens varied 11–54.
- **Time of day alone changed the price 5x** for the same calls
  ($0.000538 at peak with no cache hit vs $0.000105 off-peak with a
  hit). This is the case for the reference cost (ADR-0013).
- **Network:** two runs failed during the TLS handshake
  (`UNEXPECTED_EOF_WHILE_READING`) on the home connection. Nothing was
  sent, so nothing was billed. With a VPN on, every call succeeded.
  The adapter stopped after one attempt each time, as intended.

**Open:** whether `completion_tokens` includes reasoning tokens. The
check (reasoning ≤ output) passed on all 4 thinking calls, but that
fits either reading. Confirm against the DeepSeek usage page.

**Limits:** one short prompt, 6 calls. Not an agent run and not a
cost-per-task figure.

---

## Entry #6 — Spend ceiling, live: a deliberately broken loop (Week 2 step 2)

**Date:** 2026-09-29
**Question:** Does the accountant stop a loop with no stop condition,
with real API calls and real money?
**Answer:** Yes, by both the cost cap and the clock. Billed spend stayed
under the cap.
**Setup:** `scripts/ceiling_demo.py`, commit 029f95f, `deepseek-flash`,
thinking off, `max_tokens` 400, prompt "Count from 1 to 150" (50 bytes),
off-peak. Other limits set loose so that only the one being tested
could fire.

| Run | Limit | Calls | Tokens in / out | Billed | Ceiling $ | Stopped by |
| --- | --- | --- | --- | --- | --- | --- |
| ceiling-cost-20260929T055052Z | $0.001 cap | 2 | 34 / 598 | $0.000364 | $0.000728 | cost: $0.0012225 projected, **refused before sending** |
| ceiling-wall-20260929T055111Z | 5 s | 3 | 51 / 897 | $0.000546 | $0.001586 | wall-clock: 5.0024 s, **caught after the call** |

All [MEASURED], one run each. Both records re-validated on reading. The
Week 1 schema-1 records (`dev-gold-2`) still load under schema 2.

### Findings
- **The ceiling holds with real money:** billed $0.000364 against a
  $0.001 cap. The refusal figure ($0.000728 spent + $0.000495 worst
  case for the next call) matches a hand calculation exactly.
- **The per-call timeout doesn't bound total time**, because the
  network library times each stage (connect, send, wait) separately.
  The job overran by 2.4 ms and the after-call check caught it.
- **The bytes-to-tokens estimate was about 2.9x loose on this prompt**
  (50 bytes, 17 tokens).
- **A 17-token prompt got no cache hit**, consistent with the
  64-token block (entry #5).

**Not tested live:** a call cut off by the timeout. That's covered by a
unit test only, so whether DeepSeek bills an abandoned call is still
open.

**Running total of model spend:** about $0.002 (entries #5 and #6).

---

## Entry #7 — First agent runs: dev task 1, end to end (Week 2 steps 3–4)

**Date:** 2026-09-30
**Question:** Does the simple agent produce a patch the harness can
score, what does an attempt cost, and how stable is the outcome?
**Answer:** Yes. Two scored attempts on the same task with identical
input: one unresolved, one **resolved**. With a warm cache an attempt
cost about $0.0003–0.0004.
**Setup:** `deepseek-flash`, thinking off, temperature 0, `max_tokens`
4,096, ADR-0014 limits, prompts `prompts/simple/`, file selection by
keyword (ADR-0015). Task `django__django-13343`. Local WSL2, off-peak.

| Attempt | Commit | Input = cached + uncached | Output | Billed | FAIL_TO_PASS | PASS_TO_PASS | Outcome |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `agent_try` (04:13 UTC) | b8298b1 (pre-commit) | 27,522 = 0 + 27,522 | 641 | $0.00451 | not scored | not scored | patch produced |
| `dev-agent-1` (04:25 UTC) | b8298b1-dirty | 27,522 = 27,388 + 134 | 373 | $0.000326 | 0 / 1 | 130 / 130 | **unresolved** |
| `dev-agent-2` (04:31 UTC) | fb25fab | 27,522 = 27,388 + 134 | 433 | $0.000362 | 1 / 1 | 130 / 130 | **resolved** |

All [MEASURED], one attempt per row. Harness evaluation 39.3 s and
40.3 s. `agent_try` was a look at the agent before the runner existed;
it was not scored and is not counted below.

### Findings
- **The outcome varies between runs, not just the wording.** Identical
  input at temperature 0 gave a failed fix and a correct one. One run
  per task would have reported this task as 0% or 100% by luck. A
  5-task dev score from single runs is mostly noise; ADR-0008's
  repeats are necessary, not a nicety.
- **Why run 1 failed:** it did half the fix. It saved the callable
  storage (`self._storage_callable`) but never returned it from
  `deconstruct()`, so the one FAIL_TO_PASS test
  (`test_deconstruction`, `FieldCallableFileStorageTests`) still
  failed. Nothing else broke. Run 2 did both halves.
- **The `agent_try` patch would likely have broken Django:** it made
  `storage` a read-only property, which `__init__` then assigns to
  [JUDGEMENT — read from the patch; not scored].
- **Cache:** 99.5% of input came from the cache on both scored runs
  (27,388 of 27,522). A warm attempt cost 13x less than the cold one.
  27,388 is not a multiple of 64, which weakens the "64-token block"
  reading of entry #5; left unexplained.
- **Cost per fix on this task:** $0.000688 spent ÷ 1 resolved =
  **$0.00069** [MEASURED, n=2, warm cache, off-peak]. A cold-cache
  attempt would cost about $0.0045.
- **Localisation:** the gold file (`django/db/models/fields/files.py`)
  was shown in all three attempts. Both failures were "found it, fixed
  it wrong", not "couldn't find it".
- **The accountant's byte estimate was 4.4x loose** on real code
  (121,914 bytes, 27,522 tokens). No limit came close to firing.
- **File selection ranked a re-export module first.**
  `django.db.models.FileField` resolved to `django/db/models/__init__.py`
  (160 points), which only re-exports `FileField`; the defining file
  scored 20. It was still included. Not tuned on one task; a baseline
  for the December localiser.
- **SWE-bench images add an empty commit on top of `base_commit`**
  (HEAD `e5321912f5` "SWE-bench", parent `ece18207cb`, no file
  changes). Checking commit IDs refused a correct copy; the workspace
  now compares file trees (ADR-0015).
- **Safety checks at $0:** two runs refused to start because Docker
  Desktop was not running.

**Limits:** one task, two scored attempts. Not a resolve rate.

**Running total of model spend:** about $0.007 (entries #5–#7).

---

## Entry #8 — The agent in CI, and what the first eight scored attempts show

**Date:** 2026-09-30
**Question:** Does the agent run end to end in GitHub Actions, and where
does it fail?
**Answer:** Yes: 6 CI attempts over two runs, with the model reached
without a VPN. Across all 8 scored attempts on the dev split, **both
resolves came from tasks where the right file was shown; every task
where it wasn't failed.**
**Runs:** `ci-agent-1` (run 36673499717, commit d39fc79) and
`ci-agent-2` (run 36674272992, commit 8648578). `deepseek-flash`,
thinking off, ADR-0014 limits.

| Run | Task | Outcome as recorded | Gold file shown | In / cached / out | Billed |
| --- | --- | --- | --- | --- | --- |
| ci-agent-1 | django-13343 | patch_apply_failed → **actually tests_errored** | yes | 27,522 / 27,388 / 641 | $0.00049 |
| ci-agent-1 | django-13809 | patch_apply_failed | **no files chosen** | 389 / 0 / 4,096 (cut off) | $0.00252 |
| ci-agent-1 | sphinx-8621 | patch_apply_failed | no | 24,842 / 0 / 345 | $0.00393 |
| ci-agent-1 | sphinx-9658 | unresolved | no | 27,746 / 0 / 372 | $0.00439 |
| ci-agent-2 | django-14017 | **resolved** | yes | 25,801 / 0 / 338 | $0.00407 |
| ci-agent-2 | sphinx-8621 | patch_apply_failed | no | 24,842 / 24,704 / 395 | $0.00033 |

All [MEASURED]. `ci-agent-1` was dispatched with all five tasks.
django-14017 was refused there at $0 by the workspace check (see the
image findings below).

### Findings
- **CI reaches DeepSeek without a VPN**, so the local VPN requirement
  doesn't apply to published runs.
- **Localisation decided every outcome so far.** Gold file shown: 2
  tasks, which produced both resolves (13343 local run 2, 14017) plus
  one crash and one incomplete fix. Not shown: 3 tasks, all failed
  [MEASURED, 8 attempts; a pattern, not yet a significant result].
- **How keyword selection fails:** a behaviour-only issue
  (sphinx-8621) matched one irrelevant file via the word `between`.
  For 13809 nothing matched at all, and the model wrote 4,096 tokens
  from memory and was cut off. In 8621 the model said it couldn't see
  the file it needed. A single-call agent has no way to ask for it.
- **A mislabel, found and corrected:** report.json's
  `patch_successfully_applied` is False whenever no test results are
  found, not only when a patch fails to apply [PRIMARY — swebench 5.0.2
  `grading.py`]. The 13343 patch applied cleanly, then crashed Django
  at import (`AttributeError: can't set attribute`, a read-only
  property assigned in `__init__`). New outcome `tests_errored`,
  decided from the harness's own log markers. The existing record
  keeps its old label (ADR-0011).
- **Exact matching refused correctly:** both 8621 failures quoted code
  that isn't in any file shown to the model. The case for fuzzy
  matching (ADR-0015 reversal condition) isn't met.
- **SWE-bench image quirks:** Sphinx images commit packaging edits
  (`setup.py` dependency pins, `-rA` in `tox.ini`). Some Django images
  commit a `chmod -R 777`, so every file's permissions change while no
  file's contents do. The workspace now compares file contents
  (ADR-0015 amendment).
- **Where the cache fields really are:** `prompt_cache_hit_tokens` /
  `prompt_cache_miss_tokens` sit at the top level of `usage`, not
  nested as the API reference shows. `prompt_tokens_details.cached_tokens`
  also appears [MEASURED, reasoning-check call].
- **Output includes reasoning:** 191 output tokens = 189 reasoning + 2
  answer [MEASURED], so the cost formula is right. Closes entry #5's
  open item.
- **Cost:** a cold attempt costs $0.0039–0.0044; a warm (cached) one
  about $0.0003–0.0005. Across all 8 scored attempts: $0.01642 spent ÷
  2 resolved = **$0.0082 per fix** [MEASURED, n=8, mixed warm and cold,
  off-peak].

**Limits:** 5 tasks, uneven repeats (13343 ×3, 8621 ×2, others ×1).
Not a resolve rate.

**Running total of model spend:** about $0.023.

---

## Entry #9 — Caching measured: cold vs warm, three repeats (Week 3)

**Date:** 2026-10-02 (runs 2026-10-01 22:52–23:17 UTC, all off-peak)
**Question:** What does an attempt cost with and without the cache,
how much of the input is served from cache, and how much does it vary
between repeats?
**Answer:** With 25–28K input tokens, a cold attempt costs **$0.0041**
and a warm one **$0.0003**, about 13x less. 99.2% of warm input tokens
came from the cache. Resolved 1/20.
**Setup:** commit 630bc4c, `deepseek-flash`, thinking off, temperature
0, `max_tokens` 4,096, ADR-0014 limits, prompts unchanged (same prompt
hashes on all 20). Runs `ci-w3-cache-1/2/3` (caching on, dispatched
~10 min apart) and `ci-w3-bust-1` (`--cache-bust`, ADR-0016). Each
attempt is labelled cold or warm by its measured cache-hit share
(`scripts/week3_report.py`). Busted attempts carry about 30 extra input
tokens from the marker.

| Class | Attempts | Mean / attempt | 95% interval | Range |
| --- | --- | --- | --- | --- |
| Warm (caching on) | 15 | $0.00060 | $0.00027–0.00115 | $0.00012–0.00248 |
| Busted (cold) | 5 | $0.00381 | $0.00315–0.00427 | $0.00252–0.00438 |
| Warm, excl. 13809 | 12 | $0.00032 | $0.00023–0.00043 | $0.00013–0.00053 |
| Busted, excl. 13809 | 4 | $0.00413 | $0.00391–0.00435 | $0.00386–0.00438 |

Intervals: bootstrap, resampling tasks rather than attempts, 10,000
draws. Reference cost equals billed cost on all 20 (none at peak).
[MEASURED]

| Task | Warm ×3 | Busted | Ratio | Gold file shown | Outcomes (warm; busted) |
| --- | --- | --- | --- | --- | --- |
| django-13343 | $0.00040–0.00053 | $0.00438 | 9.3x | yes | unresolved, tests_errored ×2; **resolved** |
| django-13809 | $0.00012–0.00248 | $0.00252 | 1.5x | no files chosen | patch_apply_failed ×2, empty_patch; patch_apply_failed |
| django-14017 | $0.00020 ×3 | $0.00397 | 20.0x | yes | unresolved ×3; unresolved |
| sphinx-8621 | $0.00013–0.00038 | $0.00386 | 13.0x | no | patch_apply_failed ×4 |
| sphinx-9658 | $0.00031–0.00034 | $0.00431 | 13.3x | no | unresolved ×4 |

### Findings
- **Cache verified two ways.** All 5 busted attempts reported 0 cached
  tokens (`cache_bust_verified`). In all 20 raw responses,
  `prompt_tokens_details.cached_tokens` equalled
  `prompt_cache_hit_tokens`.
- **Hit rate 99.2%** of input tokens on warm attempts (316,401 /
  318,900). The uncached remainder is a fixed tail per task (134 tokens
  on 13343, as in entry #7).
- **There was no cold dispatch.** `ci-w3-cache-1` was already 99%
  cached from the 30 September runs, so the cache lasted at least about
  43 hours. Classing attempts by measured hits instead of dispatch
  order is required, not optional.
- **Caching moves the cost lever from input to output.** Output is 4%
  of a busted attempt's cost and 67% of a warm one's. A hit costs
  $0.003/M against $0.15/M for a miss [PRIMARY — price table
  `deepseek-2026-09-29`].
- **django-13809:** no files chosen, 389-token prompt, model cut off at
  4,096 tokens in 3 of 4 attempts. Caching can't help a task where
  output dominates. Candidate for the December localiser: no files
  found, no call.
- **Response time** 1.4–3.4 s per call, cached or not; 13.5–15.3 s for
  the cut-off calls. No speed-up from caching observed.
- **Variation between repeats:** cost is tight within a task, except
  where the output length swings (8621: 62–478 tokens). Outcomes vary:
  13343 gave unresolved, tests_errored, tests_errored, resolved. 14017
  gave a 152-token answer four times and was unresolved each time,
  though it resolved on 2026-09-30 with identical input (entry #8).
- **Localisation:** gold file shown in 8 of 20 attempts (1 resolved),
  not shown in 12 (0 resolved). Since entry #7: 3/12 resolved when
  shown, 0/16 when not (one-sided Fisher exact p ≈ 0.07, treating
  attempts as independent) [ESTIMATE].
- **Resolve rate 1/20 = 5%** (Wilson 95% interval 0.9–23.6%). **Cost
  per fix $0.028** — one fix, so no meaningful interval.

**Limits:** 5 tasks; one busted attempt per task; all off-peak; one
model.

**Running total of model spend:** about $0.051.

**Addendum (2026-10-02): wall-clock.** A scored attempt takes ~20–27 s:
model call 1.4–3.4 s, harness evaluation 18.0–23.5 s, of which ~15 s is
container teardown. Unscored attempts (no usable patch) take 1.8–15.5 s,
almost all model time (overhead 0.1–0.3 s). Workspace preparation runs
before the attempts and is not timed. Gap: scored records keep only the
harness's timing, so agent time is read from the transcript's
`latency_s`. An `agent_s` field needs record schema 3 (ADR-0011) — Week 4.
[MEASURED]
Gap closed by schema 3 (ADR-0011 amendment, 2026-10-04).

---

## Entry #10 — agent:mini against agent:simple on the dev split (Week 4)

**Date:** 2026-10-09 (headline runs 2026-10-04, 2026-10-07 and
2026-10-08 UTC)
**Question:** Does a minimal agent that searches the repository itself
(mini-swe-agent, stock prompts and loop, our transport) beat the
one-call agent:simple, and at what cost?
**Answer:** On resolve rate, yes: agent:mini resolved **14/15**
attempts (93%, Wilson 95% 70–99%) against agent:simple's **1/20** (5%,
1–24%); the intervals are separate. Per fix the 95% intervals overlap
($0.0028–0.0134 against $0.0091–unbounded). Point estimates: $0.0076
per fix against $0.028; $0.0071 per attempt against $0.0014.
**Setup:** tag `mini-baseline-2` (commit 985273b), `mini-swe-agent`
2.4.6 stock SWE-bench config, `deepseek-flash`, thinking off,
temperature 0, `max_tokens` 4,096, ADR-0018 limits (75 calls, 5M input
tokens, 40K output tokens, 1,200 s, $0.10 at peak price), agent
container with `--network none`. Headline runs `ci-mini-net-1`
(2026-10-04), `ci-mini-net-2` (2026-10-07) and `ci-mini-net-4`
(2026-10-08), one attempt per task each, as pre-registered on
2026-10-07 (state.md, commit d7a2e1b). Comparator: results entry #9's 20
attempts of agent:simple (`ci-w3-cache-1/2/3` + `ci-w3-bust-1`, commit
630bc4c). Every figure comes from `scripts/entry10_report.py` with the
pre-registered arguments, reading the run-records archives (archive
SHA-256 prefixes: net-1 `1d305a20`, net-2 `88041dc0`, net-4 `c4410e85`).
`--records` was the only argument added; it gives the archive location
and changes no analysis. Costs are reference cost (off-peak list price,
ADR-0013); billed cost is shown where it differs. Cold/warm by the
ADR-0018 amendment rule.

| Agent | Attempts | Resolved | Wilson 95% | Cost / attempt (95%) | Cost / fix (95%) |
| --- | --- | --- | --- | --- | --- |
| agent:mini, headline (net-1, 2, 4) | 15 | **14 (93.3%)** | 70.2–98.8% | $0.00710 ($0.00282–0.01138) | $0.00761 ($0.00282–0.01336) |
| agent:mini, two-day line (net-1, 2) | 10 | 9 (90.0%) | 59.6–98.2% | $0.00678 ($0.00285–0.01094) | $0.00753 ($0.00285–0.01561) |
| agent:simple (entry #9) | 20 | 1 (5.0%) | 0.9–23.6% | $0.00140 ($0.00119–0.00167) | $0.02797 ($0.00907–unbounded) |

Cost intervals: bootstrap, resampling tasks rather than attempts, seed
10, 10,000 draws. [MEASURED]

| Task | Outcomes (net-1; net-2; net-4) | Calls of 75 | Reference cost | `agent_s` |
| --- | --- | --- | --- | --- |
| django-13343 | resolved ×3 | 14, 15, 14 | $0.00198–0.00243 | 24.8–28.8 |
| django-13809 | resolved ×3 | 18, 10, 19 | $0.00210–0.00307 | 17.4–59.9 |
| django-14017 | resolved ×3 | 22, 24, 21 | $0.00375–0.00494 | 37.0–40.9 |
| sphinx-8621 | unresolved; resolved; resolved | 32, 50, 34 | $0.00893–0.01683 | 137.7–201.2 |
| sphinx-9658 | resolved ×3 | 35, 65, **71** | $0.00696–0.02099 | 69.4–318.2 |

Totals, headline: reference $0.10649, billed $0.14522; 444 calls;
6,171,391 of 6,343,589 input tokens from cache (97.3%); 0 of 15
attempts cold. [MEASURED]

### Findings
- **agent:mini resolved every task at least once; agent:simple never
  resolved a task whose gold file keyword selection missed (0/16,
  diagnostic).** The 0/16 is over all 26 of agent:simple's CI attempts
  (2/10 when the gold file was shown) and uses agent:simple's runs only.
  agent:mini patched the gold file in 14 of 15 headline attempts.
  [MEASURED] Reading this as "searching the repository is what wins" is
  a causal claim this entry cannot make: the two agents also differ in
  prompts, loop and call count (one call against 10–71) [JUDGEMENT].
- **Resolved without touching the gold file:** sphinx-9658 in net-4
  (and in the deviation run net-3) was resolved with a patch to a
  different file than the gold patch's. The harness's tests decide;
  the file match is a diagnostic. [MEASURED]
- **Cost is driven by the number of calls.** Of mini's headline
  reference cost ($0.10649), output tokens are 58.4% ($0.06215),
  uncached input 24.3% ($0.02583, 172,198 tokens) and cached input
  17.4% ($0.01851, 6,171,391 tokens) [MEASURED — token counts at the
  off-peak price table]. The two Sphinx tasks are 74% of headline
  reference cost (8621 and 9658: $0.07902 of $0.10649) [ESTIMATE —
  arithmetic on the table].
- **Cache hits, warm attempts only: mini 97.3%, simple 99.2%.** All 15
  mini attempts were warm; simple's 15 warm attempts had 316,401 of
  318,900 input tokens cached (entry #9). Simple's all-attempt figure,
  74.4%, includes its 5 busted attempts, where caching was deliberately
  defeated (ADR-0016), so it is not compared here. Mini's lower warm
  share is the uncached tail each new step adds. [MEASURED]
- **Every attempt was warm.** Call 1 of each headline attempt had more
  cached tokens than the 128-token shared prefix (1,152–2,048) [MEASURED
  — by the ADR-0018 amendment rule]. ci-mini-1 and the earlier repeats
  had already sent the same first prompts, so no headline figure is a
  cold-cache figure; cold attempts would cost more [JUDGEMENT].
- **net-4 ran at peak price.** It ran on Thursday 2026-10-08,
  02:04–02:10 UTC, inside DeepSeek's 01:00–04:00 UTC peak window; all
  159 of its calls were billed at peak rates, exactly 2.00x reference on
  every task (billed $0.07745 against reference $0.03872). net-1 (a
  Sunday) and net-2 (00:16 UTC) had no peak calls. Headline figures use
  reference cost, so this changes billed spend only. [MEASURED]
- **sphinx-9658 came close to the call limit.** It used 35, 65 and 71
  of 75 calls (71 also in net-3). In net-4: 71 calls, `agent_s` 318 s of
  1,200 s, $0.04198 at peak price = 42% of the $0.10 cap [MEASURED].
  The call limit, not the spend cap, is the limit that binds for mini on
  this task [JUDGEMENT]; ADR-0018's sizing expected the cap to refuse at
  about 56–94 calls [ESTIMATE — ADR-0018].
- **ADR-0018 reversal condition not met.** No headline attempt ended on
  a limit or as `provider_error`: 0/5 in each of net-1, net-2 and net-4
  (0/5 in net-3 too). The limits stay as they are. [MEASURED]
- **The model names upstream fixes from memory.** On django-13343 it
  grepped for `_storage_callable`, the name the gold patch introduces,
  at call 4–6 of every headline attempt (and in ci-mini-1 and net-3);
  the name is not in the repository and appeared in no output until
  after its own edit. agent:simple did the same in entry #7
  (`self._storage_callable`, with no repository access at all). On
  django-14017 it cited "ticket #32448" and commit hashes as "the actual
  Django fix" (net-1, net-2, net-4) (not checked against Django's
  history); `getattr(other, 'conditional',
  False)` itself is already in the repository (`expressions.py`) and
  was in an output (call 4) before the model wrote it, so it is not
  evidence of recall. On sphinx-8621 the recall was wrong: in net-1 and
  net-2 it "recalled" the upstream pattern as `(-|\+|\^|\s+)`, the
  unfixed pattern, and wrote its own algorithm after "No internet".
  [MEASURED — transcripts] That the dev tasks are partly answered from
  training data is likely [JUDGEMENT]; this is input to January's
  contamination check, not a correction to these figures.
- **Network tripwire: 5 entries in 15 headline attempts, all blocked.**
  Each was a `pip download` of a newer Sphinx release (sphinx-8621 in
  net-1, net-2, net-4; sphinx-9658 in net-2, net-4). Every output shows
  `Temporary failure in name resolution`. All 5 report `returncode` 0,
  which is the exit status of the pipeline's last command (`| tail`),
  not of pip. [MEASURED]
- **Variation between repeats** is mostly in calls, not outcome:
  sphinx-9658 ranged from 35 to 71 calls and $0.00696 to $0.02099 with
  the same outcome. sphinx-8621 is the one task whose outcome varied.
  [MEASURED]

### Deviation: `ci-mini-net-3` (in no figure)
net-2 (00:16 UTC) and net-3 (00:25 UTC) both ran on 2026-10-07, against
ADR-0008's repeats on separate days. As pre-registered, net-4 replaced
net-3 in every figure. net-3's numbers: 4/5 resolved (sphinx-8621
unresolved after 46 calls), reference $0.04252, 169 calls, 97.7% cache
hits, 0/5 cold, sphinx-9658 71 of 75 calls. One tripwire entry
(django-14017, `pip download django==4.0`): output suppressed; `ls
/tmp/` listed nothing. [MEASURED]

### Void: `ci-mini-1` (finding only)
5/5 resolved, reference $0.02719, but in 2 of 5 attempts (sphinx-8621,
sphinx-9658) mini downloaded newer Sphinx releases or cloned upstream
and read the fix before editing. The task images were clean. This is
why every agent container now runs without network (ADR-0018
amendment). [MEASURED]

**Local smoke `dev-mini-smoke-1`** (django-13343, off-peak): resolved,
12 calls, 58,254 in / 1,729 out, 89.4% cached, billed $0.00212,
`agent_s` 23.6 s. Not in any figure (local, before `--network none`).
[MEASURED, n=1]

**Limits:** Not an ADR-0008 comparison: the agents differ in prompts
and loop, not only model binding. A baseline. 5 dev tasks; 3 attempts
per task for mini, 4 for simple; one model; all mini attempts warm;
agent:simple ran a week earlier on a different commit. sphinx-9658 used
71 of 75 calls twice; the call limit may bind on December's harder
tasks and longer pipeline.

**Running total of model spend:** about $0.272 (about $0.084 before
these runs, plus billed $0.02702 net-1, $0.04076 net-2, $0.04253 net-3,
$0.07745 net-4) [ESTIMATE — sum of billed figures on a rounded base].

**Addendum (2026-10-09): task-clustered resolve-rate interval.** Added
after review of the README draft; the figures above are unchanged. The
Wilson intervals treat every attempt as independent, but the attempts
are 3 (mini) or 4 (simple) repeats of the same 5 tasks, and repeats of
a task are correlated: the same task tends to resolve or fail every
time. `scripts/entry10_report.py` now also prints a resolve-rate
bootstrap that resamples tasks rather than attempts (seed 10, 10,000
draws, the same method as the cost intervals), from the same
pre-registered run arguments; no argument changed.

| Agent | Resolved | Wilson 95% | Task bootstrap 95% | Tasks resolved at least once |
| --- | --- | --- | --- | --- |
| agent:mini, headline (net-1, 2, 4) | 14/15 (93.3%) | 70.2–98.8% | 80.0–100.0% | 5/5 |
| agent:mini, two-day line (net-1, 2) | 9/10 (90.0%) | 59.6–98.2% | 70.0–100.0% | 5/5 |
| agent:simple (entry #9) | 1/20 (5.0%) | 0.9–23.6% | 0.0–15.0% | 1/5 |

[MEASURED] The two agents' task-bootstrap intervals do not touch
(15.0% against 80.0%).

With 5 tasks this interval is rough, and here it is *narrower* than
Wilson, not wider. A percentile bootstrap over 5 tasks can take only a
handful of values, cannot see variation the 5 tasks do not show, and
collapses where they agree: for agent:simple only one task ever
resolved, and for `ci-mini-1` (5/5) it is 100.0–100.0%. Neither
interval should be read as more than "far apart at n=5"
[JUDGEMENT]. Wilson stays the headline interval: the task bootstrap
is narrower, and a method added after review may only make a claim
more cautious.
