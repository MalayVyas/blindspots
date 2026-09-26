# Blindspots — Decision log

One entry per significant technical decision. Format: context, options, decision, consequences, reversal condition.

---

## ADR-0001: AWS as the primary cloud

**Date:** 2026-09-22
**Status:** accepted

### Context
Blindspots needs cloud infrastructure for the end-to-end flow (webhooks, job queue, Docker workers, storage) and for SWE-bench evaluation, which needs lots of disk, memory and x86 Linux. Budget is tight, so free credits matter. The project runs roughly six months.

### Options considered
1. **AWS** — up to $200 in new-account credits ($100 at sign-up, $100 more for using services like EC2 and Bedrock). Bedrock offers models from several makers under one bill. Most commonly requested cloud in Australian job ads. Downside: the Free plan ends after six months or when credits run out, so a switch to the paid plan may be needed near the end.
2. **Azure** — Azure for Students gives $100 for 12 months with no credit card, renewable, and includes Azure OpenAI. Smaller credit pot, less common in local job ads.
3. **GCP** — larger trial credit historically, but it expires in about 90 days, too short for this project.

### Decision
AWS. Credits can fund both infrastructure and most model calls via Bedrock, the job-market value is highest, and using EC2 and Bedrock earns the second tranche of credit. Gemini is accessed directly through Google AI Studio for provider diversity without a second cloud.

### Consequences
- Easy: one bill for infra and most models; strong CV keywords.
- Hard: must watch the six-month Free plan limit; Bedrock model availability varies by region.
- Locked in: Terraform keeps infrastructure portable, reducing lock-in.

### Reversal condition
If Bedrock lacks needed models in a usable region, or credits run out early, fall back to Azure for Students.

---

## ADR-0002: AWS region

**Status:** open — check Bedrock model availability in Sydney (ap-southeast-2) vs US regions before deciding.

---

## Environment — development machine

**Recorded 2026-09-26.** Reproducibility baseline for every local
measurement in `results.md`.

| Component | Value |
| --- | --- |
| Host OS | Windows, WSL2 + Docker Desktop |
| Logical processors | 16 |
| Host RAM | 32 GB (~32,098 MB reported) |
| Free disk, E: | ~429 GB |
| Project root | `E:\Blindspots` |

**Against SWE-bench's stated requirements** (8 CPUs, 16 GB RAM, 120 GB
disk for the full environment-image set): this machine clears all
three with margin. Running the complete benchmark locally is viable,
so GitHub Actions is a deliberate choice for public CI evidence and
parallelism rather than a necessity forced by hardware.

**Open item — WSL2 allocation.** WSL2 receives a fraction of host RAM
and cores by default, and that allocation, not the host figure above,
is what bounds Docker. Record `nproc` and `free -h` from inside WSL
and add them here. Raise via `%UserProfile%\.wslconfig` if short.

**Open item — WSL2 disk location.** The WSL virtual disk
(`ext4.vhdx`) and Docker Desktop's image store default to the C:
drive, not E:. SWE-bench environment images are tens of gigabytes, so
confirm where they will actually land before the first large pull, and
relocate the Docker disk image to E: if C: is tight.
