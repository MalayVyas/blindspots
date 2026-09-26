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
