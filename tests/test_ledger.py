from datetime import date

import pytest

from cloudledger.ledger import Ledger
from cloudledger.models import Budget, LineItem, ParseError

CSV = """date,service,team,amount_usd
2026-09-01,compute,platform,10.00
2026-09-01,storage,data,5.00
2026-09-02,compute,platform,10.00
2026-09-03,egress,growth,2.50
"""


@pytest.fixture
def usage(tmp_path):
    path = tmp_path / "usage.csv"
    path.write_text(CSV, encoding="utf-8")
    return path


def test_from_csv_reads_every_row(usage):
    ledger = Ledger.from_csv(usage)
    assert len(ledger) == 4
    assert ledger.total_cents == 2750


def test_grouping(usage):
    ledger = Ledger.from_csv(usage)
    assert ledger.by_team() == {"platform": 2000, "data": 500, "growth": 250}
    assert ledger.by_service() == {"compute": 2000, "storage": 500, "egress": 250}
    assert ledger.by_day() == {
        date(2026, 9, 1): 1500,
        date(2026, 9, 2): 1000,
        date(2026, 9, 3): 250,
    }


def test_by_day_is_sorted_regardless_of_input_order():
    ledger = Ledger(
        [
            LineItem(date(2026, 9, 3), "compute", "platform", 100),
            LineItem(date(2026, 9, 1), "compute", "platform", 100),
        ]
    )
    assert list(ledger.by_day()) == [date(2026, 9, 1), date(2026, 9, 3)]


def test_filter_is_inclusive_on_both_ends(usage):
    ledger = Ledger.from_csv(usage)
    window = ledger.filter(since=date(2026, 9, 1), until=date(2026, 9, 2))
    assert window.total_cents == 2500
    assert ledger.filter(team="platform").total_cents == 2000
    assert ledger.filter(service="egress").total_cents == 250


def test_strict_mode_reports_the_offending_line(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text(CSV + "2026-09-04,compute,platform,oops\n", encoding="utf-8")
    with pytest.raises(ParseError, match="bad.csv:6"):
        Ledger.from_csv(path)


def test_lenient_mode_drops_bad_rows(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text(CSV + "2026-09-04,compute,platform,oops\n", encoding="utf-8")
    assert len(Ledger.from_csv(path, strict=False)) == 4


def test_over_budget_only_lists_breaches(usage):
    ledger = Ledger.from_csv(usage)
    breaches = ledger.over_budget([Budget("platform", 1500), Budget("data", 10_000)])
    assert set(breaches) == {"platform"}
    assert breaches["platform"] == pytest.approx(2000 / 1500)


def test_over_budget_counts_teams_with_no_spend_as_within_budget(usage):
    ledger = Ledger.from_csv(usage)
    assert ledger.over_budget([Budget("security", 100)]) == {}


def test_anomalies_need_three_days_of_history():
    ledger = Ledger([LineItem(date(2026, 9, 1), "compute", "platform", 100)])
    assert ledger.anomalies() == []


def test_anomalies_flag_the_spike():
    items = [LineItem(date(2026, 9, day), "compute", "platform", 100) for day in range(1, 11)]
    items.append(LineItem(date(2026, 9, 11), "egress", "platform", 10_000))
    flagged = Ledger(items).anomalies()
    assert flagged == [(date(2026, 9, 11), 10_000)]


def test_flat_spend_has_no_anomalies():
    items = [LineItem(date(2026, 9, day), "compute", "platform", 100) for day in range(1, 11)]
    assert Ledger(items).anomalies() == []
