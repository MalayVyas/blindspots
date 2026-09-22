# Blindspots

**A multi-agent coding system that fixes bugs in GitHub repositories.**

Label an issue, and Blindspots reads the repo, finds the bug, writes a fix, tests it, has a second agent review it, and opens a pull request explaining what was wrong. Each agent on the team runs on the model that performs best at its specific job, drawn from different AI providers.

> 🚧 **Status: early development.** Features and results below will be filled in as they're built. Every number in this repo will be reproducible from the code.

---

## Why "Blindspots"?

Every AI model has blind spots: kinds of mistakes it keeps making and can't see in its own work. A model reviewing its own patch tends to miss the same errors it made writing it.

Blindspots builds its agent team from models made by different providers, so one agent's blind spots are covered by another's. Which model gets which role is decided by measurement, not reputation.

## How it works

```
GitHub issue labelled "blindspots-fix"
        │
        ▼
 Fresh Docker sandbox with the repo cloned
        │
        ▼
 Localiser ──► Planner ──► Coder ──► Tester ──► Reviewer
                             ▲                     │
                             └──── feedback ◄──────┘
        │
        ▼
 Pull request: fix + new test + plain-English explanation
```

| Agent | Job |
| --- | --- |
| **Localiser** | Reads the issue and codebase, finds the files and functions involved |
| **Planner** | Writes a short plan for the fix |
| **Coder** | Writes the patch |
| **Tester** | Writes a test that reproduces the bug, then runs the test suite |
| **Reviewer** | Checks the patch and sends it back with feedback if it's wrong |

The coder and reviewer loop for a limited number of rounds. If no fix passes review, Blindspots comments on the issue with what it found instead of opening a bad PR.

## Two modes

**Live mode** — install the Blindspots GitHub App on a repository you own. Labelling an issue triggers a run, and the result arrives as a pull request.

**Benchmark mode** — runs the same agent team on a fixed sample of tasks from [SWE-bench](https://www.swebench.com/), a standard benchmark of real bugs from popular open-source Python projects, to measure how often it actually succeeds.

## Architecture

Blindspots runs end to end on AWS.

| Component | Service |
| --- | --- |
| Receives GitHub webhooks | API Gateway + Lambda |
| Job queue | SQS |
| Runs the agent team in Docker | EC2 worker |
| AI models | Amazon Bedrock + Google Gemini API |
| Logs, patches, agent transcripts | S3 |
| Job and cost tracking | DynamoDB |
| Secrets | SSM Parameter Store |
| Monitoring and budget alerts | CloudWatch + AWS Budgets |
| Infrastructure as code | Terraform |
| CI/CD | GitHub Actions |

All generated code runs inside disposable, isolated containers with no access to credentials.

## Results

*Coming soon.*

| Setup | Bugs fixed (SWE-bench sample) | Cost per bug fixed |
| --- | --- | --- |
| Single model doing every role | — | — |
| Blindspots mixed-model team | — | — |

The headline question: does the mixed team fix more bugs per dollar than one model doing everything? If it doesn't, that will be reported here too.

## Project structure (planned)

```
blindspots/
├── agents/        # the five agents and their prompts
├── providers/     # one adapter per model provider
├── orchestrator/  # passes work between agents
├── sandbox/       # Docker execution environment
├── github_app/    # webhook handling and pull request creation
├── benchmark/     # SWE-bench runner and metrics
├── infra/         # Terraform for AWS
├── dashboard/     # job viewer
└── decisions/     # architecture decision records
```

## Design decisions

Every significant technical choice is documented in [`decisions/`](decisions/): what was chosen, the alternatives considered, why this option won, and what would make it the wrong call.

## Roadmap

- [ ] Single agent fixes one SWE-bench task inside a Docker sandbox
- [ ] Five-agent pipeline with the coder–reviewer loop
- [ ] Provider adapters with cost tracking and response caching
- [ ] Per-role model evaluation to assign models to agents
- [ ] Benchmark run on a SWE-bench sample
- [ ] GitHub App: issue label → pull request
- [ ] AWS deployment with Terraform
- [ ] Job dashboard
- [ ] Demo video

## Getting started

*Setup instructions will be added once the first working version lands.*

## Responsible use

Only install Blindspots on repositories you own or have permission to modify. Every pull request it opens is a suggestion for a human to review, never merged automatically.

## Author

Built by **Malay Vyas**, Master of Data Science student at Monash University, Melbourne.

## License

MIT
