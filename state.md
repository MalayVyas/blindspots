# Blindspots — current state

**Last updated 2026-10-02 (Week 3 complete; Week 4 designed).** Read this first in a new session. It says
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

**Week 0 is complete (2026-09-26).** Every hardware and account unknown
has been resolved, and the spike is green. No code has been written
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
| Spike workflow | `.github/workflows/spike.yml` — **green**, run 36218467955 (github.com/MalayVyas/blindspots/actions/runs/36218467955) |
| Git auth in WSL | `gh auth login` + `gh auth setup-git` working; pushes from WSL succeed |

### Open

- ~~Record the spike~~ **done** — `results.md` entry #0, ADR-0010
  (pin `swebench==5.0.2`, locate reports by search).
- **Week 1 step 1 done (2026-09-29).** Harness 5.0.2 in a uv
  Python 3.11 venv in WSL2, Docker confirmed, smoke test resolved
  locally (results entry #1, ADR-0010 addendum).
- **Week 1 step 2 done (2026-09-29).** Dev split drawn from Verified
  outside Mini (ADR-0007 amendment): 3 django + 2 sphinx, committed
  in `splits/dev_split.json`. Test-set size: now decided after the
  first five-agent run (ADR-0007 amendment, 2026-10-02).
- **Week 1 steps 3–5 done (2026-09-29).** Gold 5/5, empty 0/5,
  no-op 0/5 on the dev split (results entry #2). Next: step 7 (run
  record), then step 6 (CI matrix).
- **Week 1 step 7 done (2026-09-29).** Run records (ADR-0011):
  `python -m blindspots.run` writes one validated JSON record per
  task; acceptance test passed (results entry #3). Next: step 6 —
  CI matrix, built on the runner.
- **Week 1 complete (2026-09-29), ahead of its 1 October start.**
  Local and CI scoreboards agree (results entries #2–#4); runner,
  records and CI matrix built (ADR-0011, ADR-0012). Next: Week 2 —
  DeepSeek provider adapter, token accountant and spend ceiling
  (ADR-0009), simplest agent. First model spend.
- **Week 2 step 1 done (2026-09-29).** DeepSeek adapter and two-cost
  pricing (ADR-0013), commit 2a95814. First model spend: 6 calls, about
  $0.0010 (results entry #5). Cache verified from the response fields.
  ADR-0008 clarified: "seeds" means repeats.
  **Local DeepSeek calls need the VPN on** — the home connection drops
  the TLS handshake.
  Next: step 2 — token accountant and spend ceiling (ADR-0009). Settings
  for Week 2 runs: $0.10 per-job cap, `deepseek-flash`, thinking off.
- **Week 2 step 2 done (2026-09-29).** Token accountant and spend
  ceiling (ADR-0014), record schema 2, commit 029f95f. A broken loop
  was stopped by the cost cap and by the clock with real API calls
  (results entry #6). Failure definitions gained "model API failed".
  Model spend to date: about $0.002.
  Next: step 3 — simplest agent. Issue text, a trimmed file tree and
  the relevant files in; a unified diff out. Files chosen by keyword
  matching on the issue text only — never from the gold patch. After
  each run, record whether the gold patch's files were in context
  (localisation hit rate, a diagnostic).
- **Week 2 complete (2026-09-30), ahead of its 8 October start.**
  Step 3: simple agent (ADR-0015), commit b8298b1. Step 4: agent source
  in the runner, commit fb25fab:
  `python -m blindspots.run --run-id NAME --source agent:simple`.
  First scored agent runs on django-13343: one unresolved, one
  **resolved**, identical input (results entry #7). Warm-cache attempt
  about $0.0003; cost per fix on that task $0.00069. Model spend to
  date about $0.007.
  Lessons: outcomes vary run to run, so single-run scores are noise;
  SWE-bench images carry an empty commit on top of `base_commit`;
  commit before a run so records are not `-dirty`.
  Next: Week 3 — caching and October's number. Caching is already
  hitting 99.5% on repeats (entry #7), so Week 3's remaining work is
  the cached-vs-uncached comparison, three repeats per task, and the
  first cost-per-task figure with a spread.

- **Agent in CI (2026-09-30).** `benchmark.yml` runs `agent:simple`
  with a task filter; `DEEPSEEK_API_KEY` repository secret in place (a
  CI-only key); reused run IDs are refused before any runner starts.
  CI reaches DeepSeek without a VPN. First CI resolve: django-14017
  (results entry #8). New outcome `tests_errored`; workspace rule
  compares file contents (ADR-0015 amendment).
  Finding: localisation decided every outcome so far; both resolves
  had the gold file shown, all tasks without it failed.
  Model spend to date about $0.023.
  Next: Week 3, starting with a proper five-task, three-repeat run.
  The main open question: how much localisation limits the resolve rate.

- **Week 3 handoff (2026-10-02) — start here in the next session.**
  All Week 2 work is pushed (latest `e035ab3`). Week 3 design approved
  by Malay on 2026-10-02:
  1. **Adapter cross-check first** (Week 3 item 2, "verify cache
     hits"): if `prompt_tokens_details.cached_tokens` is present it
     must equal top-level `prompt_cache_hit_tokens`, or the response is
     refused. $0, unit tests only.
  2. **Cache-busting option.** DeepSeek has no switch to disable
     caching (automatic, best effort [PRIMARY — context-caching
     guide]). A config option puts a unique marker at the very start
     of the prompt so no earlier prefix can match; it is part of the
     config hash. This is the controlled "caching disabled" condition
     for October-plan Week 3 item 4.
  3. **Report cold and warm separately, never averaged.** CI runs
     matrix jobs in parallel, so repeats of one task launched together
     all start cold. Run repeats as separate dispatches a few minutes
     apart: repeat 1 cold, repeats 2–3 warm.
  4. Runs: 5 dev tasks × 3 repeats, caching on (three dispatches);
     5 tasks × 1, cache busted. Then results entry #9 (cost per task
     with a spread; cold vs warm vs busted; cache hit rate;
     localisation on ~20 more attempts) and rebuild `budget.md` from
     measured numbers.
  Cost: about $0.05–0.10 total [ESTIMATE — cold/busted ~$0.004 and
  warm ~$0.0004 per attempt, from entries #7–#8]. Scope guard: do not
  improve the agent in Week 3; the localisation weakness waits for the
  December localiser (ADR-0015 amendment).
  Still open for Week 4: permanent home for CI records (artifacts
  expire after 90 days, ADR-0012); mini-swe-agent baseline; README
  numbers.

- **Week 3 complete (2026-10-02), ahead of its 15 October start.**
  ADR-0016: adapter cross-check (`cached_tokens` must equal
  `prompt_cache_hit_tokens`) and `--cache-bust` / `cache_bust` workflow
  input; `scripts/week3_report.py` classes attempts by measured cache
  hits. Runs `ci-w3-cache-1/2/3` + `ci-w3-bust-1` at commit 630bc4c
  (results entry #9): cold attempt **$0.0041**, warm **$0.0003**
  (~13x), warm hit rate **99.2%**, busted verified 0 hits on 5/5,
  resolved 1/20. Records downloaded to `runs/w3` (git-ignored).
  Findings: the cache survived ~43 h, so no dispatch is reliably cold;
  with caching on, output is 67% of cost; 13809 picks no files and burns
  4,096 output tokens; localisation still decides every resolve
  (3/12 shown vs 0/16 not, all attempts since entry #7).
  Model spend to date about $0.051.
  **Week 3 closed out the same day:** `budget.md` rebuilt from entry #9
  (central ~$175 for six months, high ~$770; the budget now hinges on
  five-agent quantities first measured in December); 5x signal not
  triggered; ADR-0007 amended (test-set size decided after the first
  five-agent run; **Malay intends a full 150-task run at the end if
  budget permits**, sample drawn and committed in December); ADR-0008
  clarified (repeats on different days); R-07 updated; entry #9
  wall-clock addendum.
  **Next: Week 4.** (a) mini-swe-agent baseline on the 5 dev tasks.
  (b) README with real numbers. (c) Permanent home for CI records
  (artifacts expire after 90 days, ADR-0012). (d) Record schema 3 with
  `agent_s`. (e) Month review of hours.
  **Open:**
  - Cross-provider caching: a mixed team can't share one warm prefix
    across providers — measure it in January (candidate ADR-0008 note).
  - **Can the $100 Azure for Students credit pay for Claude on Microsoft
    Foundry?** Unverified; third-party models are often billed through
    the Marketplace, which sponsored credits may not cover. Check in the
    Azure portal before December. If not: Sonnet in cash (~$64 central),
    a Microsoft model as the premium arm, or `deepseek-v4-pro`.
  - ~~Timeline conflict~~ **Resolved (2026-10-02, Malay):** December
    runs use the dev split only. The 150-task sample is drawn and
    committed in December but not run until the end of the project,
    budget permitting. The 50 Mini tasks stay unseen until February
    (ADR-0007). The "full 50-task run" in December's timeline becomes
    "five-agent pipeline on the dev split, with intervals" (wide, n=5).
  Commit `scripts/week3_report.py` and these doc updates from WSL.

- **Week 4 design (approved by Malay 2026-10-02) — start here.** Order:
  1. **Record schema 3 with `agent_s`.** $0; good cloud-session task
     (credit expires 5 Nov). First, so the baseline's records are born
     in schema 3.
  2. **Permanent home for CI records: GitHub Release assets.** One
     `run-records` release, one tarball per run ID, uploaded by the
     summary job. Needs an ADR. Reverse if assets hit a size limit →
     Hugging Face. Must exist before the baseline runs (20 records =
     2.4 MB [MEASURED]; mini's transcripts will be longer).
  3. **mini-swe-agent baseline.** Version 2.4.6, stock config, prompts
     and loop; a small model class routes its calls through our
     DeepSeek adapter and token accountant, so cache fields and cost
     are measured the same way as our agent's. The ADR states "stock
     mini, our transport". Same $0.10 per-job cap; higher call limit
     for this agent only (~75). Patches scored by our runner. 5 dev
     tasks x 3 repeats on separate days (ADR-0008). About $0.15-0.35
     total [ESTIMATE]. Expect mini to win (it can search the repo, and
     localisation decides every outcome so far); do not improve our
     agent in response.
  4. **README with real numbers**, after the baseline; columns change
     from "/50" to "/5 dev tasks".
  5. **Month review:** about 15-30 h from 26 Sep to 2 Oct [stated].
     Deliberate front-loading by Malay to build a buffer before the
     November exams; Weeks 0-3 finished about 2.5 weeks early.
  Stale: `october-plan.md` Week 4 items 1 and 4 are already done
  (Week 3's 20 attempts; ADR-0001 to ADR-0016).

---

## Spike result (Week 0, done)

Question: can a free GitHub-hosted runner hold and run one SWE-bench
task? **Yes, with large margin.**

Run 36217970815, `django__django-11099`, gold patch [MEASURED, one run]:

| | |
| --- | --- |
| Runner disk total / free at start | 154.9 GB / 92.3 GB |
| Peak disk added by the task | 3.91 GB |
| Image, uncompressed | 2.87 GB |
| Image pull | 35 s |
| Harness evaluation | 27 s |
| Job to summary | 83 s |
| Harness verdict | resolved: 3/3 FAIL_TO_PASS, 19/19 PASS_TO_PASS |

That run went red only because the summary step read the wrong report
path; the harness itself resolved the task. Run 36218467955 with the
fixed step is green.

- GitHub documents 14 GB of SSD [PRIMARY]; the runner actually had 92 GB
  free. Treat 14 GB as the guaranteed floor, not the real figure.
- The `free_disk` fallback run is **not needed** [JUDGEMENT].
- Caveat: one light Django task. Week 1's five dev tasks give the range.

Lessons carried forward:

- **swebench 5.0.2 on PyPI writes to `logs/run_evaluation/RUN_ID/...`**,
  while the GitHub `main` source says `logs/evaluation/`. Read reports
  by searching for the task's `report.json`, never a hardcoded path.
  Check source against the *installed* version, not `main`.
- Harness 5.x needs `image`, `eval_script`, `log_parser` columns:
  use `SWE-bench/SWE-bench_Verified` as the dataset and pass Mini task
  IDs via `--instance_ids` [PRIMARY — swebench 5.0.2 source].
- A green harness step does not mean resolved; the explicit
  resolved-check is what caught the problem.

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

Ship in December; finish by the end of February. Dates confirmed by
Malay 2026-10-02 (R-16): exams 3 and 16 Nov 2026; vacation 17 Nov 2026
to late Feb 2027; Semester 4 from the first week of March to June 2027.
**Realistic capacity: ~10 hours a week throughout** (Malay also works),
lower in exam weeks.

| Period | Deliverable |
| --- | --- |
| **Oct** | Evaluation harness; single agent; spend ceiling; verified caching; **first measured cost per task**; mini-swe-agent baseline; ADRs. Cloud-session credit expires 5 Nov |
| **1–16 Nov** | Exams (3 and 16 Nov), well under 10 hrs/week. Provider adapters only |
| **17–30 Nov** | Vacation. Start the five-agent pipeline (two weeks earlier than first planned) |
| **Dec** | Five-agent pipeline on the dev split, with intervals; README with real numbers; demo video. **Demoable from here.** Draw and commit the 150-task sample; re-budget |
| **Jan** | Offline per-role benchmarks; headline comparison; contamination check |
| **Feb** | Vacation. Write-up, GitHub Pages dashboard; optional 150-task run if the budget allows. **Everything finished by end of February** |
| **Mar–Jun** | Semester 4, under 10 hrs/week. Polish and job applications only; optional AWS slice |

**Capacity check** [ESTIMATE]: about 4 weeks × 10 h left in October, ~10 h
across the exam weeks, and ~15 vacation weeks × 10 h (17 Nov–end Feb)
give roughly **200 hours** to the end of February. R-13's after-cuts guess
was ~220 h [JUDGEMENT, unmeasured]. Tight but workable; Week 4's month
review replaces this with real hours spent. If it slips, cut in this
order: AWS slice, GitHub Pages dashboard, the optional 150-task run —
never the December ship.

The critical change from the original plan: **December is the ship
date, not March.** Everything after it is improvement on something
that already exists and can already be linked in an application.
