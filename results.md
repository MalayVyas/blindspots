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

*No runs yet. First entry due Week 1 of October: the evaluation
harness scoring gold patches on the dev split.*
