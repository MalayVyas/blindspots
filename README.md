# Blindspots

**Do mixed-model agent teams fix more bugs than a single model?**

Blindspots is a multi-agent coding system that resolves real GitHub issues from [SWE-bench](https://www.swebench.com/). Its agents run on models from different providers, and the project measures one question honestly: **at the same cost, does a team of *different* models beat the best single model?**

> 🚧 **Status: early development.** Results below will be filled in as experiments run. Every number in this repo will be reproducible from the code.

---

## The idea

Every language model has blind spots: kinds of mistakes it keeps making and can't see in its own work. When a model reviews its own patch, it tends to miss the same errors it made writing it.

Models from different providers are trained differently, so their blind spots don't fully overlap. Blindspots tests whether that diversity is useful in practice: if one model writes a patch and a *different* model reviews it, are more bugs caught and fixed?

Rather than assigning roles by reputation ("model X is good at code"), Blindspots **measures** each model on each role first, then builds teams from the measurements.

## How it works

A bug fix is split into five roles, each handled by an agent:

| Role | Job |
| --- | --- |
| **Localiser** | Find the files and functions where the bug lives |
| **Planner** | Write a short plan for the fix |
| **Coder** | Write the patch |
| **Tester** | Write a test that reproduces the bug |
| **Reviewer** | Critique the patch and send it back if it's wrong |

Each role can be assigned to any model from any supported provider. All agent code runs inside disposable Docker containers.

## The experiment

Four configurations, run on the same tasks with the **same budget per task**:

1. **Solo** — the best single model does everything alone
2. **Mono-team** — one model plays all five roles
3. **Mixed team** — each role uses the model that scored best on it
4. **Cheap mix** — low-cost models everywhere except one stronger coder

### Metrics

- **Resolve rate** — share of issues fixed (patch passes the task's tests)
- **Cost per resolved issue** — API spend divided by issues fixed
- **Tokens and latency per task**
- **Failure analysis** — which role or hand-off caused each failure

A negative result ("mixing models didn't help, and here's why") is a valid outcome and will be reported as such.

## Results

*Coming soon.* This table will be filled in from the experiment runs.

| Configuration | Resolve rate | Cost / resolved issue | Notes |
| --- | --- | --- | --- |
| Solo | — | — | |
| Mono-team | — | — | |
| Mixed team | — | — | |
| Cheap mix | — | — | |

## Built to be cheap

Evaluating agents on SWE-bench can get expensive quickly. Blindspots is designed to run on a student budget:

- A fixed sample of 50–100 tasks from SWE-bench Lite / Verified, not the full set
- Low-cost model tiers for most roles
- Every model call cached, so reruns cost nothing
- Free tiers used during development; full comparisons only at milestones
- Cost tracked per call, per role, and per task

## Project structure (planned)

```
blindspots/
├── agents/        # role definitions and prompts
├── providers/     # one adapter per model provider
├── orchestrator/  # hands tasks between roles
├── sandbox/       # Docker execution environment
├── eval/          # SWE-bench harness, metrics, cost tracking
├── experiments/   # configs for each experiment run
├── decisions/     # architecture decision records (ADRs)
└── results/       # raw results and analysis
```

## Design decisions

Every significant technical choice is documented in [`decisions/`](decisions/) as an architecture decision record: what was chosen, what the alternatives were, why this option won, and what would make it the wrong call.

## Roadmap

- [ ] Sandbox and single-agent baseline running on a small task sample
- [ ] Provider adapters with cost tracking and caching
- [ ] Five-role orchestrator
- [ ] Per-role model evaluation
- [ ] Full four-configuration comparison
- [ ] Failure analysis and write-up
- [ ] Demo video

## Getting started

*Setup instructions will be added once the first working version lands.*

## Author

Built by **Malay Vyas**, Master of Data Science student at Monash University, Melbourne.

## License

MIT
