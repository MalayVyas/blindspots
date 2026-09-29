"""Prices, and the two costs every model call gets (ADR-0013).

billed_usd     what the call actually cost, at the rate in force when it
               started (DeepSeek halves its prices outside peak hours).
reference_usd  the same tokens at one fixed rate (off-peak list price).
               Comparisons use this one, so the time of day a run happened
               to start cannot make a configuration look cheaper.

Prices are copied by hand from the vendor's page and dated. They are not
fetched at run time: a price that can change under a run makes two runs
incomparable. When the vendor changes a price, add a new table version;
never edit an old one, because old records name the version they used.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

# Bump when any price below changes. Recorded with every call.
PRICE_TABLE_VERSION = "deepseek-2026-09-29"

# USD per 1 million tokens.
# [PRIMARY — api-docs.deepseek.com/quick_start/pricing, fetched 2026-09-29]
PEAK = {
    "deepseek-flash":  {"cache_hit": 0.006, "cache_miss": 0.30, "output": 1.20},
    "deepseek-v4-pro": {"cache_hit": 0.044, "cache_miss": 1.32, "output": 3.96},
}
OFF_PEAK = {
    "deepseek-flash":  {"cache_hit": 0.003, "cache_miss": 0.15, "output": 0.60},
    "deepseek-v4-pro": {"cache_hit": 0.022, "cache_miss": 0.66, "output": 1.98},
}

# Peak: 01:00-04:00 and 06:00-10:00 UTC, Monday to Friday [PRIMARY, same page].
# The vendor also exempts Chinese public holidays. We do not model those, so
# on a holiday billed_usd is overstated (safe direction: never understated).
PEAK_HOURS_UTC = ((1, 4), (6, 10))


class UnknownModel(KeyError):
    pass


def is_peak(when: datetime) -> bool:
    """True if a call starting at `when` is billed at peak rates.

    `when` must be timezone-aware. A naive datetime is refused: guessing
    its timezone is exactly how a 10-hour error gets into a cost.
    """
    if when.tzinfo is None:
        raise ValueError("is_peak needs a timezone-aware datetime")
    utc = when.astimezone(timezone.utc)
    if utc.weekday() >= 5:  # Saturday, Sunday
        return False
    return any(start <= utc.hour < end for start, end in PEAK_HOURS_UTC)


@dataclass(frozen=True)
class Cost:
    billed_usd: float
    reference_usd: float
    peak: bool
    price_table_version: str = PRICE_TABLE_VERSION


def _price(table: dict, model: str, hit: int, miss: int, output: int) -> float:
    try:
        p = table[model]
    except KeyError:
        raise UnknownModel(f"no price for model {model!r} in {PRICE_TABLE_VERSION}") from None
    return (hit * p["cache_hit"] + miss * p["cache_miss"] + output * p["output"]) / 1_000_000


def cost_of(model: str, *, cache_hit_tokens: int, cache_miss_tokens: int,
            output_tokens: int, started_at: datetime) -> Cost:
    """Both costs for one call. output_tokens includes any reasoning tokens."""
    peak = is_peak(started_at)
    args = (model, cache_hit_tokens, cache_miss_tokens, output_tokens)
    return Cost(
        billed_usd=_price(PEAK if peak else OFF_PEAK, *args),
        reference_usd=_price(OFF_PEAK, *args),
        peak=peak,
    )


def ceiling_usd(model: str, *, cache_hit_tokens: int, cache_miss_tokens: int,
                output_tokens: int) -> float:
    """Actual tokens at peak price: what the spend ceiling counts (ADR-0014).

    Never below the billed cost, and independent of when the job ran, so
    the same job hits or misses its ceiling whatever the time of day.
    """
    return _price(PEAK, model, cache_hit_tokens, cache_miss_tokens, output_tokens)


def worst_case_usd(model: str, *, input_tokens: int, output_tokens: int) -> float:
    """Upper bound for a call not yet made: every input token a cache miss,
    every output token used, peak rates. The accountant (step 2) uses this
    to refuse a call before it is sent."""
    return _price(PEAK, model, 0, input_tokens, output_tokens)
