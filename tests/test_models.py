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


def test_negative_charges_are_rejected():
    with pytest.raises(ParseError):
        LineItem(date(2026, 9, 1), "compute", "platform", -1)


def test_budget_utilization():
    budget = Budget("platform", 100_00)
    assert budget.utilization(50_00) == 0.5
    assert budget.utilization(100_00) == 1.0


def test_budget_must_be_positive():
    with pytest.raises(ValueError):
        Budget("platform", 0)
