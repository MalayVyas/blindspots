# Blindspots — Budget

Rewritten 2026-09-26 from vendor pricing pages. **Supersedes** the cost
figures in `solutions.md` (Move 3, R-01 to R-04) and invalidates
ADR-0001's reasoning.

## How to read this document

- **[PRIMARY]** — from the vendor's own pricing page, fetched
  2026-09-26. Act on it, but re-check before any large spend; these
  pages change without notice.
- **[ESTIMATE]** — Claude's arithmetic on *assumed* token counts.
  Not a measurement. Ratios between rows are more trustworthy than
  absolute values, because the rows share assumptions.
- **[JUDGEMENT]** — opinion.

The single most important line in this document: **every per-task
figure here is an estimate until you measure one real task in
October.** That measurement is the whole point of October.

---

## Urgent: check your AWS account's plan today

**[PRIMARY — AWS Free Tier FAQ]** Under the current AWS Free Plan, the
plan ends after six months or when credits run out, whichever comes
first, and at that point AWS **closes** the account. There is a 90-day
window to upgrade to the Paid plan before the account and its contents
are permanently erased.

Your credits are gone, so one of two things is true:

1. **Already on the Paid plan.** Nothing to do.
2. **Still on the Free plan.** A closure clock may already be running.
   Upgrade to Paid, then set an AWS Budgets alarm at $5/month.

Check this before any other AWS work.

---

## AWS with no credits still costs roughly nothing

**[PRIMARY]** The always-free tier has no expiry and applies on the Paid
plan: Lambda 1M requests and 400,000 GB-seconds, DynamoDB 25GB,
CloudWatch 10 metrics / 10 alarms / 5GB logs, SQS 1M requests, SSM
Parameter Store standard tier. S3 and API Gateway fall to pay-as-you-go
after the first year, at cents for this workload.

**[ESTIMATE] Expected AWS bill: $0–3/month.** The expensive component —
an EC2 worker with a 150GB EBS volume — was already cut when the
benchmark moved to GitHub Actions (Move 1 in `solutions.md`).

**[JUDGEMENT]** ADR-0001's conclusion survives; its reasoning does not.
Rewrite it: AWS stays because the serverless slice is genuinely free at
this scale and the keywords matter in local job ads — not because it
funds the models.

**Drop Bedrock from the critical path.** Credits were its only
justification. Route measured runs through direct provider APIs; keep
the Bedrock adapter and run one demonstration call through it so the
multi-provider claim is real.

---

## Two separate meters — do not confuse them

**[PRIMARY — support.claude.com, fetched 2026-09-26]** Anthropic bills
two different things, and only one of them can fund Blindspots.

| | **Plan usage / usage credits** | **API (Console)** |
| --- | --- | --- |
| What it covers | Claude conversations, Claude Code, cloud sessions, Projects | programmatic calls from your own code, via an API key |
| How you spend it | by chatting or by running Claude Code | by your provider adapter making HTTP requests |
| Malay's $100 cloud-session credit | **applies here** | **does not apply** |

The support documentation is explicit: usage credits are **"not
available for Anthropic API Console calls"**. The $100 expiring
5 November is scoped narrower still — to *cloud sessions*, meaning
Claude Code tasks running on Anthropic's infrastructure against a
connected GitHub repository.

**Consequences for this budget:**

1. **The model-spend estimates below are unchanged.** Every benchmark
   run bills to an API key on the API meter. The $100 cannot touch it.
2. **The $100 is a build subsidy, not an inference subsidy.** It pays
   for Claude helping *write* Blindspots, not for Blindspots calling
   models.
3. **Do not design the agent around cloud sessions as an inference
   backend.** They are a coding-agent product, not an inference
   endpoint — not programmatically callable from your pipeline, and
   they share rate limits with all other Claude Code usage.
4. **It expires 5 November**, which falls inside exam month. See
   `october-plan.md` — this is now a reason to front-load.

---

## Vendor pricing, fetched 2026-09-26

