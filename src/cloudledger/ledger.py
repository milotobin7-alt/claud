"""Aggregation over a collection of line items."""

from __future__ import annotations

import csv
from collections import defaultdict
from collections.abc import Iterable, Iterator
from datetime import date
from pathlib import Path
from statistics import mean, pstdev

from cloudledger.models import Budget, LineItem, ParseError


class Ledger:
    """An in-memory collection of :class:`LineItem` with grouping helpers."""

    def __init__(self, items: Iterable[LineItem] = ()) -> None:
        self._items: list[LineItem] = list(items)

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[LineItem]:
        return iter(self._items)

    @classmethod
    def from_csv(cls, path: str | Path, *, strict: bool = True) -> Ledger:
        """Load a usage export.

        With ``strict=False`` unparseable rows are dropped instead of raising,
        which is what you want against a vendor export you do not control.
        """
        items: list[LineItem] = []
        with Path(path).open(newline="", encoding="utf-8") as handle:
            for lineno, row in enumerate(csv.DictReader(handle), start=2):
                try:
                    items.append(LineItem.from_row(row))
                except ParseError as exc:
                    if strict:
                        raise ParseError(f"{path}:{lineno}: {exc}") from exc
        return cls(items)

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

        return Ledger(item for item in self._items if keep(item))

    def by_team(self) -> dict[str, int]:
        return self._group(lambda item: item.team)

    def by_service(self) -> dict[str, int]:
        return self._group(lambda item: item.service)

    def by_day(self) -> dict[date, int]:
        """Daily totals, ascending by date, with no gaps left implicit."""
        grouped = self._group(lambda item: item.day)
        return dict(sorted(grouped.items()))

    def _group(self, key) -> dict:
        totals: dict = defaultdict(int)
        for item in self._items:
            totals[key(item)] += item.cents
        return dict(totals)

    def over_budget(self, budgets: Iterable[Budget]) -> dict[str, float]:
        """Teams whose spend exceeds their budget, mapped to utilization."""
        spend = self.by_team()
        return {
            budget.name: budget.utilization(spend.get(budget.name, 0))
            for budget in budgets
            if spend.get(budget.name, 0) > budget.monthly_cents
        }

    def anomalies(self, *, sigma: float = 2.0) -> list[tuple[date, int]]:
        """Days whose total sits more than ``sigma`` deviations above the mean.

        Needs at least three days of history; with fewer, the deviation is not
        meaningful and the result is empty rather than noisy.
        """
        daily = self.by_day()
        if len(daily) < 3:
            return []
        values = list(daily.values())
        spread = pstdev(values)
        if spread == 0:
            return []
        cutoff = mean(values) + sigma * spread
        return [(day, total) for day, total in daily.items() if total > cutoff]
