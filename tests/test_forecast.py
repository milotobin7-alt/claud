from datetime import date, timedelta

import pytest

from cloudledger.forecast import forecast_month_end
from cloudledger.ledger import Ledger
from cloudledger.models import Budget, LineItem


def steady_ledger(days: int, cents_per_day: int) -> Ledger:
    return Ledger(
        LineItem(date(2026, 9, 1) + timedelta(days=offset), "compute", "platform", cents_per_day)
        for offset in range(days)
    )


def test_steady_spend_projects_the_full_month():
    ledger = steady_ledger(10, 100)
    result = forecast_month_end(ledger, as_of=date(2026, 9, 10))
    assert result.days_in_month == 30
    assert result.days_remaining == 20
    assert result.spent_cents == 1000
    assert result.daily_run_rate_cents == 100
    assert result.projected_cents == 3000


def test_trailing_window_ignores_an_early_backfill():
    ledger = steady_ledger(14, 100)
    ledger.add(LineItem(date(2026, 9, 1), "compute", "platform", 50_000))
    result = forecast_month_end(ledger, as_of=date(2026, 9, 14), window_days=7)
    # The spike is outside the window, so the run rate stays at the steady level
    # even though month-to-date spend is dominated by it.
    assert result.daily_run_rate_cents == 100
    assert result.spent_cents == 51_400


def test_window_is_clamped_to_the_start_of_the_month():
    ledger = steady_ledger(3, 100)
    result = forecast_month_end(ledger, as_of=date(2026, 9, 3), window_days=30)
    assert result.daily_run_rate_cents == 100


def test_last_day_of_month_projects_exactly_what_was_spent():
    ledger = steady_ledger(30, 100)
    result = forecast_month_end(ledger, as_of=date(2026, 9, 30))
    assert result.days_remaining == 0
    assert result.projected_cents == result.spent_cents == 3000


def test_prior_month_spend_is_excluded():
    ledger = steady_ledger(5, 100)
    ledger.add(LineItem(date(2026, 8, 30), "compute", "platform", 99_999))
    result = forecast_month_end(ledger, as_of=date(2026, 9, 5))
    assert result.spent_cents == 500


def test_february_leap_year_day_count():
    ledger = Ledger([LineItem(date(2028, 2, 1), "compute", "platform", 100)])
    assert forecast_month_end(ledger, as_of=date(2028, 2, 1)).days_in_month == 29


def test_window_days_must_be_positive():
    with pytest.raises(ValueError):
        forecast_month_end(steady_ledger(3, 100), as_of=date(2026, 9, 3), window_days=0)


def test_verdict_against_budget():
    result = forecast_month_end(steady_ledger(10, 100), as_of=date(2026, 9, 10))
    assert "over" in result.against(Budget("platform", 1000))
    assert "under" in result.against(Budget("platform", 100_00))
