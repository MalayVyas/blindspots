# Blindspots — Decision log

One entry per significant technical decision. Format: context, options
considered, decision, consequences, reversal condition.

An ADR records *why* a choice was made and *what would undo it*. If a
decision here turns out wrong, the entry is superseded by a new one
rather than edited — the reasoning trail is the point.

---

## ADR-0001: AWS as the primary cloud

**Date:** 2026-09-22 · **Revised:** 2026-09-26 · **Status:** accepted

> **Revision note.** The original version of this ADR justified AWS on
> the strength of up to $200 in new-account credits funding both
> infrastructure and model calls through Bedrock. That premise was
> false: the credits were already spent, and the account has since
> moved to the Paid plan. The conclusion survives on different
> reasoning, recorded below. The original reasoning is preserved in
> git history.

### Context

Blindspots needs a small amount of cloud infrastructure for the
live-mode path: receive a GitHub webhook, queue a job, run it, store
results. It does **not** need cloud infrastructure for benchmarking —
see ADR-0004. The project runs six months on a student budget with no
credits remaining.

### Options considered

1. **AWS.** No credits left, so every service is pay-as-you-go. The
   always-free tier has no expiry and covers this workload almost
   entirely: Lambda 1M requests and 400,000 GB-seconds per month, SQS
   1M requests, DynamoDB 25 GB, CloudWatch 10 metrics and alarms plus
   5 GB of logs, SSM Parameter Store standard tier. S3 and API Gateway
   fall to pay-as-you-go pricing measured in cents at this volume.
   Most commonly requested cloud in Australian job advertisements.
2. **Azure.** $100 of Azure for Students credit is available and does
   not expire for twelve months. Less common in local job ads. The
   credit is more valuable spent on models than on infrastructure.
3. **No cloud at all.** Everything local plus GitHub Actions. Cheapest
   and simplest; costs the project its strongest CV keywords and the
   live-mode story.

### Decision

AWS, for the live-mode slice only, on the always-free tier. Estimated
cost $0–3 per month, entirely from S3 and API Gateway overflow. The
Azure credit is reserved for model spend, not infrastructure.

### Consequences

- The serverless slice is effectively free and stays free indefinitely.
- No credit cliff and no six-month account-closure clock, because the
  account is on the Paid plan.
- A Budgets alarm at $5/month is mandatory: with no credit balance
  acting as a ceiling, a misconfiguration bills real money.
- This is deliberately more infrastructure than the workload requires.
  See ADR-0006.

### Reversal condition

If the AWS bill exceeds $10 in any month, or if February's time budget
disappears, drop the cloud slice entirely. The project is complete
without it.

---

## ADR-0002: AWS region

**Date:** 2026-09-22 · **Closed:** 2026-09-26 · **Status:** withdrawn

The open question was whether to run in Sydney (ap-southeast-2) or a
US region, driven by Bedrock model availability. ADR-0003 removes
Bedrock from the critical path and ADR-0004 removes EC2 entirely, so
nothing latency- or availability-sensitive remains. The Lambda, SQS
and DynamoDB slice runs in ap-southeast-2 for proximity, and the
choice no longer carries consequences worth an ADR.

---

## ADR-0003: Bedrock off the critical path

**Date:** 2026-09-26 · **Status:** accepted

### Context

The original plan routed model calls through Amazon Bedrock so that
AWS credits would pay for them and one bill would cover several model
providers. There are no credits.

### Options considered

1. **Bedrock as the primary model gateway.** One bill, one set of
   credentials, several providers. But without credits it is not
   cheaper than calling providers directly; new AWS accounts have been
   reported at very low request-per-minute quotas on frontier models;
   and Bedrock lags the first-party APIs on prompt caching and batch
   features, which ADR-0005 shows are the dominant cost lever.
2. **Direct provider APIs only.** Cheapest, full feature access,
   immediate. Loses a CV keyword and the single-bill convenience.
3. **Direct APIs primary, Bedrock as one adapter among several.**

### Decision

Option 3. Every measured run goes through direct provider APIs. The
provider-adapter layer includes a Bedrock adapter, and one
demonstration run is executed through it so the multi-provider claim
is real and testable.

### Consequences

- No dependency on AWS quota increases before a benchmark can run.
- Full access to prompt caching and batch pricing.
- The Bedrock adapter still appears in the codebase and the write-up.
- Slightly more surface area to maintain than direct APIs alone.

### Reversal condition

If a provider's direct API becomes unavailable in Australia, or a
model needed for a role is reachable only through Bedrock, promote the
Bedrock adapter for that role and record it in `results.md`.

---

## ADR-0004: Benchmark execution platform

**Date:** 2026-09-26 · **Status:** accepted

### Context

SWE-bench evaluation needs Docker, x86 Linux, substantial RAM and
disk. The original plan provisioned an EC2 worker for this.

### Options considered

1. **EC2 worker with persistent EBS.** The SWE-bench harness documents
   a need for roughly 120 GB of disk and 16 GB of RAM for the full
   environment-image set. On AWS that means an EBS volume billed
   hourly whether or not the instance runs — roughly $12/month of
   pure idle cost, which directly contradicts the project's "nothing
   runs in the cloud when idle" constraint — plus instance time per
   run.
2. **GitHub Actions.** Standard runners are free and unlimited on
   public repositories, at 4 CPUs, 16 GB RAM and 14 GB SSD per job,
   with a 6-hour job limit, 256 jobs per matrix and 20 concurrent jobs
   on the Free plan. One task becomes one matrix job, so the 14 GB
   disk is ample — the 120 GB figure applies to caching every
   environment image at once, which a 50-task sample never does.
3. **Local machine.** Measured 2026-09-26: 16 processors, 19 GiB RAM
   after the WSL2 adjustment, ~429 GB free. Clears every requirement.

### Decision

Local for development and iteration; GitHub Actions for published
benchmark runs. No EC2, no EBS.

Local is faster to iterate on and has no per-run cost. Actions gives
every published number a public, permanently linkable CI log with the
commit that produced it — stronger evidence than a figure in a README,
and it survives any cloud account lapsing.

### Consequences

- Idle cloud cost for benchmarking falls to zero.
- The repository must be public. Acceptable; it is a portfolio piece.
  Planning documents containing personal budget detail stay out of it.
- Benchmark throughput is bounded by 20 concurrent jobs on the Free
  plan, so a 50-task run is roughly three waves.
