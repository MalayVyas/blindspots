# Blindspots — current state

**Last updated 2026-09-26.** Read this first in a new session. It says
where the project stands, what is decided, what is still open, and
which older material is stale.

---

## Read in this order

1. **This file** — current state.
2. **`README.md`** — what the project is, rewritten around the question.
3. **`decisions.md`** — ADR-0001 to ADR-0009. The binding choices.
4. **`claude/october-plan.md`** — week-by-week for October.
5. **`results.md`** — measurement definitions, fixed before any run.

Only if you need the reasoning behind a decision:
**`claude/risks.md`** (21 risks), **`claude/solutions.md`** (the
options considered), **`claude/budget.md`** (costing).

---

## Where the project is

**Week 0 is essentially complete.** Every hardware and account unknown
has been resolved into a measured number. No code has been written
yet beyond the spike workflow. No model has been called yet. No
benchmark has been run yet.

### Done

| | |
| --- | --- |
| Machine measured | 16 cores, 19 GiB RAM in WSL2, 8 GiB swap, ~429 GB free on E: |
| WSL2 memory raised | 15 GiB → 19 GiB via `.wslconfig`, verified after restart |
| Docker image store | Moved off C: to E:, out of the repo folder |
| AWS | Upgraded to the Paid plan (credits were already spent); $5/month Budgets alarm confirmed 2026-09-26 |
| Azure for Students | $100 available, reserved for the premium comparison arm |
| GitHub Student Developer Pack | Claimed |
| DeepSeek API | Account open |
| Claude cloud-session credit | $100, **expires 5 November 2026** |
| Repository | `github.com/MalayVyas/blindspots`, public, remote configured |
| Documents | README rewritten, nine ADRs written, measurement definitions fixed |
| Git | Local `main` committed and pushed; matches `origin/main` (checked 2026-09-26 by reading `.git` refs) |
| Spike workflow | `.github/workflows/spike.yml` written 2026-09-26, linted, **not yet committed or run** |

### Open

- **Git auth inside WSL.** Push from WSL failed (password auth). Fix: `gh auth login` in WSL, then `gh auth setup-git`.
- **The Week 0 spike** — the last item, and the first interesting one.
  See below.

---

## The next piece of work

**Status 2026-09-26:** the workflow is written (`.github/workflows/spike.yml`).
Commit it from the terminal, push, then Actions tab → spike → Run
workflow. Run it twice: once with `free_disk` off (the baseline
answer) and once on (the fallback). The job summary prints the
numbers; paste them into `results.md`.

Findings made while writing it:

- **SWE-bench harness 5.x needs `image`, `eval_script` and
  `log_parser` columns** [PRIMARY — swebench 5.0.2 source,
  `harness/utils.py`]. `SWE-bench/SWE-bench_Verified` has them;
  the Verified Mini dataset (`MariusHobbhahn/swe-bench-verified-mini`)
  does not [PRIMARY — Hugging Face dataset viewer]. So Mini is used as
  a **list of IDs** passed to `--instance_ids` against the Verified
  dataset, not as `--dataset_name`. Pin `swebench==5.0.2`.
- The spike task is `django__django-11099`, chosen from Verified and
  **outside** Mini, so the held-out set is not touched. The workflow
  refuses to run on a Mini ID.
- Its image is 1.07 GB compressed on Docker Hub [PRIMARY — Docker Hub
  API]; uncompressed size is what the spike measures.
- A 50-task matrix runs each task on its own runner, so the per-job
  disk figure is the one that matters, not 50× it [JUDGEMENT].


A GitHub Actions workflow that pulls one SWE-bench environment image,
checks out the task's repo at the base commit, applies the **gold**
patch, and runs the FAIL_TO_PASS and PASS_TO_PASS tests to green.
Roughly three hours.

It exists to answer one question: can a free GitHub runner (4 CPUs,
16 GB RAM, **14 GB disk**) hold and run a single SWE-bench task? If
yes, benchmarking is free forever. If no, fall back in this order:
local-only, self-hosted runner on Malay's machine, paid larger runner.

**Log the disk used and the wall-clock.** Those two numbers decide
whether a 50-job matrix is viable, and they are the entire reason the
spike exists.