### Anthropic **[PRIMARY — claude.com/pricing]**

Per million tokens. Batch processing is 50% off across models.

| Model | Input | Output | Cache read | Cache write |
| --- | --- | --- | --- | --- |
| Haiku 4.5 | $1 | $5 | $0.10 | $1.25 |
| Sonnet 5 | $2 | $10 | $0.20 | $2.50 |
| Opus 5.5 | $4 | $20 | $0.20 | $5.00 |
| Fable 5.1 | $10 | $50 | $0.25 | $12.50 |

Two gotchas: US-only inference costs 1.1x standard, and Opus 5.5 fast
mode costs 2x. Neither applies unless you opt in.

**Correction to an earlier draft:** it quoted "Opus 5 at $5/$25". The
vendor page lists **Opus 5.5 at $4/$20**. Haiku and Sonnet were right.

### DeepSeek **[PRIMARY — api-docs.deepseek.com]**

| Model | Cache hit in | Cache miss in | Output |
| --- | --- | --- | --- |
| `deepseek-flash` peak | $0.006 | $0.30 | $1.20 |
| `deepseek-flash` off-peak | $0.003 | $0.15 | $0.60 |
| `deepseek-v4-pro` peak | $0.044 | $1.32 | $3.96 |
| `deepseek-v4-pro` off-peak | $0.022 | $0.66 | $1.98 |

Off-peak is exactly half of peak. **Peak hours are 01:00–04:00 and
06:00–10:00 UTC, Monday to Friday**; everything else — including all
weekend — is off-peak.

In Melbourne (AEDT, UTC+11, from 4 October): peak is 12:00–15:00 and
17:00–21:00. **Anything you run after 9pm, before noon, or at the
weekend is half price.** Overnight benchmark runs land in the discount
window automatically.

The cache-hit rate of $0.003–$0.006 per million is the outlier on this
whole page — 30 to 60 times below Haiku's cache read. In a pipeline
that re-reads the same repository context fifteen times, that one
number dominates the bill.

### Google Gemini **[PRIMARY — ai.google.dev/gemini-api/docs/pricing]**

| Model | Input | Output | Context cache |
| --- | --- | --- | --- |
| Gemini 3.8 Flash (to 2026-12-31) | $0.75 | $3.75 | $0.075 |
| Gemini 3.8 Flash (from 2027-01-01) | **$1.50** | **$7.50** | **$0.15** |
| Gemini 3.5 Flash-Lite | $0.30 | $2.50 | — |
| Gemini 3.1 Pro Preview (≤200k) | $2.00 | $12.00 | — |

Batch is 50% off. Context caching is **paid tier only**.

**Flag this one.** Gemini 3.8 Flash doubles in price on **1 January
2027** — which is exactly when the per-role evaluation and headline
comparison are scheduled. Either run the Gemini arm in December at half
the 2027 price, or budget the higher rate, or use Flash-Lite. Do not
plan January's Gemini spend on today's number.

Also: the **free tier uses your content to improve Google's products**,
and context caching is unavailable on it. Fine for exploration,
unsuitable for a measured benchmark run.

---

## Cost per task **[ESTIMATE — this is the shaky part]**

There is no measurement behind these. They assume one task means:

- ~15 model calls across five agents (plausible range: 8–40)
- ~50k tokens of shared repository context (range: 20k–150k)
- ~10k unique tokens per call
- ~20k output tokens total (range: 5k–60k)

Under those assumptions, with prompt caching working:

| Configuration | Cost per task |
| --- | --- |
| DeepSeek Flash, off-peak | **~$0.04** |
| DeepSeek Flash, peak | ~$0.09 |
| Gemini 3.8 Flash (2026 price) | ~$0.28 |
| Haiku 4.5 | ~$0.38 |
| Sonnet 5, batched | ~$0.38 |
| Gemini 3.8 Flash (2027 price) | ~$0.55 |
| Sonnet 5 | ~$0.77 |
| Opus 5.5 | ~$1.39 |

