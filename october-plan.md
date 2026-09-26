# Blindspots — October plan

Written 2026-09-26. Week by week, with an acceptance test for each
week and a stated cut list if a week slips. Budget: ~12 hours a week.

## The ordering principle

**Build the evaluation before the agent.**

The original plan had the sandbox and a single agent in October and
benchmarking later. Flip it. The first thing that works end to end
should be: *take a patch, run it against a SWE-bench task, get a
verdict* — no agents involved. Just the official harness, one task, a
gold patch, and a pass.

You cannot improve what you cannot score. Every question after October
— which model, how many review rounds, did caching break something — is
settled by that harness. If it exists in week one, every later decision
is measured. If it exists in December, you spend two months arguing
from intuition.

## The $100 cloud-session credit expires 5 November

**[PRIMARY — support.claude.com]** The $100 is scoped to *cloud
sessions*: Claude Code tasks running on Anthropic's infrastructure
against a connected GitHub repository. It cannot fund Blindspots'
own model calls — those bill to a separate API meter (see `budget.md`).
It can fund a large amount of Claude helping you *build* Blindspots.

Two consequences for this plan:

1. **Creating the public repo moves up the priority list.** Cloud
   sessions work against a connected GitHub repo, so the credit is
   unusable until the repo exists. It is already Week 0 item 7 —
   treat it as blocking rather than housekeeping.
2. **Front-load.** The credit dies on 5 November, five days into exam
   month, when you have the least time to spend it. Anything
   mechanical and well-specified should be pulled into October.

**What cloud sessions are good for here** — well-specified plumbing
against a repo, which is most of weeks 1 and 2: wiring the SWE-bench
harness, the run-record schema, the provider adapter, the Actions
matrix, the token accountant. Write a tight task description, let it
open a pull request, review the diff yourself.

**What to keep hands-on** — anything where the judgement *is* the work.
Week 3's cache verification is the clearest example: the whole point is
that you personally confirm the cache fields in the API response rather
than trusting that it worked. Delegating that defeats it. Same for
choosing the dev split and writing the ADRs.

**Do not** stretch October's scope because the help is subsidised.
Cheaper help is a reason to finish October's plan with margin, not a
reason to pull December forward. Scope creep is R-13, and a free
credit is exactly the kind of thing that causes it.

---

## The thing that must not be skipped

**From run number one, write the full run record to disk**: task ID,
config hash, prompt hashes, model, tokens in / out / cached, cost,
wall-clock, the patch, the complete transcript, and the outcome. As
JSON, one file per run.

Two reasons. It is the only way cost-per-fix is ever computable. And
every failed patch October produces becomes labelled data for the
reviewer benchmark in January — gold patches are the positive class,
your failures are the negative class. That dataset is free if you save
it from day one and expensive to reconstruct later.

---

## Week 0 — Sep 26 to 30 (~6h): remove the unknowns

Everything here is cheap and unblocks a decision.

| # | Task | Time |
| --- | --- | --- |
| 1 | ~~Check AWS plan status~~ **done — upgraded to Paid.** Still set a $5 Budgets alarm | 5m |
| 2 | ~~Open Azure for Students~~ **done — $100 available** | — |
| 3 | ~~Open DeepSeek API account~~ **done.** GitHub Student Developer Pack also claimed | — |
| 4 | Record your PC's RAM, core count and free disk — **and the RAM/cores WSL2 actually gets**, which is what constrains Docker. Write both into `decisions.md` | 10m |
| 5 | Confirm Monash 2027 Semester 1 dates | 10m |
| 7 | **Blocking — do this first.** Create the **public** repo and connect it to Claude Code cloud sessions. Push README rewritten to the question form, plus `decisions.md`, `results.md`, `risks.md`, `solutions.md`, `budget.md`, `october-plan.md`. Until this exists the $100 credit cannot be spent | 1h |
| 8 | **The spike** — see below | 2–3h |

### The spike

A GitHub Actions workflow that: pulls one SWE-bench environment image,
checks out the task's repo at the base commit, applies the **gold**
patch, runs the FAIL_TO_PASS and PASS_TO_PASS tests, and goes green.

This is the highest-information three hours available to you. If it
works, your benchmark platform is free forever and the EC2 worker never
gets built. If it does not — 14GB of runner disk is tight, and image
pulls may be slow — you find out now rather than in December.

Log the disk actually used and the wall-clock. You need both to know
whether a 50-job matrix is viable.

**Fallbacks if the spike fails**, in order: run benchmarks locally only;
a self-hosted runner on your own PC (free, and your E: drive has
headroom); a paid larger runner. Do not go back to EC2 without
re-reading R-05.

**Acceptance:** a green CI run at a public URL you could paste to
someone, with disk and wall-clock recorded.

**If the week slips:** items 1–6 can move into Oct week 1. The spike
cannot — everything else is built on the answer.

---

## Week 1 — Oct 1 to 7 (~12h): the scoreboard

**Goal:** you can score any patch against any task in your dev set,
locally and in CI.

1. Install the official SWE-bench harness in WSL2; confirm Docker works. *(2h)*
2. Choose your **5-task dev split** from SWE-bench Verified Mini. Commit the task IDs to the repo. **Do not look at the other 45 tasks again until February.** *(30m)*
3. Evaluate all 5 gold patches locally. Expect 5/5 resolved. *(2h)*
4. Evaluate 5 empty patches. Expect 0/5. This proves your harness can fail — a harness that always passes is worse than none. *(30m)*
5. `results.md` entry #1: harness working, 5/5 gold, 0/5 empty, disk used, wall-clock per task. *(30m)*
6. Wire the same 5 tasks into the Actions matrix from week 0. *(2h)*
7. Define and implement the **run record** schema described above. JSON, one file per run, written from the very first run. *(2h)*

