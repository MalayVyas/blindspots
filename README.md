# Blindspots

**Given a fixed inference budget, which roles in a multi-agent coding
pipeline justify a more expensive model?**

Blindspots is a role-level benchmark for AI coding agents, with a
working agent on top. It measures each role in a bug-fixing pipeline
independently — localise, plan, code, test, review — then tests
whether a team assembled from the best model *per role* fixes more
bugs per dollar than spending the same money on one model doing
everything.

> **Status: early development, October 2026.** Nothing below is
> claimed until it appears in [`results.md`](results.md) with a
> confidence interval and the commit that produced it. Numbers that
> are not there yet are marked as such.

---

## The question

Every model has blind spots: mistakes it makes and cannot see in its
own work. A model reviewing its own patch tends to miss the errors it
made writing it. The intuition behind Blindspots is that a team drawn
from different providers covers more of those gaps than any single
model does — and, more usefully, that the roles differ in how much
model quality they actually need.

Finding which file to change is not the same job as writing the patch,
and neither is the same as judging whether the patch is right. If the
cheap roles really are cheap, a team that spends selectively should
beat a team that spends uniformly. That is a claim about cost, not
about peak capability, and it is testable.

**This is a question, not a thesis.** If measurement says a single
model everywhere wins, that result gets published here with the same
prominence.

## What it is not claiming

Blindspots is not trying to top the SWE-bench leaderboard, and it will
not. Minimal single-agent scaffolds of around a hundred lines already
score far above what this project expects to reach, and that race
belongs to well-funded labs.

The open question — the one a company paying an inference bill
actually has, and the one the minimal baselines cannot answer — is
which roles are worth paying for. That is what is measured here.

A minimal single-agent baseline runs on the same tasks with the same
models, from October, so the comparison is always visible rather than
quietly omitted.

---

## How the agent works

```
GitHub issue, or a SWE-bench task
        │
        ▼
 Fresh Docker sandbox with the repo cloned at the base commit
        │
        ▼
 Localiser ──► Planner ──► Coder ──► Tester ──► Reviewer
                             ▲                     │
                             └──── feedback ◄──────┘
        │
        ▼
 Patch + new test + plain-English explanation
```

| Agent | Job | Scored offline against |
| --- | --- | --- |
| **Localiser** | Reads the issue and codebase, finds the files and functions involved | the files the gold patch touches |
| **Planner** | Writes a short plan for the fix | downstream effect only |
| **Coder** | Writes the patch | the evaluation harness |
| **Tester** | Writes a test reproducing the bug, then runs the suite | does the test fail before the patch and pass after |
| **Reviewer** | Checks the patch, sends it back with feedback if wrong | accuracy at separating correct from incorrect patches |

Three of the five roles can be scored **directly, one model call per
example, without running the full pipeline**. That is what makes a
per-role comparison affordable, and it isolates each role's
contribution from pipeline noise.

The coder–reviewer loop is treated as a hypothesis, not a given: zero,
one and two review rounds are measured as separate configurations.
Self-correction loops are not reliably an improvement, and this
project intends to find out rather than assume.

---

## How it is measured

The measurement discipline is the substance of this project, so it is
fixed in advance and documented in
[ADR-0008](decisions.md) rather than decided after seeing results.

- **Task set:** SWE-bench Verified Mini, a published random 50-task
  subset. Using someone else's subset removes the cherry-picking
  question.
- **Dev split:** 5 tasks, committed by ID. The other 45 are not
  examined until February.
- **Paired comparison:** every configuration runs the same tasks;
  significance via McNemar on the discordant pairs.
- **Three seeds minimum,** with the run-to-run spread reported.
- **Cost per task is the primary outcome.** It is continuous, so its
  intervals are far tighter than a binary resolve rate at n=50 — and
  cost-efficiency is the actual claim.
- **Bootstrap confidence interval on every number.**
- **Prompt files are hashed into every run record.** The runner
  refuses to compare runs whose prompts differ.
- **Contamination check:** a second run on a rotating,
  contamination-free benchmark. Models score materially higher on
  SWE-bench Verified than on problems postdating their training data,
  so both numbers are reported, and the gap is itself a result.

If no significant difference is detectable at this sample size — which
is the likely outcome — that is reported, with the interval and the
sample size that would be needed.

---

## Results

*No runs yet.* [`results.md`](results.md) carries the definitions —
what counts as resolved, how cost per fix is computed, what every
entry must record — fixed before the first measurement.

| Setup | Resolved / 50 | Cost per fix | 95% CI |
| --- | --- | --- | --- |
| Minimal single-agent baseline | — | — | — |
| Five agents, one model for every role | — | — | — |
| Five agents, best model per role | — | — | — |

**Resolved** means every `FAIL_TO_PASS` test passes and every
`PASS_TO_PASS` test still passes, under the official harness. Patches
that fail to apply, jobs that hit the spend ceiling or time out, and
harness errors all count as failures. **Cost per fix** is total spend
across all attempted tasks divided by tasks resolved — the cost of
failures stays in the numerator.

---

## Architecture

| Concern | Where it runs | Why |
| --- | --- | --- |
| Development and iteration | Local, WSL2 + Docker | No per-run cost, fastest loop |
| Published benchmark runs | GitHub Actions | Free on public repos; every number gets a public CI log |
| Models | Direct provider APIs | Full access to prompt caching and batch pricing |
| Live mode: webhook → queue → worker | AWS Lambda, SQS, DynamoDB, S3 | Always-free tier, ~$0–3/month |
| Infrastructure as code | Terraform, deployed by GitHub Actions with OIDC | |

Generated code runs only inside disposable, isolated containers with
no access to credentials. Every model call passes through a token
accountant that enforces per-job ceilings on tokens, calls and
wall-clock, and aborts rather than retrying.

**On the AWS layer, stated plainly:** it is more infrastructure than
this workload needs. A single script would do the same job. It is
here because the roles this project is aimed at ask for it, and
[ADR-0006](decisions.md) records that trade-off rather than dressing
it up as a requirement.

### Development machine

Measurements in `results.md` were taken on: 16 logical processors,
19 GiB RAM allocated to WSL2, Docker Desktop. Full environment details
in [`decisions.md`](decisions.md).

---

## Design decisions

Every significant choice is recorded in
[`decisions.md`](decisions.md): context, options considered, the
decision, its consequences, and what would reverse it. Where a
decision turned out to rest on a false premise — ADR-0001 did — the
entry is superseded rather than edited, and the original reasoning
stays in git history.

---

## Roadmap

- [ ] Evaluation harness scores a gold patch on the dev split
- [ ] Run records written as JSON from the first run
- [ ] Provider adapter with prompt caching, verified against API response fields
- [ ] Per-job spend ceiling enforced in code
- [ ] Measured cost of one real task
- [ ] Single agent across the 5-task dev split
- [ ] Minimal single-agent baseline on the same tasks
- [ ] Five-agent pipeline with the coder–reviewer loop
- [ ] Offline per-role benchmarks
- [ ] Headline comparison: per-role team vs one model everywhere
- [ ] Contamination check on a rotating benchmark
- [ ] AWS live mode, deployed with Terraform
- [ ] Results dashboard

---

## Responsible use

Only install Blindspots on repositories you own or have permission to
modify. Every pull request it opens is a suggestion for a human to
review, never merged automatically.

## Author

Built by **Malay Vyas**, Master of Data Science student at Monash
University, Melbourne.

## License

MIT