**Sensitivity.** Push the assumptions to the pessimistic end — 40 calls,
150k context, 60k output — and DeepSeek off-peak goes from $0.04 to
about **$0.14**, roughly 3.5x. Every row scales similarly. So read
the table as "DeepSeek is roughly ten times cheaper than Sonnet for
this shape of work", which is robust, and not as "it costs four cents",
which is not.

---

## Budget **[ESTIMATE — range, not a number]**

| Phase | Design | Low | High |
| --- | --- | --- | --- |
| Dev and debug, Oct–Dec | 5-task dev set, DeepSeek Flash | $10 | $40 |
| Role screening, Jan | offline single-call scoring | $5 | $20 |
| Role confirmation, Jan | 6 configs x 20 dev tasks | $8 | $30 |
| Headline, Feb | 50 tasks x 3 configs x 3 seeds, DeepSeek | $20 | $70 |
| Premium arm | 50 tasks x 1 config x 2 seeds, Sonnet 5 | $38 | $120 |
| Gemini arm | 50 tasks x 1 config (run in December) | $14 | $45 |
| Contamination check | 20 rotating tasks x 2 configs | $3 | $10 |
| AWS infrastructure | always-free plus overflow, 6 months | $0 | $20 |
| GitHub Actions | free on public repositories | $0 | $0 |
| **Total** | | **~$100** | **~$355** |

Central case around **$230 across six months**, or roughly $40/month.
Against $100 of Azure for Students **[PRIMARY — azure.microsoft.com]**
(12 months, renewable, no credit card) the cash exposure is roughly
**$130 across the project**.

### If it needs to be cheaper

1. **Run off-peak.** Halves DeepSeek spend for nothing but scheduling.
   Do this regardless.
2. **Run the Gemini arm in December**, before the 1 January price
   doubling.
3. **Use Azure for Students for the premium arm** instead of cash.
4. **Cut the headline sample from 50 to 30 tasks.** ~40% off that line.
5. **Cut three seeds to two.** ~33% off. Report the reduced spread.
6. **Drop the premium arm.** Costs the price-range story. A cheaper
   substitute: run the price-range comparison inside DeepSeek's own
   catalogue, `deepseek-flash` against `deepseek-v4-pro`, which is a
   4–7x spread for a few dollars.

**Not on this list:** free tiers and aggregator endpoints for measured
runs. Rate limits and best-effort capacity make run-to-run comparison
meaningless, and Gemini's free tier trains on your content. Use them
for exploration; never produce a published number on one.

---

## The reframing this enables **[JUDGEMENT]**

Losing the credits pushes the project into the cheap-model regime, and
that is where its question is most interesting. The labs publish
frontier SWE-bench numbers themselves. What almost nobody publishes is
**which role in a coding-agent pipeline justifies a more expensive
model** — whether the localiser and tester can run at $0.30 per million
while you spend only on the planner and reviewer, and what that does to
cost per fix.

That question only exists on a tight budget. It is the question a
company paying an inference bill actually has. And the 100-line
single-agent baselines cannot answer it at all.

> Given a fixed inference budget, which roles in a multi-agent coding
> pipeline justify a more expensive model? Blindspots measures each
> role independently, then tests whether the resulting mixed team fixes
> more bugs per dollar than spending the same money on one model
> everywhere.

---

## Actions

1. ~~Check AWS plan status.~~ **Done 2026-09-26 — upgraded to Paid.**
   Still set an AWS Budgets alarm at $5/month if you have not. **(Today.)**
2. ~~Open Azure for Students.~~ **Done 2026-09-26** — $100 available,
   earmarked for the premium comparison arm.
3. ~~Open a DeepSeek API account.~~ **Done 2026-09-26.** GitHub Student
   Developer Pack also claimed.
4. Rewrite ADR-0001 with its real reasoning. Add an ADR dropping
   Bedrock from the critical path. **(This week.)**
5. **Measure one real task in October** with caching on and the spend
   ceiling enforced. Replace every [ESTIMATE] on this page with the
   measured value. **(October, week 3.)**
