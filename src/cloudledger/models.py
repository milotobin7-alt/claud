"""Core value types for cloud spend records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, DecimalException, InvalidOperation

REQUIRED_COLUMNS = frozenset({"date", "service", "team", "amount_usd"})


class ParseError(ValueError):
    """Raised when a usage record cannot be turned into a LineItem."""


def parse_cents(raw: str, *, field: str = "amount") -> int:
    """Parse a dollar string into whole cents, rounding halves away from zero.

    Decimal, not float: ``round()`` is banker's rounding, so a half-cent charge
    would round to even and a ledger of them would drift low.
    """
    try:
        amount = Decimal(raw.strip())
    except (InvalidOperation, AttributeError, TypeError) as exc:
        raise ParseError(f"bad {field} {raw!r}: not a number") from exc
    # Decimal("nan") and Decimal("Infinity") parse happily; reject them here
    # rather than letting int() raise something that is not a ParseError.
    if not amount.is_finite():
        raise ParseError(f"bad {field} {raw!r}: must be a finite amount")
    try:
        return int(amount.scaleb(2).to_integral_value(rounding=ROUND_HALF_UP))
    except (DecimalException, OverflowError, ValueError) as exc:
        raise ParseError(f"bad {field} {raw!r}: out of range") from exc


@dataclass(frozen=True, slots=True)
class LineItem:
    """A single cloud usage charge.

    Amounts are whole cents to keep aggregation exact; float dollars accumulate
    rounding error fast once a ledger holds tens of thousands of rows.

    ``cents`` may be negative: credits, refunds, and committed-use discounts
    arrive as negative line items in real AWS CUR and GCP billing exports, and
    dropping them overstates spend.
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

    @property
    def dollars(self) -> float:
        return self.cents / 100

    @property
    def is_credit(self) -> bool:
        return self.cents < 0

    @classmethod
    def from_row(cls, row: dict[str, str | None]) -> LineItem:
        """Build a LineItem from a CSV row with date/service/team/amount_usd keys."""
        missing = REQUIRED_COLUMNS - row.keys()
        if missing:
            raise ParseError(f"row is missing columns: {', '.join(sorted(missing))}")

        values: dict[str, str] = {}
        for column in sorted(REQUIRED_COLUMNS):
            value = row[column]
            # A truncated row makes DictReader hand back None, which would blow
            # up on .strip() as an AttributeError and escape ParseError handling.
            if value is None:
                raise ParseError(f"row is truncated: no value for column {column!r}")
            values[column] = value.strip()

        try:
            day = date.fromisoformat(values["date"])
        except ValueError as exc:
            raise ParseError(f"bad date {values['date']!r}: {exc}") from exc

        return cls(
            day=day,
            service=values["service"],
            team=values["team"],
            cents=parse_cents(values["amount_usd"]),
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
