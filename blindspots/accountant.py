"""Token accountant and spend ceiling (ADR-0009, ADR-0014).

Every model call in a job goes through one Accountant. It is the only way
agents reach a provider, so no call can bypass the limits.

    acct = Accountant(DeepSeek(), Limits(max_cost_usd=0.10), model="deepseek-flash")
    reply = acct.complete(messages, max_tokens=4096, temperature=0.0, thinking="disabled")

Before a call: the accountant adds the call's worst case to what the job
has used so far. If any total would pass its limit, it raises LimitBreached
and sends nothing.

After a call: it adds the real usage and keeps the full call (request and
response) for the transcript. If a total has passed a limit anyway (a
bound was wrong, or a call overran the clock), it raises LimitBreached;
that call is already paid for and stays in the transcript.

On any breach the job ends. Nothing is retried. The runner turns the
exception into a record with outcome spend_ceiling or wall_clock_limit and
the partial transcript (`acct.transcript()`).
"""

from __future__ import annotations

import json
import time
from typing import Any, Callable, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from blindspots import pricing
from blindspots.providers.base import Completion, ProviderError, reply_message
from blindspots.record import Breach, Usage


class Limits(BaseModel):
    """Per-job limits. Part of the job's config, so part of its config hash.

    max_cost_usd is in peak-price dollars (ADR-0014): the same job hits or
    misses the ceiling whatever the time of day, and real spending can
    never exceed it.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_calls: int = Field(5, ge=1)
    max_input_tokens: int = Field(200_000, ge=1)
    max_output_tokens: int = Field(16_000, ge=1)
    max_wall_clock_s: float = Field(600.0, gt=0)
    max_cost_usd: float = Field(0.10, gt=0)


class LimitBreached(RuntimeError):
    """A job limit was reached. Carries the Breach for the run record."""

    def __init__(self, breach: Breach):
        self.breach = breach
        when = "refused before sending" if breach.before_call else "passed after a call"
        super().__init__(f"{breach.limit}: {breach.would_reach:g} > {breach.allowed:g} ({when})")


class Provider(Protocol):
    """Anything with the adapter's complete() signature (DeepSeek, or a test fake)."""

    def complete(self, messages: list[dict[str, Any]], *, model: str, max_tokens: int,
                 temperature: float, thinking: str, reasoning_effort: str | None = None,
                 timeout_s: float | None = None) -> Completion: ...
    # Providers that take tools also accept tools= and tool_choice=; the
    # accountant passes them only when an agent sends tools (ADR-0018).


class TranscriptMismatch(RuntimeError):
    """An agent's request is not its previous request + previous reply + new
    messages (ADR-0018). Raised before the call is sent: a delta transcript
    could not rebuild such a request, so the attempt must fail loudly."""


def _bytes(text: str | None) -> int:
    return len((text or "").encode("utf-8"))


def prompt_bytes(messages: list[dict[str, Any]],
                 tools: list[dict[str, Any]] | None = None) -> int:
    """Upper bound on the prompt's tokens: its size in UTF-8 bytes.

    A byte-level tokenizer never makes more tokens than bytes [JUDGEMENT —
    not confirmed for DeepSeek's tokenizer; the after-call check below
    catches it if wrong]. Loose: code runs about 3-4 bytes per token
    (results entry #5), so this overestimates roughly 4x.

    Counts content (None as empty), and for tool-using agents the tool calls,
    tool-call IDs and tool schema too (ADR-0014 amendment). For content-only
    messages without tools the count is exactly what it was in Week 2.
    """
    n = 0
    for m in messages:
        n += _bytes(m.get("content"))
        if m.get("tool_calls"):
            n += _bytes(json.dumps(m["tool_calls"]))
        if m.get("tool_call_id"):
            n += _bytes(m["tool_call_id"])
    if tools:
        n += _bytes(json.dumps(tools))
    return n


