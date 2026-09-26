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