- Locally, RAM rather than cores bounds concurrency: at 1–2 GB per
  container, 19 GiB supports about 8–10 workers. Start the harness at
  8.

### Reversal condition

If the Week 0 spike shows the 14 GB runner disk cannot hold a single
SWE-bench environment image, fall back in this order: local-only runs,
then a self-hosted runner on the development machine, then a paid
larger runner. Return to EC2 only if all three fail.

---

## ADR-0005: Prompt caching is a week-one requirement

**Date:** 2026-09-26 · **Status:** accepted

### Context

A five-agent pipeline sends the same repository context to several
agents within one task. The original plan scheduled response caching
for November, "if time".

### Options considered

1. **Cache later, once the pipeline works.** Simpler early code.
2. **Cache from the first agent.** Requires every prompt to be
   structured as `[stable context][variable instruction]` from the
   start.

### Decision

Option 2. Caching is built in October, before the second agent exists,
and cache hits are **verified by reading the cache fields in each API
response** rather than assumed.

Cached input is priced one to two orders of magnitude below fresh
input across every provider under consideration, and in a pipeline
that re-reads the same context repeatedly it is the dominant term in
the bill. Retrofitting it means restructuring every prompt, which
invalidates every measurement taken before the change.

### Consequences

- Prompt structure is constrained from the beginning: no timestamps,
  task IDs or other varying content above the stable prefix, since a
  single changed token silently disables the cache.
- Every measured cost in `results.md` is comparable, because the
  caching regime does not change mid-project.
- Verification is non-negotiable. An unverified cache is worse than no
  cache, because it produces a confident wrong number.

### Reversal condition

None expected. If a provider drops caching support, that provider's
per-task cost is re-measured and reported separately rather than
silently mixed with cached figures.

---

## ADR-0006: The AWS layer is deliberate over-engineering

**Date:** 2026-09-26 · **Status:** accepted

### Context

API Gateway, Lambda, SQS, DynamoDB, SSM and Terraform, for a system
with one user and a few dozen real runs, is more infrastructure than
the workload demands. A single script on the development machine would
do the same job.

### Decision

Build it anyway, as a narrow slice — one deployed path, fully
described in Terraform, deployed by GitHub Actions with OIDC — and say
plainly in this log and in the README that it exists for the target
job roles rather than because the problem required it.

### Consequences

- Roughly 15 hours spent on capability the project does not need.
- Every keyword in the target job advertisements is demonstrated by
  working, deployed, version-controlled infrastructure.
- Naming the trade-off explicitly reads as engineering judgement.
  Presenting it as architecture the problem demanded would read as
  inexperience, and a reviewer can tell the difference.

### Reversal condition

Cut it if January ends without a completed headline comparison. The
project is complete without this layer; it is not complete without the
measurement.

---

## ADR-0007: Task sample and dev/test split

**Date:** 2026-09-26 · **Status:** accepted

### Context

Choosing your own benchmark subset invites the accusation that it was
chosen to flatter the result. SWE-bench Verified is also known to be
contaminated: models score materially higher on it than on rotating
benchmarks built from problems postdating their training data.

### Decision

- **Test set:** SWE-bench Verified Mini, a published random 50-task
  subset of SWE-bench Verified. Using someone else's subset removes
  the cherry-picking question and makes comparison to published
  numbers free.
- **Dev split:** 5 tasks, drawn from the same subset, chosen in
  Week 1 and committed to the repository by task ID.
- **The remaining 45 tasks are not looked at until February.** No
  tuning, no inspection, no prompt iteration against them.
- **Contamination check:** a 20-task run on a rotating
  contamination-free benchmark (SWE-bench-Live or SWE-rebench),
  reported alongside the Verified Mini number. The gap between them is
  itself a result.

### Consequences

- Published numbers are comparable to other people's on the same
  subset.
- The honest number and the comparable number are both reported, which
  most portfolio projects do not do.
- 5 dev tasks is a small signal for iteration. Accepted: the
  alternative is contaminating the test set.

### Reversal condition

If 5 dev tasks proves too noisy to iterate against, expand the dev
split from tasks *outside* SWE-bench Verified Mini rather than from
within it.

### Amendment — dev split outside Mini; test-set size revisited (2026-09-29)

**Corrections to the context above.** Verified Mini is not a random
subset. It was selected by k-means clustering plus linear programming
to keep performance, test pass rates and difficulty close to the full
500 tasks while minimising Docker storage, and it uses only the
**django and sphinx** repositories [PRIMARY — make_swe_bench_verified_mini
README]. Results on Mini therefore cover two codebases, and the README
must say so.

**Change 1 — dev split.** The dev split is drawn from SWE-bench
Verified tasks **outside** Verified Mini, instead of from within it.

| Option | What it lacks |
| --- | --- |
| Dev from inside Mini (original decision) | Test set shrinks to 45; no longer the published 50, so not comparable to others' Mini numbers; the reported set contains tuned-against tasks |
| **Dev from Verified, outside Mini** | Chosen. Same two repositories and parent pool as the test set, but not filtered for storage size |

**Selection procedure** (fixed before the draw):
`scripts/choose_dev_split.py` — candidates are Verified tasks not in
Mini, from django and sphinx only; excluding the smoke-test canary
`django__django-11099` and tasks labelled ">4 hours"; seats per
repository follow Mini's mix with at least one per repository;
seeded random draw, seed `20261001`. The script reads metadata
columns only and prints nothing but aggregate counts for Mini.

**Result of the draw** (run 2026-09-29, output accepted unmodified):

| instance_id | repo | version | difficulty | FAIL_TO_PASS | PASS_TO_PASS |
| --- | --- | --- | --- | --- | --- |
| django__django-13343 | django | 3.2 | 15 min – 1 hour | 1 | 130 |
| django__django-13809 | django | 4.0 | 15 min – 1 hour | 1 | 245 |
| django__django-14017 | django | 4.0 | 15 min – 1 hour | 2 | 147 |
| sphinx-doc__sphinx-9658 | sphinx | 4.3 | 15 min – 1 hour | 1 | 24 |
| sphinx-doc__sphinx-8621 | sphinx | 3.5 | <15 min fix | 2 | 31 |

Mini's mix: 25 django / 25 sphinx; difficulty 19 "<15 min",
23 "15 min – 1 hour", 7 "1–4 hours", 1 ">4 hours" [MEASURED — script
output, aggregates only]. Candidate pool: 205 django, 19 sphinx.
Seats 3 / 2: the 2.5 / 2.5 tie was broken by dataset order.

