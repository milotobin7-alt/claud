"""Core value types for cloud spend records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation


class ParseError(ValueError):
    """Raised when a usage record cannot be turned into a LineItem."""


@dataclass(frozen=True, slots=True)
class LineItem:
    """A single cloud usage charge.

    Amounts are stored in whole cents to keep aggregation exact; float dollars
    accumulate rounding error fast once a ledger holds tens of thousands of rows.
    """

    day: date
    service: str
    team: str
    cents: int

    def __post_init__(self) -> None:
        if not self.service:
            raise ParseError("service must not be empty")
        if not self.team:
            raise ParseError("team must not be empty")
        if self.cents < 0:
            raise ParseError(f"cents must not be negative, got {self.cents}")

    @property
    def dollars(self) -> float:
        return self.cents / 100

    @classmethod
    def from_row(cls, row: dict[str, str]) -> LineItem:
        """Build a LineItem from a CSV row with date/service/team/amount_usd keys."""
        missing = {"date", "service", "team", "amount_usd"} - row.keys()
        if missing:
            raise ParseError(f"row is missing columns: {', '.join(sorted(missing))}")
        try:
            day = date.fromisoformat(row["date"].strip())
        except ValueError as exc:
            raise ParseError(f"bad date {row['date']!r}: {exc}") from exc
        try:
            # Decimal, not float: round() is banker's rounding, so a half-cent
            # charge would round to even and a ledger of them would drift low.
            amount = Decimal(row["amount_usd"].strip())
        except InvalidOperation as exc:
            raise ParseError(f"bad amount {row['amount_usd']!r}: not a number") from exc
        cents = int(amount.scaleb(2).to_integral_value(rounding=ROUND_HALF_UP))
        return cls(
            day=day,
            service=row["service"].strip(),
            team=row["team"].strip(),
            cents=cents,
        )


@dataclass(frozen=True, slots=True)
class Budget:
    """A monthly spend cap for one dimension value (a team or a service)."""

    name: str
    monthly_cents: int

    def __post_init__(self) -> None:
        if self.monthly_cents <= 0:
            raise ValueError(f"budget for {self.name!r} must be positive")

    def utilization(self, spent_cents: int) -> float:
        """Fraction of the budget consumed. 1.0 means exactly on budget."""
        return spent_cents / self.monthly_cents
