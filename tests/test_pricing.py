from datetime import datetime, timedelta, timezone

import pytest

from blindspots import pricing

UTC = timezone.utc
SYDNEY_AEDT = timezone(timedelta(hours=11))

# 2026-10-05 is a Monday.
@pytest.mark.parametrize("when, peak", [
    (datetime(2026, 10, 5, 0, 59, tzinfo=UTC), False),
    (datetime(2026, 10, 5, 1, 0, tzinfo=UTC), True),    # window opens
    (datetime(2026, 10, 5, 3, 59, tzinfo=UTC), True),
    (datetime(2026, 10, 5, 4, 0, tzinfo=UTC), False),   # window closes
    (datetime(2026, 10, 5, 6, 0, tzinfo=UTC), True),
    (datetime(2026, 10, 5, 9, 59, tzinfo=UTC), True),
    (datetime(2026, 10, 5, 10, 0, tzinfo=UTC), False),
    (datetime(2026, 10, 3, 2, 0, tzinfo=UTC), False),   # Saturday
    (datetime(2026, 10, 4, 7, 0, tzinfo=UTC), False),   # Sunday
])
def test_peak_windows(when, peak):
    assert pricing.is_peak(when) is peak


def test_peak_uses_utc_not_local_clock():
    # 6pm Monday in Sydney (AEDT) is 07:00 UTC Monday: peak.
    assert pricing.is_peak(datetime(2026, 10, 5, 18, 0, tzinfo=SYDNEY_AEDT))
    # 10am Tuesday in Sydney is 23:00 UTC Monday: off-peak.
    assert not pricing.is_peak(datetime(2026, 10, 6, 10, 0, tzinfo=SYDNEY_AEDT))


def test_naive_datetime_refused():
    with pytest.raises(ValueError):
        pricing.is_peak(datetime(2026, 10, 5, 2, 0))


def test_peak_bill_is_double_reference():
    c = pricing.cost_of("deepseek-flash", cache_hit_tokens=1_000_000,
                        cache_miss_tokens=1_000_000, output_tokens=1_000_000,
                        started_at=datetime(2026, 10, 5, 2, 0, tzinfo=UTC))
    assert c.peak
    assert c.reference_usd == pytest.approx(0.003 + 0.15 + 0.60)
    assert c.billed_usd == pytest.approx(2 * c.reference_usd)


def test_off_peak_bill_equals_reference():
    c = pricing.cost_of("deepseek-v4-pro", cache_hit_tokens=500, cache_miss_tokens=1500,
                        output_tokens=200,
                        started_at=datetime(2026, 10, 3, 2, 0, tzinfo=UTC))
    assert c.billed_usd == c.reference_usd
    assert c.reference_usd == pytest.approx((500 * 0.022 + 1500 * 0.66 + 200 * 1.98) / 1e6)


def test_unknown_model_refused():
    with pytest.raises(pricing.UnknownModel):
        pricing.cost_of("deepseek-chat", cache_hit_tokens=0, cache_miss_tokens=1,
                        output_tokens=1, started_at=datetime.now(UTC))


def test_worst_case_is_an_upper_bound():
    worst = pricing.worst_case_usd("deepseek-flash", input_tokens=10_000, output_tokens=2_000)
    for when in (datetime(2026, 10, 5, 2, 0, tzinfo=UTC), datetime(2026, 10, 3, 2, 0, tzinfo=UTC)):
        actual = pricing.cost_of("deepseek-flash", cache_hit_tokens=4_000,
                                 cache_miss_tokens=6_000, output_tokens=2_000, started_at=when)
        assert actual.billed_usd <= worst