def rebuild_requests(transcript: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Every request's full message list, from a delta transcript (ADR-0018):
    request n = request n-1 [+ reply n-1, if it was re-sent] + new messages n.
    The accountant checked that identity before each call was sent."""
    out: list[list[dict[str, Any]]] = []
    prev: list[dict[str, Any]] = []
    prev_reply: dict[str, Any] | None = None
    for entry in transcript:
        if "new_messages" not in entry:     # timed_out / refused: never sent in full
            continue
        msgs = prev + ([prev_reply] if entry["reply_resent"] else []) + entry["new_messages"]
        out.append(msgs)
        prev, prev_reply = msgs, reply_message(entry["response"])
    return out


class Accountant:
    def __init__(self, provider: Provider, limits: Limits, *, model: str,
                 clock: Callable[[], float] = time.monotonic,
                 transcript: Literal["full", "delta"] = "full"):
        pricing.worst_case_usd(model, input_tokens=0, output_tokens=0)  # unknown model fails now
        self.provider = provider
        self.limits = limits
        self.model = model
        self._clock = clock          # injectable so tests can fake the passage of time
        self._t0 = clock()           # the job's clock starts when its accountant is made
        self.calls: list[Completion] = []
        self.refused: list[dict[str, Any]] = []  # what was about to be sent when refused
        # Calls our timeout cut off. The server may still bill them [UNVERIFIED],
        # and we never see their usage, so each is booked at its worst case.
        self.timed_out: list[dict[str, Any]] = []
        # "full": every call keeps its whole request (agent:simple, one call).
        # "delta": every call keeps only its new messages; the identity that
        # makes that lossless is checked before each call (ADR-0018).
        self.transcript_mode = transcript
        self._deltas: list[dict[str, Any]] = []   # one per entry in self.calls
        # The previous successful call, for the prefix-aware estimate and the
        # delta check: its messages, tools and reported input tokens.
        self._last: tuple[list[dict[str, Any]], Any, int, dict[str, Any]] | None = None

    # ------------------------------------------------------------- totals

    @property
    def elapsed_s(self) -> float:
        return self._clock() - self._t0

    def usage(self) -> Usage:
        """Totals for the job so far, in the run record's shape."""
        u = [c.usage for c in self.calls]
        return Usage(
            model_calls=len(self.calls),
            input_tokens=sum(x.input_tokens for x in u),
            output_tokens=sum(x.output_tokens for x in u),
            cached_input_tokens=sum(x.cache_hit_tokens for x in u),
            cache_miss_input_tokens=sum(x.cache_miss_tokens for x in u),
            reasoning_tokens=sum(x.reasoning_tokens for x in u),
            cost_usd=sum(c.billed_usd for c in self.calls),
            reference_usd=sum(c.reference_usd for c in self.calls),
            ceiling_usd=(sum(self._ceiling(c) for c in self.calls)
                         + sum(t["worst_case_usd"] for t in self.timed_out)),
        )

    def transcript(self) -> list[dict[str, Any]]:
        """Every call made, in order, as plain JSON; then any refused call.

        In delta mode a call's `request` is replaced by its settings (the body
        without messages) and its new messages; rebuild_requests() gives the
        full requests back."""
        if self.transcript_mode == "full":
            made = [c.model_dump(mode="json") for c in self.calls]
        else:
            made = []
            for c, d in zip(self.calls, self._deltas):
                entry = c.model_dump(mode="json", exclude={"request"})
                entry["request_settings"] = {k: v for k, v in c.request.items()
                                             if k != "messages"}
                made.append({**entry, **d})
        return (made + [{"timed_out": t} for t in self.timed_out]
                + [{"refused": r} for r in self.refused])

    # ------------------------------------------------------------- history

    def _split(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        """Delta mode: check this request against the previous one and return
        what is new. Raises TranscriptMismatch on anything else."""
        if self._last is None:
            return {"resent_messages": 0, "reply_resent": False, "new_messages": messages}
        prev, _, _, prev_reply = self._last
        k = len(prev)
        if messages[:k] != prev:
            raise TranscriptMismatch(
                f"request does not start with the previous request ({k} messages)")
        rest = messages[k:]
        resent = bool(rest) and rest[0].get("role") == "assistant"
        if resent and rest[0] != prev_reply:
            raise TranscriptMismatch("the previous reply was re-sent changed")
        new = rest[1:] if resent else rest
        if any(m.get("role") == "assistant" for m in new):
            raise TranscriptMismatch("an assistant message other than the previous reply")
        return {"resent_messages": k + int(resent), "reply_resent": resent,
                "new_messages": new}

    def estimate_input(self, messages: list[dict[str, Any]],
                       tools: list[dict[str, Any]] | None = None) -> int:
        """Upper bound on this call's input tokens (ADR-0014 amendment).

        If the messages start with exactly the previous call's messages, sent
        with the same tools, that prefix counts as the previous call's
        reported input tokens and only the rest is counted in bytes. Otherwise
        the whole prompt is counted in bytes, as in Week 2."""
        if self._last is not None:
            prev, prev_tools, prev_tokens, _ = self._last
            if prev_tools == tools and messages[:len(prev)] == prev:
                return prev_tokens + prompt_bytes(messages[len(prev):])
        return prompt_bytes(messages, tools)

    def _ceiling(self, c: Completion) -> float:
        return pricing.ceiling_usd(c.model, cache_hit_tokens=c.usage.cache_hit_tokens,
                                   cache_miss_tokens=c.usage.cache_miss_tokens,
                                   output_tokens=c.usage.output_tokens)

    # ------------------------------------------------------------- the call

    def complete(self, messages: list[dict[str, Any]], *, max_tokens: int,
                 temperature: float, thinking: str,
                 reasoning_effort: str | None = None,
                 tools: list[dict[str, Any]] | None = None,
                 tool_choice: str | None = None) -> Completion:
        delta = self._split(messages) if self.transcript_mode == "delta" else None
        L, used = self.limits, self.usage()
        est_in = self.estimate_input(messages, tools)
        worst = pricing.worst_case_usd(self.model, input_tokens=est_in, output_tokens=max_tokens)
        remaining = L.max_wall_clock_s - self.elapsed_s

        # Checked in this order; the first that fails is reported.
        checks = [
            ("wall_clock_s", self.elapsed_s, L.max_wall_clock_s, remaining <= 0),
            ("calls", used.model_calls + 1, L.max_calls, used.model_calls + 1 > L.max_calls),
            ("input_tokens", used.input_tokens + est_in, L.max_input_tokens,
             used.input_tokens + est_in > L.max_input_tokens),
            ("output_tokens", used.output_tokens + max_tokens, L.max_output_tokens,
             used.output_tokens + max_tokens > L.max_output_tokens),
            ("cost_usd", used.ceiling_usd + worst, L.max_cost_usd,
             used.ceiling_usd + worst > L.max_cost_usd),
        ]
        for limit, reach, allowed, failed in checks:
            if failed:
                self.refused.append({"limit": limit, "estimated_input_tokens": est_in,
                                     "max_tokens": max_tokens, "worst_case_usd": worst,
                                     **self._sent(messages, delta)})
                raise LimitBreached(Breach(limit=limit, allowed=allowed,
                                           would_reach=reach, before_call=True))

        with_tools = {} if tools is None else {"tools": tools, "tool_choice": tool_choice}
        try:
            c = self.provider.complete(messages, model=self.model, max_tokens=max_tokens,
                                       temperature=temperature, thinking=thinking,
                                       reasoning_effort=reasoning_effort,
                                       timeout_s=remaining, **with_tools)
        except ProviderError:
            if self.elapsed_s >= L.max_wall_clock_s:
                # The timeout we set fired: this is the clock, not a provider fault.
                self.timed_out.append({"worst_case_usd": worst, "estimated_input_tokens": est_in,
                                       "max_tokens": max_tokens, **self._sent(messages, delta)})
                raise LimitBreached(Breach(limit="wall_clock_s", allowed=L.max_wall_clock_s,
                                           would_reach=self.elapsed_s, before_call=False))
            raise
        self.calls.append(c)
        if delta is not None:
            self._deltas.append(delta)
        self._last = (list(messages), tools, c.usage.input_tokens, reply_message(c.response))
        self._check_after()
        return c

    @staticmethod
    def _sent(messages, delta) -> dict[str, Any]:
        """What a refused or timed-out call was about to send, as recorded."""
        return {"messages": messages} if delta is None else delta

    def _check_after(self) -> None:
        """Totals after a call. Only a wrong bound or a slow call can trip these."""
        L, u = self.limits, self.usage()
        for limit, reach, allowed in [
            ("wall_clock_s", self.elapsed_s, L.max_wall_clock_s),
            ("input_tokens", u.input_tokens, L.max_input_tokens),
            ("output_tokens", u.output_tokens, L.max_output_tokens),
            ("cost_usd", u.ceiling_usd, L.max_cost_usd),
        ]:
            if reach > allowed:
                raise LimitBreached(Breach(limit=limit, allowed=allowed,
                                           would_reach=reach, before_call=False))


def outcome_for(breach: Breach):
    """The run-record outcome for a breach (results.md: both are failures)."""
    from blindspots.record import Outcome
    return Outcome.WALL_CLOCK_LIMIT if breach.limit == "wall_clock_s" else Outcome.SPEND_CEILING
