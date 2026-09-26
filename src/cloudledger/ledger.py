"""Aggregation over a collection of line items."""

from __future__ import annotations

import csv
from collections import defaultdict
from collections.abc import Iterable, Iterator
from datetime import date, timedelta
from pathlib import Path
from statistics import mean, pstdev

from cloudledger.models import Budget, LineItem, ParseError


class Ledger:
    """An in-memory collection of :class:`LineItem` with grouping helpers."""

    def __init__(self, items: Iterable[LineItem] = (), *, skipped: Iterable[str] = ()) -> None:
        self._items: list[LineItem] = list(items)
        #: Descriptions of rows dropped during a lenient load, so a caller can
        #: report them instead of silently under-counting spend.
        self.skipped: list[str] = list(skipped)

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[LineItem]:
        return iter(self._items)

    @classmethod
    def from_csv(cls, path: str | Path, *, strict: bool = True) -> Ledger:
        """Load a usage export.

        With ``strict=False`` unparseable rows are recorded on
        :attr:`skipped` instead of raising, which is what you want against a
        vendor export you do not control.
        """
        items: list[LineItem] = []
        skipped: list[str] = []
        # utf-8-sig, not utf-8: exports that went through Excel carry a BOM,
        # which would corrupt the first header name and drop every single row.
        with Path(path).open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                try:
                    items.append(LineItem.from_row(row))
                except ParseError as exc:
                    # reader.line_num, not a row counter: a quoted field may
                    # span physical lines, and the file position is what a
                    # human needs to find the bad record.
                    location = f"{path}:{reader.line_num}"
                    if strict:
                        raise ParseError(f"{location}: {exc}") from exc
                    skipped.append(f"{location}: {exc}")
        return cls(items, skipped=skipped)

    def add(self, item: LineItem) -> None:
        self._items.append(item)

    @property
    def total_cents(self) -> int:
        return sum(item.cents for item in self._items)

    def filter(
        self,
        *,
        team: str | None = None,
        service: str | None = None,
        since: date | None = None,
        until: date | None = None,
    ) -> Ledger:
        """Return a new ledger narrowed to the given dimensions (inclusive dates)."""

        def keep(item: LineItem) -> bool:
            return (
                (team is None or item.team == team)
                and (service is None or item.service == service)
                and (since is None or item.day >= since)
                and (until is None or item.day <= until)
            )

        return Ledger((item for item in self._items if keep(item)), skipped=self.skipped)

    def by_team(self) -> dict[str, int]:
        return self._group(lambda item: item.team)

    def by_service(self) -> dict[str, int]:
        return self._group(lambda item: item.service)

    def by_day(self) -> dict[date, int]:
        """Totals for days that have usage, ascending. Days with none are absent.

        Use :meth:`daily_series` when absent days should read as zero.
        """
        grouped = self._group(lambda item: item.day)
        return dict(sorted(grouped.items()))

    def daily_series(self) -> dict[date, int]:
        """Daily totals across the ledger's full span, with gaps filled as zero."""
        totals = self.by_day()
        if not totals:
            return {}
        first, last = min(totals), max(totals)
        days = (first + timedelta(days=offset) for offset in range((last - first).days + 1))
        return {day: totals.get(day, 0) for day in days}

    def _group(self, key) -> dict:
        totals: dict = defaultdict(int)
        for item in self._items:
            totals[key(item)] += item.cents
        return dict(totals)

    def months(self) -> set[tuple[int, int]]:
        """The distinct (year, month) pairs this ledger covers."""
        return {(item.day.year, item.day.month) for item in self._items}

    def over_budget(self, budgets: Iterable[Budget]) -> dict[str, float]:
        """Teams whose spend exceeds their budget, mapped to utilization.

        Raises if the ledger spans more than one month: the caps are monthly,
        so comparing them against a multi-month total reports fake breaches.
        """
        months = self.months()
        if len(months) > 1:
            raise ValueError(
                f"budgets are monthly, but this ledger spans {len(months)} months; "
                "narrow it to a single month first (Ledger.filter or --month)"
            )
        spend = self.by_team()
        return {
            budget.name: budget.utilization(spend.get(budget.name, 0))
            for budget in budgets
            if spend.get(budget.name, 0) > budget.monthly_cents
        }

    def anomalies(self, *, sigma: float = 2.0) -> list[tuple[date, int]]:
        """Days whose total sits more than ``sigma`` deviations above the mean.

        Baselines on :meth:`daily_series`, so quiet days count as the zeros they
        are; excluding them would raise the mean and hide spikes on sparse data.
        Needs at least three days of span — with fewer, the deviation is not
        meaningful and the result is empty rather than noisy.
        """
        daily = self.daily_series()
        if len(daily) < 3:
            return []
        values = list(daily.values())
        spread = pstdev(values)
        if spread == 0:
            return []
        cutoff = mean(values) + sigma * spread
        return [(day, total) for day, total in daily.items() if total > cutoff]