**Acceptance:** one command gives a verdict for a given patch and task,
locally and in CI. Gold passes, empty fails. Every run writes a JSON
record.

**Cut list:** item 6 moves to week 2. **Do not cut item 7** —
retrofitting the run record later is painful and costs you the reviewer
dataset.

---

## Week 2 — Oct 8 to 14 (~12h): first agent, on a leash

**Goal:** one model, one prompt, produces a patch, and cannot run away
with your money.

1. **Provider adapter** for DeepSeek: chat completion, token counts read back from the response, cache fields surfaced. *(3h)*
2. **Token accountant and spend ceiling.** Per job: max input tokens, max output tokens, max model calls, max wall-clock. On breach, abort and write the partial transcript rather than retrying. Refuse to start if projected cost exceeds the cap. *(3h)*
3. **Simplest possible agent:** issue text plus repo file tree plus relevant file contents in, unified diff out. No roles. No loop. *(3h)*
4. Run it on dev task 1. Expect it to fail. Capture the run record. *(2h)*

**Acceptance:** the agent emits a diff the harness can apply — resolved
or not — and a deliberately broken loop hits the ceiling and aborts
cleanly. The cost of that run is in `results.md`.

**Cut list:** simplify item 3 to a bare "here is the issue, here are
the files, return a diff" prompt. **Do not cut item 2.** The ceiling is
what makes every later experiment safe to run unattended.

---

## Week 3 — Oct 15 to 21 (~12h): caching, and October's number

**Goal:** the measurement that replaces every estimate in `budget.md`.

1. Restructure every prompt as `[stable repo context][variable instruction]` so a cache prefix can actually hit. *(2h)*
2. **Verify cache hits by reading the cache fields in the API response**, not by assuming. Log the hit rate per call. *(2h)*
3. Run dev task 1 three times. Record cost, tokens, cached fraction and wall-clock each time. *(2h)*
4. Measure the same task with caching disabled. The ratio is your first real finding. *(1h)*
5. `results.md` entry: measured cost per task, cache hit rate, spread across three runs. *(1h)*
6. Replace every `[ESTIMATE]` in `budget.md` with measured values and re-derive the six-month budget. *(2h)*

**Acceptance:** `results.md` contains a measured cost per task with a
three-run spread and a stated cache hit rate. `budget.md` no longer
contains estimated per-task costs.

**Cut list:** item 6 moves to week 4. **Do not cut item 2** —
unverified caching is worse than no caching, because you will believe a
number that is wrong.

A note on item 3: three runs of the same task on the same config is
also your first measurement of run-to-run variance (R-07). If the
spread is large, that changes how many seeds February needs. Write down
whatever you see, even if it is untidy.

---

## Week 4 — Oct 22 to 31 (~15h): baseline and decisions

**Goal:** a first honest number, and the decisions written down before
they go stale.

1. Run the single agent across all 5 dev tasks, one seed. Expect 0–2 out of 5. *(3h)*
2. Update the README with the first real resolve rate and cost. *(1h)*
3. **Install and run mini-swe-agent** on the same 5 tasks with the same model. *(3h)*
4. Write the ADRs *(4h)*:
   - **ADR-0001 rewritten** — AWS, with its real reasoning: always-free serverless tier plus job-market keywords, not credits
   - **ADR-0002 closed** — the region question is moot with no EC2
   - **ADR-0003** — Bedrock off the critical path
   - **ADR-0004** — benchmark platform: GitHub Actions over EC2
   - **ADR-0005** — the comparison protocol, pre-registered
   - **ADR-0006** — dev/test split, with the committed task IDs
5. **Month review:** hours actually spent against the 12/week assumption. Re-estimate November honestly. *(1h)*

**Acceptance:** the README shows a real resolve rate and cost for both
your agent and mini-swe-agent on the 5 dev tasks. Six ADRs exist. You
have a true hours-spent figure.

**Cut list:** the mini-swe-agent baseline can move to December, but no
later — it is the comparison every reviewer will reach for. **ADR-0005
cannot slip past the first comparison run**, because a protocol written
after seeing results is not a protocol.

Item 3 is scheduled deliberately early. A baseline that makes your
numbers look worse is exactly the baseline that gets quietly dropped in
March, so run it while it costs nothing to be honest.

---

## Do not touch in October

Five agents. AWS beyond the plan check. Terraform. The GitHub App. Any
model comparison. The dashboard. Each is cheaper once you can score a
patch, and three of them may not survive the cuts in `solutions.md`.

## Signals you are off track

- **End of week 1 and the harness does not score a gold patch.** Stop
  adding features and fix that. Nothing downstream works without it.
- **Week 2 ends with no spend ceiling.** Do not run anything unattended
  until it exists.
- **Week 3's measured cost per task is more than 5x the estimate in
  `budget.md`.** Re-plan February before building anything else — the
  experiment design depends on that number.
- **You are past 15 hours a week.** November is exams. Cut scope now
  rather than borrowing from a month that has nothing to lend.

## What October hands to November

November is exams, under 10 hours a week, and should be
low-concentration work only: a second provider adapter, and tidying.
For that to be possible, October must end with a working scoreboard, a
working single agent, a spend ceiling, verified caching, one measured
cost figure, and the decisions written down.

Nothing on that list requires five agents. That is the point.
