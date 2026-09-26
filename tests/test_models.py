from datetime import date

import pytest

from cloudledger.models import Budget, LineItem, ParseError


def test_from_row_converts_dollars_to_cents():
    item = LineItem.from_row(
        {"date": "2026-09-01", "service": "compute", "team": "platform", "amount_usd": "12.34"}
    )
    assert item == LineItem(date(2026, 9, 1), "compute", "platform", 1234)
    assert item.dollars == 12.34


def test_from_row_tolerates_surrounding_whitespace():
    item = LineItem.from_row(
        {"date": " 2026-09-01 ", "service": " compute ", "team": " data ", "amount_usd": " 1.00 "}
    )
    assert item.service == "compute"
    assert item.team == "data"


def test_from_row_rounds_sub_cent_amounts():
    item = LineItem.from_row(
        {"date": "2026-09-01", "service": "egress", "team": "data", "amount_usd": "0.005"}
    )
    assert item.cents == 1


@pytest.mark.parametrize(
    "row",
    [
        {"service": "compute", "team": "platform", "amount_usd": "1"},
        {"date": "not-a-date", "service": "c", "team": "p", "amount_usd": "1"},
        {"date": "2026-09-01", "service": "c", "team": "p", "amount_usd": "free"},
    ],
)
def test_from_row_rejects_bad_input(row):
    with pytest.raises(ParseError):
        LineItem.from_row(row)


def test_credits_are_kept_as_negative_line_items():
    item = LineItem.from_row(
        {"date": "2026-09-01", "service": "compute", "team": "platform", "amount_usd": "-40.00"}
    )
    assert item.cents == -4000
    assert item.is_credit


def test_half_cent_rounds_away_from_zero_not_to_even():
    def cents(amount):
        return LineItem.from_row(
            {"date": "2026-09-01", "service": "c", "team": "t", "amount_usd": amount}
        ).cents

    # round() would give 0 and 2 here; accounting expects 1 and 3.
    assert cents("0.005") == 1
    assert cents("0.025") == 3


def test_truncated_row_raises_parse_error_not_attribute_error():
    with pytest.raises(ParseError, match="truncated"):
        LineItem.from_row({"date": "2026-09-01", "service": "c", "team": "t", "amount_usd": None})


@pytest.mark.parametrize("amount", ["nan", "Infinity", "-Infinity"])
def test_non_finite_amounts_are_rejected(amount):
    with pytest.raises(ParseError, match="finite"):
        LineItem.from_row({"date": "2026-09-01", "service": "c", "team": "t", "amount_usd": amount})


def test_absurdly_large_amount_raises_parse_error():
    with pytest.raises(ParseError):
        LineItem.from_row(
            {"date": "2026-09-01", "service": "c", "team": "t", "amount_usd": "1E+1000000000"}
        )


def test_budget_utilization():
    budget = Budget("platform", 100_00)
    assert budget.utilization(50_00) == 0.5
    assert budget.utilization(100_00) == 1.0


def test_budget_must_be_positive():
    with pytest.raises(ValueError):
        Budget("platform", 0)
