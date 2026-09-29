"""DeepSeek chat-completion adapter (Week 2 step 1).

Plain HTTP with httpx rather than the openai SDK or LiteLLM (ADR-0013):

- the SDK retries failed calls by default; ADR-0009 says abort, never retry;
- the exact JSON sent and received goes into the transcript unchanged;
- tests swap the network for `httpx.MockTransport`, so they cost $0.

Nothing is left to a server default. Thinking mode, max_tokens and
temperature are always sent, because each changes cost or behaviour and
must appear in the config hash. (Thinking mode is ON by default at
DeepSeek [PRIMARY — API reference], and its tokens bill as output.)

The API key comes from the DEEPSEEK_API_KEY environment variable only.
It is never an argument, never logged, never written to a record.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any, Literal

import httpx
from pydantic import ValidationError

from blindspots import pricing
from blindspots.providers.base import Completion, ProviderError, TokenUsage

BASE_URL = "https://api.deepseek.com"
MODELS = ("deepseek-flash", "deepseek-v4-pro")  # [PRIMARY — API reference, 2026-09-29]
MAX_OUTPUT_TOKENS = 393_216                      # 384K, the documented ceiling
DEFAULT_TIMEOUT_S = 300.0

Thinking = Literal["disabled", "enabled"]
Effort = Literal["low", "high", "max"]


class DeepSeek:
    def __init__(self, api_key: str | None = None, *, base_url: str = BASE_URL,
                 timeout_s: float = DEFAULT_TIMEOUT_S,
                 transport: httpx.BaseTransport | None = None):
        key = api_key if api_key is not None else os.environ.get("DEEPSEEK_API_KEY")
        if not key:
            raise ProviderError("DEEPSEEK_API_KEY is not set")
        # transport= exists for tests (httpx.MockTransport). Real runs leave it None.
        self._http = httpx.Client(
            base_url=base_url, timeout=timeout_s, transport=transport,
            headers={"Authorization": f"Bearer {key}"})

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> DeepSeek:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ------------------------------------------------------------------ call

    def complete(self, messages: list[dict[str, str]], *, model: str,
                 max_tokens: int, temperature: float, thinking: Thinking,
                 reasoning_effort: Effort | None = None,
                 timeout_s: float | None = None) -> Completion:
        """One call, no retries. Raises ProviderError on anything unexpected.

        timeout_s overrides the client timeout for this call; the accountant
        passes the job's remaining wall-clock. httpx applies it to each phase
        (connect, send, wait for the reply) separately, not to the call as a
        whole, so the caller must still check elapsed time afterwards.
        """
        body = build_request(messages, model=model, max_tokens=max_tokens,
                             temperature=temperature, thinking=thinking,
                             reasoning_effort=reasoning_effort)
        started = datetime.now(timezone.utc)
        t0 = time.monotonic()
        try:
            kwargs = {} if timeout_s is None else {"timeout": timeout_s}
            resp = self._http.post("/chat/completions", json=body, **kwargs)
        except httpx.HTTPError as e:  # timeout, connection refused, DNS ...
            raise ProviderError(f"request failed: {type(e).__name__}: {e}") from e
        latency = time.monotonic() - t0

        if resp.status_code != 200:
            # 402 = balance exhausted, 429 = rate limit [PRIMARY — error-codes page].
            # Either way: stop and report, do not retry.
            raise ProviderError(f"HTTP {resp.status_code}: {resp.text[:500]}")
        try:
            data = resp.json()
        except ValueError as e:
            raise ProviderError(f"response is not JSON: {resp.text[:200]}") from e

        return parse_response(data, request=body, model=model,
                              started_at=started, latency_s=latency)


# ---------------------------------------------------------------- pure helpers
# Kept outside the class so tests can call them with no network at all.

def build_request(messages: list[dict[str, str]], *, model: str, max_tokens: int,
                  temperature: float, thinking: Thinking,
                  reasoning_effort: Effort | None = None) -> dict[str, Any]:
    if model not in MODELS:
        raise ProviderError(f"unknown model {model!r}; expected one of {MODELS}")
    if not 1 <= max_tokens <= MAX_OUTPUT_TOKENS:
        raise ProviderError(f"max_tokens {max_tokens} outside 1..{MAX_OUTPUT_TOKENS}")
    if not 0 <= temperature <= 2:
        raise ProviderError(f"temperature {temperature} outside 0..2")
    if thinking not in ("disabled", "enabled"):
        raise ProviderError(f"thinking must be 'disabled' or 'enabled', got {thinking!r}")
    if reasoning_effort is not None and thinking != "enabled":
        raise ProviderError("reasoning_effort only applies when thinking is enabled")
    if not messages:
        raise ProviderError("no messages")

    thinking_obj: dict[str, Any] = {"type": thinking}
    if reasoning_effort is not None:
        thinking_obj["reasoning_effort"] = reasoning_effort
    return {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "thinking": thinking_obj,
        "stream": False,
    }


def _cache_fields(usage: dict[str, Any]) -> tuple[int, int]:
    """Cache hit and miss counts, from wherever this API version puts them.

    The current reference nests them in usage.prompt_tokens_details; older
    DeepSeek responses put them directly in usage. Accept either, and refuse
    if both are present and disagree, or if neither is present: a missing
    cache field must never be read as "zero cache hits".
    """
    nested = usage.get("prompt_tokens_details") or {}
    found = []
    for where in (usage, nested):
        if "prompt_cache_hit_tokens" in where or "prompt_cache_miss_tokens" in where:
            found.append((where.get("prompt_cache_hit_tokens"),
                          where.get("prompt_cache_miss_tokens")))
    if not found:
        raise ProviderError("response has no prompt_cache_hit/miss_tokens fields")
    if len(found) == 2 and found[0] != found[1]:
        raise ProviderError(f"cache fields disagree: top-level {found[0]}, nested {found[1]}")
    hit, miss = found[0]
    if hit is None or miss is None:
        raise ProviderError(f"only one of the cache fields is present: hit={hit}, miss={miss}")
    return int(hit), int(miss)


def parse_response(data: dict[str, Any], *, request: dict[str, Any], model: str,
                   started_at: datetime, latency_s: float) -> Completion:
    try:
        choice = data["choices"][0]
        message = choice["message"]
        usage = data["usage"]
        prompt_tokens = int(usage["prompt_tokens"])
        completion_tokens = int(usage["completion_tokens"])
    except (KeyError, IndexError, TypeError) as e:
        raise ProviderError(f"unexpected response shape: missing {e}") from e

    hit, miss = _cache_fields(usage)
    reasoning = int((usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0)

    try:
        tokens = TokenUsage(input_tokens=prompt_tokens, cache_hit_tokens=hit,
                            cache_miss_tokens=miss, output_tokens=completion_tokens,
                            reasoning_tokens=reasoning)
    except ValidationError as e:
        # The accounting identity failed. Refuse the whole response.
        raise ProviderError(f"usage fields are inconsistent: {e.errors()[0]['msg']}") from e

    cost = pricing.cost_of(model, cache_hit_tokens=hit, cache_miss_tokens=miss,
                           output_tokens=completion_tokens, started_at=started_at)
    return Completion(
        provider="deepseek",
        model=model,
        response_model=data.get("model"),
        content=message.get("content") or "",
        reasoning_content=message.get("reasoning_content"),
        finish_reason=choice.get("finish_reason"),
        usage=tokens,
        billed_usd=cost.billed_usd,
        reference_usd=cost.reference_usd,
        peak=cost.peak,
        price_table_version=cost.price_table_version,
        started_at=started_at,
        latency_s=latency_s,
        request=request,
        response=data,
    )
