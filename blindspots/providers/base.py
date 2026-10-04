"""The result type every provider adapter returns.

One shape for every vendor means the accountant, the run record and the
agents never need to know which API answered.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, model_validator


class ProviderError(RuntimeError):
    """The call failed, or its answer cannot be trusted. Never retried here.

    ADR-0009: a failure aborts the job and is written down. Retrying hides
    cost and turns one bad call into several.
    """


class TokenUsage(BaseModel):
    """Token counts for one call, as the vendor reported them.

    input_tokens = cache_hit_tokens + cache_miss_tokens, checked on build.
    output_tokens is the number the vendor bills as output, reasoning included.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    input_tokens: int
    cache_hit_tokens: int
    cache_miss_tokens: int
    output_tokens: int
    reasoning_tokens: int = 0

    @model_validator(mode="after")
    def _check(self) -> TokenUsage:
        for name, value in self.model_dump().items():
            if value < 0:
                raise ValueError(f"{name} is negative: {value}")
        if self.cache_hit_tokens + self.cache_miss_tokens != self.input_tokens:
            raise ValueError(
                f"cache hit ({self.cache_hit_tokens}) + miss ({self.cache_miss_tokens}) "
                f"!= input ({self.input_tokens})")
        if self.reasoning_tokens > self.output_tokens:
            raise ValueError(
                f"reasoning ({self.reasoning_tokens}) > output ({self.output_tokens}); "
                "output is assumed to include reasoning")
        return self


class Completion(BaseModel):
    """One model call, everything needed to cost it, audit it and replay it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: Literal["deepseek"]
    model: str                      # what we asked for
    response_model: str | None      # what the vendor says answered
    content: str
    reasoning_content: str | None   # thinking-mode text, if any
    finish_reason: str | None       # "length" means max_tokens cut it off
    usage: TokenUsage
    billed_usd: float
    reference_usd: float
    peak: bool
    price_table_version: str
    started_at: datetime
    latency_s: float
    request: dict[str, Any]         # the exact body sent (no credentials)
    response: dict[str, Any]        # the exact JSON received

    @property
    def truncated(self) -> bool:
        return self.finish_reason == "length"


def reply_message(response: dict[str, Any]) -> dict[str, Any]:
    """The assistant message an agent sends back as history, built from the
    raw response (ADR-0018).

    One definition, used both by agents that re-send their history and by the
    accountant that checks they re-sent it unchanged; two copies could drift
    and make that check fail, or pass, for the wrong reason. Keys are fixed:
    role, content (None when the reply is only tool calls, as the API returns
    it) and tool_calls only when there are any.
    """
    message = response["choices"][0]["message"]
    out: dict[str, Any] = {"role": "assistant", "content": message.get("content")}
    if message.get("tool_calls"):
        out["tool_calls"] = message["tool_calls"]
    return out