The draw skews towards "15 min – 1 hour" and has no "1–4 hours"
task. Accepted: re-drawing until the mix looks right would be
cherry-picking. Committed as `splits/dev_split.json`.

**Change 2 — test-set size is decided after Week 3.** Mini (50 tasks)
is the committed floor. Once cost per task is measured (October
week 3), the test set may be expanded to a seeded random sample of
100–150 Verified tasks across all repositories, excluding the dev
split.

| Option | What it lacks |
| --- | --- |
| Mini only, fixed now | Two repositories; n=50 is likely too small to detect a difference (ADR-0008) |
| Full Verified (500) | ~10x the headline cost [ESTIMATE — budget.md scaled], ~130 GB of images, and would force the dev split outside Verified entirely |
| **Mini as floor; expansion decided on measured cost** | Chosen. The size decision uses a measured number, not an estimate |

Rules for the expansion, fixed now so they cannot be tuned later:
the sample is drawn by a committed seeded script; it is decided
before any agent has run on a test task; the headline reports Mini
separately as well, so the comparable number is never lost. If the
measured cost does not allow the expansion, Mini stands and the
two-repository limit is stated as a limitation.

**Consequence.** All 50 Mini tasks stay untouched until February.
The dev split works for either test-set size.

**Amendment (2026-10-02) — size decision moves to December.** Week 3
measured single-call cost only (results entry #9); the expansion cost
is dominated by calls per task, unique input per call and output,
first measured on the five-agent pipeline in December (`budget.md`).
So the size decision is taken after the first five-agent run, not after
Week 3. **Stated intent (Malay):** a full 150-task run at the end of the
project, if the budget permits; Mini's 50 stay the committed floor and
are always reported separately. To keep the rules above intact, the
150-task sample is **drawn and committed in December** by the seeded
script, before any agent has run on a test task — even though the run
itself comes last. The premium arm stays on Mini's 50 (cost).

---

## ADR-0008: Pre-registered comparison protocol

**Date:** 2026-09-26 · **Status:** accepted — **binding before the
first comparison run**

### Context

Published analyses attribute large swings in SWE-bench scores to
harness and scaffold choices alone, with the same underlying model.
Whichever configuration receives more prompt-tuning attention will
win. In this project that would be the mixed-model team, because it is
the hypothesis being tested. A protocol written after seeing results
is not a protocol.

### Decision

Fixed before any comparison is run:

1. **Identical role prompts across all configurations.** Only the
   model bound to each role varies.
2. **Identical iteration caps, context limits, retry logic and spend
   ceilings.**
3. **Prompt files are hashed, and the hash is recorded in every run
   record.** The benchmark runner refuses to compare two runs whose
   prompt hashes differ.
4. **Paired comparison.** Every configuration runs the same tasks;
   significance is tested with McNemar on the discordant pairs, not by
   comparing two independent proportions.
5. **Three seeds minimum** on the headline comparison, with the spread
   reported.
6. **Cost per task is the primary outcome**, resolve rate secondary.
   Cost is continuous and has far tighter intervals at n=50 than a
   binary outcome, and cost-efficiency is the actual claim.
7. **Every number in `results.md` carries a bootstrap confidence
   interval.**
8. **Any prompt change made after seeing results invalidates the run.**
   It is re-run from scratch, and the invalidated run stays in
   `results.md` marked as such.

### Consequences

- The comparison is auditable from the repository rather than on
  trust.
- Re-runs after a prompt change cost real money, which is the point:
  it makes post-hoc tuning expensive rather than tempting.
- The likely outcome is that no significant difference is detectable
  at n=50. That is reported as a finding, with the interval and the
  sample size that would be required.

### Reversal condition

None. Changing this after results exist defeats its entire purpose.

### Clarification — "seeds" means repeats (2026-09-29)

"Seeds" means independent repeats. DeepSeek has no seed parameter
[PRIMARY — API reference], and outputs differ between identical calls
at temperature 0 (results entry #5). The record's `seed` field holds
the repeat number.

### Clarification — repeats are separate days (2026-10-02)

Repeats of a task are **separate dispatches on different days**, never
parallel or back-to-back, and results report the agreement between
repeats. Reason: within one 25-minute session django-14017 produced an
identical 152-token answer four times (unresolved), while the same input
resolved on 2026-09-30 (results entries #8–#9). Repeats close in time
are not independent, so they would understate the spread. This adds a
constraint before any comparison has run; it loosens nothing.

---

## ADR-0009: Per-job spend ceiling in code

**Date:** 2026-09-26 · **Status:** accepted

### Context

A coder–reviewer loop with a faulty termination condition can run all
night on an expensive model. AWS Budgets and provider console caps
alert after the fact and stop nothing.

### Decision

Every model call passes through a token accountant that enforces, per
job: maximum input tokens, maximum output tokens, maximum model calls,
maximum wall-clock, maximum review rounds. On breach it aborts and
writes a partial transcript rather than retrying. It refuses to start
a job whose projected cost exceeds the cap.

Built in Week 2 of October, before the first unattended run.

### Consequences

- Roughly one day of work that prevents an expensive morning.
- The same accountant is the instrument that measures cost per task,
  so it is not overhead — it is the measuring device.
- Provider console caps and an AWS Budgets alarm remain as backstops.

### Reversal condition

None.

---

## ADR-0010: Pin the SWE-bench harness; read reports by search

**Date:** 2026-09-26 · **Status:** accepted

### Context

The Week 0 spike (results entry #0) ran the official SWE-bench harness
on GitHub Actions. Two things surfaced that the plan had assumed away:

1. **The harness changed shape in 5.x.** `swebench` 5.0.2 requires
   `image`, `eval_script` and `log_parser` columns on every task
   [PRIMARY — swebench 5.0.2 source, `harness/utils.py`].
   `SWE-bench/SWE-bench_Verified` has them; the Verified Mini dataset
   (`MariusHobbhahn/swe-bench-verified-mini`) does not [PRIMARY —
   Hugging Face dataset viewer]. Passing Mini as `--dataset_name`
   cannot work.
2. **Report paths differ between versions.** The release on PyPI
   (5.0.2) writes per-task reports to
   `logs/run_evaluation/RUN_ID/MODEL/TASK_ID/report.json`; the source
   on GitHub `main` writes to `logs/evaluation/` [MEASURED — run
   36217970815; PRIMARY — GitHub source]. Spike run 1 was marked
   failed because the summary step read a hardcoded path from `main`
   while the job ran 5.0.2. The harness had in fact resolved the task.

The scoreboard is the instrument every later result depends on. If
its behaviour can shift under us, every number after that shift is
suspect.

### Options considered

| Option | What it lacks |
| --- | --- |
| Unpinned `pip install swebench` | A new release can silently change dataset requirements, report paths or grading. Results become irreproducible |
| Pin, and hardcode the report path for that version | Works until the pin moves; the failure mode is a false "unresolved", which looks like an agent failure rather than a tooling bug |
| Fork or vendor the harness | Loses the "official harness" credibility and becomes code to maintain |
| **Pin, and locate reports by search with an exactly-one check** | Chosen |

### Decision

- **Pin `swebench==5.0.2`** everywhere the harness is installed:
  local WSL, GitHub Actions, and any cloud session. The version is
  recorded in every run record.
- **Dataset:** always `SWE-bench/SWE-bench_Verified`. Verified Mini
  is used only as a **list of task IDs**, passed through
  `--instance_ids`. The 5-task dev split (ADR-0007) is likewise a
  list of IDs.
- **Reading results:** find the task's `report.json` by searching
  under `logs/` for the task ID and the run ID. Require **exactly
  one** match; zero or several fails the job loudly. Read `resolved`
  from that file, never from a summary file or the harness's exit
  code.
- **Checking code against docs:** when reading harness source to
  understand behaviour, read the source of the *installed* version
  (the tagged release or the installed package), not `main`.

### Consequences

- Scores are reproducible: the same patch and task give the same
  verdict regardless of when the job runs.
- A green harness step no longer counts as success on its own. Only
  `resolved: true` in the task's own report does. This caught a
  real error on the first run.
- Harness upgrades become a deliberate, recorded act, not an
  accident.
- Cost: pinned software drifts out of date; bug fixes upstream are
  missed until the pin is moved.

### Reversal condition

Move the pin only when a newer release fixes something that matters
here. When moving it: re-read that release's source for the report
path and required columns, re-run the gold and empty-patch checks on
the 5 dev tasks, and record the change in `results.md`. Never change
the harness version between the configurations of a comparison run
(ADR-0008).

### Addendum — local harness environment (2026-09-29)

Recorded after the local smoke tests (results entry #1). Same
decision, extended from CI to the development machine.

**1. Python environment: uv-managed Python 3.11 venv at
`~/.venvs/blindspots`, inside WSL.**

| Option | What it lacks |
| --- | --- |
| System Python (3.12 on Ubuntu 24.04) | Works — swebench 5.0.2 needs ≥3.10 [PRIMARY — PyPI metadata] — but differs from CI's 3.11, adding a variable when local and CI disagree |
| conda | Heavy; a second package ecosystem for no gain here |
| venv on E: (`/mnt/e/...`) | Cross-OS file access from WSL is slow for many small files [PRIMARY — Microsoft WSL docs]; also breaks the "source and documents only" rule for `E:\Blindspots` |
| **uv, Python 3.11, venv in WSL home** | Chosen — matches CI's interpreter; one tool installs both Python and packages |

Verified: Python 3.11.16, swebench 5.0.2, Docker SDK `ping()` →
True [MEASURED, 2026-09-26].

**2. Local runs set `HF_DATASETS_OFFLINE=1` once the dataset is
cached.** The Hugging Face Hub online check cost ~45 s per invocation;
offline mode cut a warm run from 77 s to 33 s with the evaluation
step unchanged [MEASURED — results entry #1]. Side benefit: the
dataset cannot change underneath a run. Cached revision:
`78f471bf655a3137b2e8a75af1501690ec009ec3`.
First download of any new dataset (e.g. Verified Mini's ID list)
must run without the flag.

**3. Hugging Face authentication: read-only token.** Stored in WSL
via `hf auth login` (`~/.cache/huggingface/token`), outside the
repository; not added as a git credential. CI will read the same
token from the `HF_TOKEN` repository secret (step 6). Read-only
scope because the harness only downloads; a leaked read token
cannot modify anything. Never written to any file under
`E:\Blindspots` — the repository is public. Verified: `hf auth
whoami` → `Malay01` [MEASURED, 2026-09-29].

**Open:** pin the dataset revision explicitly in CI as well, so
local and published runs provably score against the same task
definitions. Decide in step 6.

**Reversal:** move off Python 3.11 only together with CI. Drop
offline mode if a dataset update is deliberately adopted — and
record the new revision here.

---

## ADR-0011: Run record format and runner design

**Date:** 2026-09-29 · **Status:** accepted

### Context

Cost per fix, the headline metric, can only be computed from
per-attempt records of tokens, cost and outcome. January's reviewer
benchmark needs every failed patch as labelled data. Both are free if
captured from the first run and expensive to reconstruct later
(results.md, "Run records"). Week 1 steps 3–4 also showed the harness
has behaviour worth recording explicitly: empty patches are never
evaluated, and a "not resolved" can come from the bug, a broken
environment, or a patch that did not apply.

### Decision

1. **One JSON file per task attempt**, at `RUN_ID/INSTANCE_ID.json`.
2. **Schema is a Pydantic v2 model** (`blindspots/record.py`),
   `schema_version` 1. Extra fields forbidden; records frozen.
3. **The harness runs as a separate process** through its documented
   command line; verdicts come from each task's `report.json`, found
   by search (ADR-0010).
4. **Exactly one outcome per record**, matching results.md:
   resolved, unresolved, patch_apply_failed, empty_patch,
   harness_error, spend_ceiling, wall_clock_limit.
5. **Consistency enforced at write and read:** config hash matches
   config; `resolved` only if every FAIL_TO_PASS and PASS_TO_PASS
   test passed; test results present whenever tests ran.
6. **Config and prompt hashes** are SHA-256 of canonical JSON (sorted
   keys) and of prompt files, so comparability (ADR-0008) is checked
   by code.
7. **Environment recorded per record:** Blindspots commit, swebench
   version, dataset name and revision, Python and Docker versions,
   local or CI.
8. **Records live outside the repository** (`~/bs-work/records/`
   locally); in CI, uploaded as workflow artifacts. Artifacts on public
   repositories expire after at most 90 days [PRIMARY — GitHub Actions
   docs], so published evidence needs a permanent home — decided in
   step 6.
9. **Writes are atomic and never overwrite.** A rerun gets a new run ID.
10. **Code is a package** (`blindspots/`, `pyproject.toml`) with tests
    in `tests/`. `swebench==5.0.2` is pinned in `pyproject.toml`.

### Options considered

| Choice | Rejected alternatives and what they lack |
| --- | --- |
| One file per attempt | Per-batch file: a crash loses finished tasks. One JSONL file: one bad write damages every record. SQLite: binary, no readable diffs, write conflicts |
| Pydantic | Plain dict: no checking. Dataclasses: types not enforced. Hand-written JSON Schema: a second definition to keep in sync |
| Harness as a process | Importing internals: signatures can change even within a pinned major version |
| Package with tests | Loose scripts: cannot be imported by the agent code |

### Consequences

- Every results.md figure becomes recomputable from files.
- Failed patches accumulate as reviewer-benchmark data from run one.
- A disagreement between the harness verdict and results.md's
  definition of "resolved" stops the write rather than producing a
  wrong number.
- Cost: one dependency (Pydantic); records are larger than a summary
  table, especially once transcripts are included.

### Reversal condition

Change the format only by incrementing `schema_version` and keeping a
reader for older versions. Never edit existing records.

### Amendment — schema 3 (2026-10-04)

`Timing.agent_s`: wall-clock seconds of the agent's attempt for one
task — every model call plus the agent's own processing — measured
with `time.monotonic`, excluding workspace preparation. Required
(not null, ≥ 0) when `patch_source` starts with `agent:`, including
attempts that end in `spend_ceiling`, `wall_clock_limit`,
`provider_error` or `empty_patch`; null for gold, empty and no-op.
Reason: scored records kept only the harness's timing, so agent time
could only be rebuilt from transcript `latency_s` (results entry #9
addendum). Checked for schema 3 only; schema 1 and 2 records load
unchanged and are never edited.

---

## ADR-0012: CI benchmark design

**Date:** 2026-09-29 · **Status:** accepted

### Context

Local runs are the development bench; published results need a clean
machine, public logs and a link anyone can check. The Week 0 spike
showed a free runner holds one task with large margin (results
entry #0). Step 7 built the runner and record format; CI must use the
same code path so local and CI records are identical in shape.

### Decision

1. **`benchmark.yml`, manual trigger only** (`workflow_dispatch`,
   inputs: source, run ID). Never on push or schedule — from Week 2
   a run spends money.
2. **One job per task** (matrix from `splits/dev_split.json`,
   `fail-fast: false`), each running `python -m blindspots.run
   --instances TASK`. The runner refuses tasks outside the split.
3. **Dataset downloaded at a pinned revision**
   (`78f471bf655a3137b2e8a75af1501690ec009ec3`) with the `HF_TOKEN`
   secret, then used offline — same revision as local runs.
4. **`pip freeze` saved with every job**, as a record of exact
   package versions.
5. **Evidence uploaded as workflow artifacts** (record, harness logs,
   console output, package list), 90-day retention, uploaded even on
   failure.
6. **A summary job** re-validates every record and publishes the
   table on the run page (`python -m blindspots.summarise`).
7. **`tests.yml`: unit tests on every push and pull request.** No
   Docker, no secrets, $0.
8. **Workflow inputs pass through environment variables**, never
   interpolated into scripts (GitHub script-injection guidance).

### Options considered

| Choice | Rejected alternatives and what they lack |
| --- | --- |
| Manual trigger | On push: image pulls on every doc edit; spending must never start automatically. Scheduled: runs nobody asked for |
| Job per task | One job for all tasks: five images on one runner's disk (14 GB documented floor), serial, one crash loses all |
| Pinned dataset revision | "Latest": local and CI can silently score different task definitions |
| `pip freeze` per run | Nothing: CI/local differences untraceable. Full lock file: right eventually, premature now |
| Shared `summarise` module | Summary logic in YAML: duplicated between CI and local, and drifts |

### Consequences

- Every CI result has a public, permanent-for-90-days link with logs.
- CI cost: $0 on public repositories [PRIMARY — GitHub docs; confirmed
  by the spike].
- Artifacts expire after 90 days. **Open, with a trigger:** before the
  first run cited as a published result, decide the permanent home
  (likely GitHub Release attachments; rejected: committing records to
  the repo, a records branch, AWS S3).
- `spike.yml` is kept unchanged as the evidence for results entry #0.
- **Unverified assumption:** the pinned revision equals the local
  cache folder name. The first CI run confirms or refutes it (a wrong
  revision fails the download loudly).

### Reversal condition

Move to a lock file at the first unexplained difference between local
and CI results. Move to a self-hosted runner only if task images
outgrow the free runner's disk.

### Amendment — permanent home for records (2026-10-04)

The open item under Consequences is decided in **ADR-0017**: every run
is archived as `RUN_ID.tar.gz` in the `run-records` release, and the
run-ID check also refuses IDs found there. Run IDs are now letters,
digits and hyphens only. Decision 5 (artifacts, 90 days) is unchanged;
artifacts stay as a convenience copy.

---

## ADR-0013: Provider adapters over raw HTTP; two costs per call

**Date:** 2026-09-29 · **Status:** accepted

### Context

Week 2 needs the first provider adapter (DeepSeek). Reading the API
reference surfaced three facts the plan had not accounted for:

1. **DeepSeek charges double in peak hours:** 01:00–04:00 and
   06:00–10:00 UTC, Monday to Friday [PRIMARY — api-docs.deepseek.com,
   pricing]. The same tokens can cost twice as much depending on when
   a run starts.
2. **There is no `seed` parameter** [PRIMARY — API reference].
3. **Thinking mode is on by default**, its tokens bill as output, and
   the default `max_tokens` changes with it (8K off, 64K on)
   [PRIMARY — API reference].

### Options considered

| Choice | Rejected alternatives and what they lack |
| --- | --- |
| **`httpx`, calling the API directly** | `openai` SDK: retries failed calls twice by default, against ADR-0009, and converts responses into objects so the raw fields aren't directly visible. LiteLLM: heavy, and applies its own price tables, while cost is the one number that must come from our code |
| **Two costs per call** | Billed cost only: a configuration run at 6pm looks twice as expensive as the same one at 10pm. Scheduling every comparison off-peak: works until one run starts late, then silently biases the result |
| **Every setting sent explicitly** | Relying on server defaults: a default change at DeepSeek would change cost and behaviour without changing the config hash |

### Decision

1. Adapters use `httpx` directly. Tests replace the network with
   `httpx.MockTransport`, so they cost $0.
2. No server defaults: thinking mode, `max_tokens` and temperature are
   always sent and are part of the config hash.
3. Every call records cache-hit, cache-miss, output and reasoning
   tokens, plus `billed_usd` (the rate in force when the call
   started), `reference_usd` (off-peak list price) and the price-table
   version. **ADR-0008 comparisons use `reference_usd`; the budget
   tracks `billed_usd`.**
4. The adapter refuses a response whose usage fields are missing, or
   whose cache hit + miss doesn't equal input tokens. A missing cache
   field is never read as zero hits.
5. Prices are copied by hand from the vendor page and dated in
   `blindspots/pricing.py`. A price change adds a new table version;
   old versions are never edited.

### Consequences

- Comparisons don't depend on time of day.
- The price table is maintained by hand.
- Chinese public holidays aren't modelled, so billed cost is slightly
  overstated on those days (the safe direction).
- Local runs that call DeepSeek need the VPN on (results entry #5).
  CI is expected to be unaffected; the first CI run with model calls
  will confirm this.

### Reversal condition

Switch to vendor SDKs if the November adapters end up duplicating a
lot of code. Change the reference price only through a new table
version.

---

## ADR-0014: The spend ceiling as built

**Date:** 2026-09-29 · **Status:** accepted

### Context

ADR-0009 requires per-job limits, enforced in code, before any
unattended run. Building them raised three questions ADR-0009 doesn't
answer: which dollars the cap counts, how the clock is enforced during a
call, and how to account for a call that gets cut off.

### Options considered

| Choice | Rejected alternatives and what they lack |
| --- | --- |
| **Cap counts peak-price dollars** | Billed dollars: the same job passes off-peak and breaches at peak, which breaks ADR-0008's identical ceilings. Reference (off-peak) dollars: real spending at peak can reach 2x the cap |
| **Accountant sits in front of the adapter** | Limits inside each adapter: every November adapter would reimplement them |
| **Timeout set to the remaining time, plus an after-call check** | Timeout alone: the network library applies it per stage, so a job can still overrun (measured: 2.4 ms, results entry #6). A background thread killing the call: not safe in Python |
| **Estimate by prompt bytes** | Estimating by characters: can under-count. An exact tokenizer: an extra dependency, not yet confirmed to match DeepSeek's |

### Decision

1. Five limits per job: calls, input tokens, output tokens, wall-clock,
   and peak-price dollars. They're stored in the config, so they're part
   of the config hash.
2. Week 2 values: 5 calls, 200,000 input tokens, 16,000 output tokens,
   600 s, $0.10.
3. Before each call, the job's totals plus the call's worst case are
   checked. If any limit would be passed, the call is refused and
   nothing is sent.
4. After each call, the real totals are checked again.
5. A call cut off by the clock is booked at its worst case.
6. Any breach ends the job: outcome `spend_ceiling` or
   `wall_clock_limit`, with the partial transcript. Nothing is retried.
7. Record schema 2 adds the `breach` block, `reference_usd`,
   `ceiling_usd`, cache-miss and reasoning tokens, and the
   `provider_error` outcome. Version 1 records still load.

### Consequences

- Real spending can't exceed the cap, except through a call cut off
  partway, which is booked at its worst case.
- The byte estimate is about 3–4x loose, so large prompts may be
  refused early. That's deliberate: it's the safe direction, and step 4
  will measure how often it happens.
- The cap is stricter off-peak than it needs to be.

**Open:** whether DeepSeek bills a call the client abandons
[UNVERIFIED].

### Reversal condition

Replace the byte estimate with an exact tokenizer if good calls are
regularly refused. Revisit the limit values when the multi-agent
pipeline arrives in December, using the costs measured in Week 3.

---

## ADR-0015: The simple agent (Week 2)

**Date:** 2026-09-30 · **Status:** accepted

### Context

Week 2 step 3 needed a first agent: one model call, no roles, no loop.
Four choices shape every later agent and, once comparison runs begin,
are bound by ADR-0008: where the agent reads the code from, what the
model writes back, how the prompt is laid out, and how files are
chosen.

### Options considered

| Choice | Rejected alternatives and what they lack |
| --- | --- |
| **Code from the task image's `/testbed`**, checked by file tree | `git clone` at `base_commit`: ~300 MB per Django task over a flaky connection, and a second copy that could differ from what the harness tests. Checking commit IDs: refuses correct copies, because the images add an empty commit (results entry #7) |
| **Search/replace blocks; our code writes the diff** | Model writes a unified diff: wrong line numbers and malformed hunks fail to apply, so scores would partly measure diff formatting. Fuzzy matching of blocks: a guess about what the model meant, which we would then score |
| **Prompt: system, repo context, issue, then role instruction last** | Role instruction first or in the system prompt: in December each role would change the start of the prompt, so no role could reuse another's cached prefix (ADR-0005) |
| **Files chosen by keyword matching on the issue text** | Whole repository: millions of tokens. Gold-patch files ("oracle" retrieval): leaks the answer. Embedding search: another model and another cost, before a baseline exists |

### Decision

1. The agent reads the repository copied out of the task's Docker image
   (`/testbed`), kept per task under `~/bs-work/repos/`. Its files must
   be identical to `base_commit` (equal tree hashes), and a reused copy
   must be unchanged since it was copied.
2. The model replies with search/replace blocks. Each SEARCH text must
   match exactly once. Our code builds the diff with `difflib` and
   checks it with `git apply --check`. A block that does not match is
   `patch_apply_failed`; no blocks is `empty_patch`.
3. Prompt parts live in `prompts/simple/` and are hashed into every
   record. Order: system, repository context, issue, instruction.
   Nothing that varies between runs appears in any part.
4. Files are chosen from the issue text only: explicit paths, dotted
   module names, file names, and code-looking identifiers found by
   their definitions. Test files are down-weighted. Budgets: 120 KB of
   file content, 20 KB of directory listing, 8 files.
5. After each run, the record stores whether the gold patch's files
   were shown (`diagnostics.localisation`). It is never shown to the
   model.
6. Week 2 settings: `deepseek-flash`, thinking off, temperature 0,
   `max_tokens` 4,096, ADR-0014 limits.

### Consequences

- The agent reads exactly the code the harness tests, with no network.
- A failed patch always means the model's edit was wrong, never that
  our diff was malformed.
- Identical prompts across repeats of a task make nearly all input
  cacheable (99.5% measured, results entry #7).
- Keyword selection can rank a re-export module above the defining
  file (entry #7). Accepted as a baseline for the December localiser.
- Needs Docker Desktop running, and the task image local, before the
  agent can start.

### Reversal condition

Replace keyword selection when the localiser role exists and beats it
on localisation hit rate. Allow a fuzzier match only if exact matching
turns out to cause most `patch_apply_failed` outcomes, and then record
the change as a new prompt/config version, never mid-comparison.

### Amendment (2026-09-30)

**Workspace rule, revised twice after contact with real images.**
`base_commit` must be an ancestor of HEAD. Files whose **contents**
differ from `base_commit` (compared by blob hash) must be top-level
packaging or test-configuration files (`setup.py`, `setup.cfg`,
`tox.ini`, `pyproject.toml`, `pytest.ini`, `requirements*.txt`).
Permission-only changes are ignored. Anything else refuses the task,
and the error names up to 10 files. Changed files are recorded as
`image_environment_changes`. Reason: the harness tests the image's
tree, so the agent must see exactly that, and must never see code that
differs from the task's (results entry #8).

**Harness outcome mapping.** "Not applied" in report.json is decided by
`run_instance.log`: `>>>>> Patch Apply Failed` → `patch_apply_failed`;
`>>>>> Applied Patch` → `tests_errored`; neither → `harness_error`.

**Keyword selection: known weakness, kept as the baseline.** It can
choose no files, or an irrelevant one, when the issue names no paths or
classes (results entry #8). Kept unchanged so the December localiser
has a fixed baseline to beat; flagging weak selections is left to that
work.

---

## ADR-0016: Verifying cache hits, and a cache-busted condition (Week 3)

**Date:** 2026-10-02 · **Status:** accepted

### Context

October-plan Week 3 needs cache hits verified from the API response
(item 2) and a measurement with "caching disabled" (item 4). DeepSeek
caching is automatic and best effort, with no switch to turn it off
[PRIMARY — context-caching guide]. Cache entries also outlive a single
session: a dispatch planned as "cold" was already 99% cached from runs
two days earlier (results entry #9).

### Options considered

| Option | What it lacks |
| --- | --- |
| Trust `prompt_cache_hit_tokens` alone | One unchecked number decides the cost |
| Wait for the cache to expire between conditions | Expiry has no stated time; observed lifetime is at least ~43 hours. Not controllable |
| Change model or settings between conditions | Changes more than caching; confounds the comparison |
| **Random marker first in each prompt, plus a second cache field as a cross-check** | Adds ~30 input tokens per busted call; the prompt text differs slightly from the cached condition |

### Decision

1. **Cross-check.** When `usage.prompt_tokens_details.cached_tokens` is
   present it must equal `prompt_cache_hit_tokens`, or the adapter
   refuses the response (`ProviderError`). Its absence is accepted:
   the field is not guaranteed.
2. **Cache busting.** `--cache-bust` (CLI) / `cache_bust` (workflow
   input) puts 128 random bits, then a one-line "ignore this" note, at
   the very start of the system message. New per attempt, not per run,
   so attempts in one run cannot warm each other.
3. **Verified, not assumed.** Each busted attempt records
   `cache_bust_verified` — true only if zero cached tokens were
   reported. A false value excludes the attempt from busted figures.
4. **Hashes.** Prompt-file hashes are unchanged (ADR-0008). The
   `cache_bust` key enters the config only when on, so the default
   config keeps its Week 2 hash.
5. **Classification.** Attempts are classed cold, warm or busted by
   their measured cache-hit share (`scripts/week3_report.py`), never
   by dispatch order.

### Consequences

- Entry #9: 5/5 busted attempts reported 0 cached tokens; 20/20 raw
  responses passed the cross-check.
- The marker adds about 0.1% to a 27K-token prompt. One task
  (django-14017) gave an identical 152-token answer with and without
  it [MEASURED, n=1 busted].
- There is still no measured "first-ever" cold attempt; the busted
  condition stands in for it.

### Reversal condition

DeepSeek documents a way to disable caching; or any busted attempt
reports a cache hit (then put the marker inside every message, or
move to the documented switch).

---

## ADR-0017: Permanent home for CI run records — GitHub Release assets

**Date:** 2026-10-04 · **Status:** accepted

### Context

CI records live only as workflow artifacts, which expire after at most
90 days on a public repository [PRIMARY — GitHub Actions docs]
(ADR-0012 left this open). Two things are lost at expiry: the records
themselves, the evidence for every CI figure in results.md; and the
check that refuses a reused run ID, which looks up artifacts and so
silently stops protecting IDs older than 90 days. The mini-swe-agent
baseline (Week 4 item 3) must not start before this is fixed.

### Decision

1. **One long-lived release, tag `run-records`, one asset per run:
   `RUN_ID.tar.gz`.** It holds the run's artifacts exactly as uploaded,
   one folder per task (record, harness logs, console output,
   predictions, `pip freeze`).
2. **`scripts/archive_ci_run.sh GITHUB_RUN RUN_ID` builds and uploads
   it**, for new runs and old ones alike. It downloads the run's
   artifacts, refuses names that are not exactly `RUN_ID-TASK` for a
   dev-split task, re-validates every record, packs, creates the release
   if missing, uploads, and checks the asset kept its exact name.
3. **The benchmark's summary job runs that script** after its own
   re-validation succeeds. It is the only job with `contents: write`;
   the workflow default stays `contents: read`.
4. **Never overwritten.** No `--clobber`; GitHub refuses a second asset
   with the same name [PRIMARY — REST docs, release assets], so a repeat
   fails the job (ADR-0011).
5. **The run-ID check also refuses an ID whose `RUN_ID.tar.gz` exists**,
   besides the existing artifact check. Run IDs are restricted to
   letters, digits and hyphens, because GitHub renames asset files with
   special characters [PRIMARY — REST docs, release assets], and a
   renamed archive would escape an exact-name check.
6. The 90-day artifacts stay as they are, for convenience.

### Options considered

| Choice | Rejected alternatives and what they lack |
| --- | --- |
| Release assets | **Commit records to the repo:** this folder holds source and documents only; transcripts make every run a permanent addition to git history. **Hugging Face dataset:** built for data and permanent, but a second service and a write token in CI for a few MB a month; kept as the fallback. **Artifacts only:** expire after 90 days, taking the evidence and the run-ID protection with them |
| Tarball per run | One asset per record: up to five uploads per run and five times the assets against the per-release cap |
| Archive after re-validation | Archive everything: a record that fails validation would be kept for good as if it were evidence |
| Same script for CI and backfill | Archive logic in YAML: two builders that can drift, so old and new archives would differ |

### Consequences

- Records outlive the 90 days, and so does protection of run IDs.
- Limits: each file under 2 GiB; up to 1,000 assets per release; no
  limit on total release size or bandwidth [PRIMARY — GitHub docs,
  "About releases"]. One 5-task agent run packs to 256 KB [MEASURED,
  ci-w3-cache-1, dry run], so the per-file limit is far away; the
  asset cap means 1,000 runs.
- Retention: the docs state no expiry for release assets; that they are
  kept until deleted is [UNVERIFIED].
- **Not tamper-proof.** Anyone with write access can delete an asset or
  the release, which would also free its run ID. Accepted for a
  one-maintainer repository [JUDGEMENT].
- A run whose records fail re-validation is not archived; its ID is
  protected only by artifacts, for 90 days. That run is broken anyway
  and is investigated, not cited.
- The summary job downloads its own run's artifacts with `gh run
  download` while the run is still in progress [UNVERIFIED — confirmed
  or refuted by the first archived run].
- Backfill is manual: every earlier CI run must be archived with the
  script before its artifacts expire, 90 days after upload. The first
  (`ci-gold-1`, 2026-09-29) expires around 2026-12-28 [ESTIMATE].
  Before the run-ID check existed (commit d39fc79, 2026-09-30),
  `ci-gold-1` was used by three runs; only run 36506913529, the one
  results entry #4 cites, can be archived under that name.

### Reversal condition

Move to a Hugging Face dataset if a run's archive nears 2 GiB, the
release nears 1,000 assets, or GitHub documents an expiry for release
assets.

---

## Environment — development machine

**Recorded 2026-09-26.** Reproducibility baseline for every local
measurement in `results.md`.

| Component | Value |
| --- | --- |
| Host OS | Windows, WSL2 + Docker Desktop |
| Logical processors | 16 |
| Host RAM | 32 GB |
| Free disk, E: | ~429 GB |
| Project root | `E:\Blindspots` |

**WSL2 allocation.** WSL2, not Windows, is what bounds Docker. Raised
from the default via `C:\Users\malay\.wslconfig`:

```ini
[wsl2]
memory=20GB
processors=16
swap=8GB
```

**Verified after restart:**

| | Default | After | SWE-bench recommends |
| --- | --- | --- | --- |
| Processors | 16 | 16 | 8 |
| RAM | 15 GiB | **19 GiB** | 16 GB |
| Swap | 4 GiB | **8 GiB** | — |

Every requirement is now cleared with margin, so hardware does not
constrain local benchmark runs.

**Parallelism.** RAM, not cores, bounds concurrency: the harness
suggests fewer than `min(0.75 * cpu_count, 24)` workers, which would
be 12 here, but at 1–2 GB per container 19 GiB supports about 8–10.
Start at 8 workers and watch memory.

**Docker image store location — deferred 2026-09-26.** Docker Desktop
keeps its images in a WSL virtual disk under `%LOCALAPPDATA%\Docker\wsl`
on C:, not on E: where the free space is. (`docker info` reports
`/var/lib/docker`, which is the path *inside* the Linux VM and says
nothing about the Windows-side location.) On the WSL2 backend the
Docker Desktop "Disk image location" setting is absent or inert on
some versions, so relocating means moving the WSL data by hand.

**Measured 2026-09-26: C: has 43.7 GB free of 415 GB.** Below the
100 GB threshold, so relocation is required before any large image
pull. The 50-task sample spans roughly 12 repositories and needs an
estimated 20–30 GB of environment images — that would leave C: at
roughly 15 GB free, low enough to destabilise Windows Update and the
page file.

**Resolved 2026-09-26 — the Docker Desktop setting worked.** Settings
→ Resources → Advanced → Disk image location accepted an E: path and
moved the data. C: free space rose from 43.7 GB to 48.2 GB, and no
large Docker `.vhdx` remains under `%LOCALAPPDATA%`. The junction
workaround below was unnecessary and is retained only as a fallback
for machines where the setting is inert.

**Follow-up — the first destination was wrong.** The disk image was
pointed at `E:\Blindspots\DockerDesktopWSL`, i.e. *inside* the git
repository and inside the folder connected to Cowork sessions. At
15 GB of virtual disk, a `git add .` would have tried to stage it, and
GitHub rejects files above 100 MB. Moved to `E:\DockerDesktopWSL`, a
sibling of the repo rather than a child. `DockerDesktopWSL/` and
`*.vhdx` are also in `.gitignore` as a second line of defence.

**Rule going forward:** no data store, cache or virtual disk lives
inside `E:\Blindspots`. That folder holds source and documents only.

**Fallback if the setting is ever inert** (a directory junction —
Docker keeps writing to its usual path, Windows redirects to E:):

```bat
:: Quit Docker Desktop from the system tray first
wsl --shutdown
mkdir E:\Docker
move "%LOCALAPPDATA%\Docker\wsl" "E:\Docker\wsl"
mklink /J "%LOCALAPPDATA%\Docker\wsl" "E:\Docker\wsl"
```

`mklink /J` creates a junction, which needs no administrator rights
and works across drives. Verify with `dir "%LOCALAPPDATA%\Docker"` —
the entry should read `<JUNCTION> wsl [E:\Docker\wsl]`. Reversible:
delete the junction and move the folder back.

**Secondary check.** The Ubuntu WSL distro also lives on C:
(`%LOCALAPPDATA%\Packages\CanonicalGroupLimited*\LocalState\ext4.vhdx`)
and holds cloned repositories and the harness install. Smaller than
the image store, but worth watching once C: is this tight.

This does not block Week 0: the GitHub Actions spike runs Docker on
GitHub's runners, not locally. Required before Week 1.