Note that the local machine now clears every SWE-bench requirement, so
this is no longer a dependency — Actions is chosen for public CI
evidence and parallelism, not because the hardware forces it.

---

## What is decided and should not be relitigated

From `decisions.md`, ADR-0001 to ADR-0009:

- **No EC2, no EBS.** Local for development, GitHub Actions for
  published runs.
- **Bedrock is off the critical path.** Direct provider APIs for every
  measured run; the Bedrock adapter exists and gets one demonstration
  call.
- **AWS is the always-free serverless tier only**, for the live-mode
  slice, at roughly $0–3 a month — and it is deliberate
  over-engineering, stated as such in ADR-0006.
- **Prompt caching is built in October**, not November, and cache hits
  are verified by reading the API response fields rather than assumed.
- **SWE-bench Verified Mini** (published 50-task subset) is the test
  set; a 5-task dev split is committed by ID; the other 45 are not
  looked at until February.
- **The comparison protocol is pre-registered** (ADR-0008) and binding
  before the first comparison run. Identical prompts across configs,
  prompt hashes in every run record, paired McNemar testing, three
  seeds, cost as the primary outcome, bootstrap intervals on
  everything.
- **A per-job spend ceiling is enforced in code** before the first
  unattended run.

---

## Two principles that shape October

**Build the evaluation before the agent.** The first thing that works
end to end should be "take a patch, run it against a SWE-bench task,
get a verdict" — no agents involved. You cannot improve what you
cannot score.

**Write the full run record from run number one.** Task ID, config
hash, prompt hashes, model, tokens in/out/cached, cost, wall-clock,
the patch, the full transcript, the outcome. As JSON, one file per
run. Beyond making cost-per-fix computable, every failed patch becomes
labelled data for January's reviewer benchmark — gold patches are the
positive class, failures the negative class. Free if captured from the
start, expensive to reconstruct.

---

## Stale material — do not act on it

**Project instructions** were replaced with the current text by
2026-09-26 (they now match `decisions.md`). If they ever disagree,
`decisions.md` wins.

**Earlier cost figures.** A first pass at costing used invented token
assumptions and third-party pricing pages, some of which listed
models that do not exist. `claude/budget.md` was rebuilt from vendor
pricing pages on 2026-09-26 and every claim in the planning documents
now carries a source tag. Anything untagged from before that date is
suspect.

---

## How to work on this project

- **Tag every factual claim** with source quality: `[PRIMARY]` vendor
  or project documentation, `[SECONDARY]` third-party, `[ESTIMATE]`
  arithmetic on stated assumptions, `[JUDGEMENT]` opinion,
  `[UNVERIFIED]` asserted without a source. Never let an estimate
  read as a measurement. This convention exists because an earlier
  session got this wrong and Malay caught it.
- **Every technical choice gets an ADR**: context, options considered,
  decision, consequences, reversal condition.
- Plain language, abbreviations expanded on first use.
- Flag weak ideas, cost risks and scope creep bluntly and early.
- Keep the agent at the centre; say so if the work drifts into pure
  research.
- Remind Malay to update `results.md` and `decisions.md` after a
  substantial session.
- He is on Windows with WSL2 and is **new to WSL and to git**. Avoid
  angle-bracket placeholders in CMD snippets — `<` and `>` are
  redirection operators and will produce a confusing error. Use a
  plain placeholder word instead.

---

## Timeline, as revised

Ship in December; February and March are semester months.

| Month | Deliverable |
| --- | --- |
| **Oct** | Evaluation harness; single agent; spend ceiling; verified caching; **first measured cost per task**; mini-swe-agent baseline; ADRs |
| **Nov** | Exams, under 10 hrs/week. Provider adapters only |
| **Dec** | Five-agent pipeline; first full 50-task run with intervals; README with real numbers; demo video. **Demoable from here** |
| **Jan** | Offline per-role benchmarks; headline comparison; contamination check |
| **Feb–Mar** | Semester, under 10 hrs/week. GitHub Pages dashboard, write-up, optional AWS slice |

The critical change from the original plan: **December is the ship
date, not March.** Everything after it is improvement on something
that already exists and can already be linked in an application.
