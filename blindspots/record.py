"""Run record: one JSON file per task attempt (ADR-0011).

Every number in results.md is computed from these files. A record is
written once and never changed.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, model_validator

SCHEMA_VERSION = 2
# Version history (ADR-0011: never edit old records, keep a reader for them):
#   1  Week 1. Usage held input/output/cached tokens and one cost_usd.
#   2  Week 2. Usage adds cache-miss and reasoning tokens and three costs
#      (ADR-0013, ADR-0014); outcome provider_error; a `breach` block.
#   A version-1 file still loads: every new field has a default.


class Outcome(str, Enum):
    """Exactly one per record. Mirrors the failure definitions in results.md."""

    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    PATCH_APPLY_FAILED = "patch_apply_failed"
    EMPTY_PATCH = "empty_patch"
    HARNESS_ERROR = "harness_error"
    SPEND_CEILING = "spend_ceiling"        # from Week 2 (ADR-0009)
    WALL_CLOCK_LIMIT = "wall_clock_limit"  # from Week 2 (ADR-0009)
    PROVIDER_ERROR = "provider_error"      # schema 2: the model API failed; no patch


class _Strict(BaseModel):
    # extra="forbid": a misspelt field name is an error, not a silent new field.
    # frozen=True: a record cannot be changed after it is built.
    model_config = ConfigDict(extra="forbid", frozen=True)


class SuiteResults(_Strict):
    fail_to_pass_passed: list[str]
    fail_to_pass_failed: list[str]
    pass_to_pass_passed: list[str]
    pass_to_pass_failed: list[str]


class Timing(_Strict):
    """Wall-clock for one task, from the harness's own log (run_instance.log).

    image_pull_s: first log line to "container created" (None if the image
        was already local). Includes container creation, ~0.1-4 s.
    evaluation_s: "container created" to the last log line.
    test_runtime_s: the harness's own "Test runtime" figure, inside evaluation_s.
    teardown_s: "attempting to stop container" to the last line, inside
        evaluation_s. The harness waits up to 15 s for the stop.
    """

    started_at: datetime
    finished_at: datetime
    image_pull_s: float | None = None
    evaluation_s: float | None = None
    test_runtime_s: float | None = None
    teardown_s: float | None = None


class Usage(_Strict):
    """Model usage for the whole job. All zero for patches not from a model.

    input_tokens = cached_input_tokens + cache_miss_input_tokens (schema 2).
    output_tokens includes reasoning_tokens.
    cost_usd       what was billed (the name is kept from schema 1).
    reference_usd  the same tokens at off-peak list price; comparisons use
                   this (ADR-0013).
    ceiling_usd    the same tokens at peak price; the spend ceiling counts
                   this (ADR-0014).
    """

    model_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    cost_usd: float = 0.0
    # schema 2
    cache_miss_input_tokens: int = 0
    reasoning_tokens: int = 0
    reference_usd: float = 0.0
    ceiling_usd: float = 0.0


class Breach(_Strict):
    """Which limit stopped the job, and by how much (ADR-0014)."""

    limit: Literal["calls", "input_tokens", "output_tokens", "cost_usd", "wall_clock_s"]
    allowed: float        # the limit
    would_reach: float    # the total the job had reached, or would have reached
    before_call: bool     # True: refused before sending, nothing billed for it


class Environment(_Strict):
    blindspots_commit: str
    swebench_version: str
    dataset_name: str
    dataset_revision: str | None
    python_version: str
    docker_version: str | None
    machine: Literal["local", "ci"]


def config_hash(config: dict[str, Any]) -> str:
    """SHA-256 of the config in a fixed form (sorted keys, no spaces).

    The same settings always give the same hash, whatever order they
    were written in.
    """
    canonical = json.dumps(config, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class RunRecord(_Strict):
    schema_version: Literal[1, 2] = SCHEMA_VERSION
    run_id: str
    instance_id: str
    patch_source: str  # "gold", "empty", "noop", or "agent:NAME" from Week 2
    model: str | None = None
    seed: int | None = None
    config: dict[str, Any]
    config_hash: str
    prompt_hashes: dict[str, str] = {}  # role -> SHA-256 of its prompt file
    patch: str
    outcome: Outcome
    tests: SuiteResults | None  # None when the tests never ran
    usage: Usage = Usage()
    timing: Timing
    transcript: list[dict[str, Any]] = []  # model messages, from Week 2
    harness_log: str | None = None
    error: str | None = None
    breach: Breach | None = None  # schema 2: set iff a limit stopped the job
    environment: Environment

    @model_validator(mode="after")
    def _check_consistency(self) -> RunRecord:
        if self.config_hash != config_hash(self.config):
            raise ValueError("config_hash does not match config")

        ran = self.outcome in (Outcome.RESOLVED, Outcome.UNRESOLVED)
        if ran and self.tests is None:
            raise ValueError(f"outcome {self.outcome.value} needs test results")

        if self.outcome is Outcome.RESOLVED:
            # The definition fixed in results.md, enforced in code.
            t = self.tests
            if t.fail_to_pass_failed or t.pass_to_pass_failed or not t.fail_to_pass_passed:
                raise ValueError("resolved requires every FAIL_TO_PASS and "
                                 "PASS_TO_PASS test to pass")

        if self.outcome is Outcome.EMPTY_PATCH and self.patch.strip():
            raise ValueError("empty_patch outcome with a non-empty patch")

        if self.schema_version >= 2:
            limited = self.outcome in (Outcome.SPEND_CEILING, Outcome.WALL_CLOCK_LIMIT)
            if limited != (self.breach is not None):
                raise ValueError("breach must be set exactly when a limit stopped the job")
            if self.breach is not None:
                wall = self.breach.limit == "wall_clock_s"
                if wall != (self.outcome is Outcome.WALL_CLOCK_LIMIT):
                    raise ValueError(f"breach {self.breach.limit} does not match "
                                     f"outcome {self.outcome.value}")
            u = self.usage
            if u.cached_input_tokens + u.cache_miss_input_tokens != u.input_tokens:
                raise ValueError("usage: cached + cache-miss input != input tokens")
            if u.reasoning_tokens > u.output_tokens:
                raise ValueError("usage: reasoning tokens exceed output tokens")
        return self


def write_record(record: RunRecord, root: Path) -> Path:
    """Write to root/RUN_ID/INSTANCE_ID.json. Never overwrites.

    Atomic: the JSON goes to a temporary file first and is then renamed
    into place, so a crash mid-write can never leave a half-written or
    zero-filled record.
    """
    path = Path(root) / record.run_id / f"{record.instance_id}.json"
    if path.exists():
        raise FileExistsError(f"record already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(record.model_dump_json(indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return path


def read_record(path: Path) -> RunRecord:
    """Load and re-validate a record."""
    return RunRecord.model_validate_json(Path(path).read_text(encoding="utf-8"))
