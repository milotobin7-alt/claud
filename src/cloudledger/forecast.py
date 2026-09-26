"""Month-end spend projection from a partial month of usage."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

from cloudledger.ledger import Ledger
from cloudledger.models import Budget


@dataclass(frozen=True, slots=True)
class Forecast:
    """A projection of where the month lands if the recent run rate holds."""

    as_of: date
    spent_cents: int
    projected_cents: int
    daily_run_rate_cents: int
    days_elapsed: int
    days_in_month: int

    @property
    def days_remaining(self) -> int:
        return self.days_in_month - self.days_elapsed

    def against(self, budget: Budget) -> str:
        """A one-line verdict for this forecast against a budget."""
        pct = budget.utilization(self.projected_cents) * 100
        verb = "over" if self.projected_cents > budget.monthly_cents else "under"
        return (
            f"{budget.name}: projected ${self.projected_cents / 100:,.2f} "
            f"vs ${budget.monthly_cents / 100:,.2f} budget "
            f"({pct:.0f}% — {verb})"
        )


def forecast_month_end(
    ledger: Ledger,
    *,
    as_of: date,
    window_days: int = 7,
) -> Forecast:
    """Project month-end spend from the trailing ``window_days`` of usage.

    A trailing window rather than a month-to-date average, because a single
    backfill or migration early in the month otherwise drags the projection for
    the rest of it. Days with no usage inside the window count as zero — they
    are real days of low spend, not missing data.
    """
    if window_days < 1:
        raise ValueError(f"window_days must be at least 1, got {window_days}")

    month_start = as_of.replace(day=1)
    days_in_month = calendar.monthrange(as_of.year, as_of.month)[1]
    month = ledger.filter(since=month_start, until=as_of)
    spent = month.total_cents
    days_elapsed = as_of.day

    window_start = max(month_start, as_of.fromordinal(as_of.toordinal() - window_days + 1))
    window_span = (as_of - window_start).days + 1
    window_total = month.filter(since=window_start).total_cents
    run_rate = round(window_total / window_span)

    projected = spent + run_rate * (days_in_month - days_elapsed)
    return Forecast(
        as_of=as_of,
        spent_cents=spent,
        projected_cents=projected,
        daily_run_rate_cents=run_rate,
        days_elapsed=days_elapsed,
        days_in_month=days_in_month,
    )
