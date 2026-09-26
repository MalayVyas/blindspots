# CLAUDE.md

Conventions for any Claude session working in this repository —
Claude Code in the terminal, a cloud session, or Cowork.

## What this project is

Blindspots asks: **given a fixed inference budget, which roles in a
multi-agent coding pipeline justify a more expensive model?** It is a
role-level benchmark for AI coding agents with a working agent on top.
Portfolio project, October 2026 to March 2027, ~12 hours a week.

It is **not** chasing a peak SWE-bench score — minimal 100-line
scaffolds already beat what this will reach. The claim is about cost
and role allocation.

## Read before changing anything

- `state.md` — current state, what is open, what is stale
- `decisions.md` — ADR-0001 to ADR-0009. Binding; do not relitigate
- `results.md` — measurement definitions, fixed before any run
- `october-plan.md` — week by week, with acceptance tests

## Rules that are not negotiable

- **Evaluation before agents.** Nothing is built that cannot be
  scored.
- **Every run writes a full JSON record**: task ID, config hash,
  prompt hashes, model, tokens in/out/cached, cost, wall-clock, the
  patch, the full transcript, the outcome. From run number one.
- **Prompt structure is `[stable context][variable instruction]`.** No
  timestamps, task IDs or other varying content above the stable
  prefix — one changed token silently disables the cache, which is the
  dominant cost lever.
- **Cache hits are verified** by reading the API response fields,
  never assumed.
- **Every model call passes through the token accountant** with
  per-job ceilings on tokens, calls and wall-clock. Abort, do not
  retry.
- **The comparison protocol (ADR-0008) is pre-registered.** Identical
  prompts across configurations; only the model binding varies. A
  prompt change after seeing results invalidates the run.
- **The 45 held-out tasks are not looked at until February.** Dev
  split is 5 tasks, committed by ID.

## Writing style for docs and commits

- Tag factual claims by source: `[PRIMARY]` vendor or project docs,
  `[SECONDARY]` third-party, `[ESTIMATE]` arithmetic on stated
  assumptions, `[JUDGEMENT]` opinion. **Never let an estimate read as
  a measurement.**
- Every significant technical choice gets an ADR in `decisions.md`:
  context, options considered, decision, consequences, reversal
  condition.
- Plain language. Expand abbreviations on first use.
- Flag weak ideas, cost risks and scope creep bluntly and early.

## Environment

Windows host, WSL2 + Docker Desktop. 16 cores, 19 GiB RAM in WSL2,
~429 GB free on E:. Docker's image store lives on E:, outside this
repo. Start the SWE-bench harness at **8 workers** — RAM, not cores,
bounds concurrency at roughly 1–2 GB per container.

`E:\Blindspots` holds source and documents only. No caches, no data
stores, no virtual disks.

## Which surface does what

- **Claude Code in the terminal** — code, tests, Docker, git.
- **Cowork** — planning, research, docs, review. It reaches this
  folder through a bridge that cannot delete files, so **it must not
  run git commands here**; every git write strands a lock file.
- **Cloud sessions** — self-contained, well-specified tasks that end
  in a pull request. Good for plumbing; keep judgement work local.

Coordinate through git. Commit before switching surfaces. Never have
two surfaces editing at once.

## Private files

`risks.md`, `solutions.md` and `budget.md` are in `.gitignore` and
stay local. They contain candid self-assessment and personal budget
figures. Do not commit them, and do not quote their contents into
files that are committed.
