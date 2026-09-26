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


def test_bom_prefixed_export_still_parses(tmp_path):
    path = tmp_path / "excel.csv"
    path.write_text("﻿" + CSV, encoding="utf-8")
    assert Ledger.from_csv(path).total_cents == 2750


def test_lenient_mode_records_what_it_skipped(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text(CSV + "2026-09-04,compute,platform,oops\n", encoding="utf-8")
    ledger = Ledger.from_csv(path, strict=False)
    assert len(ledger) == 4
    assert len(ledger.skipped) == 1
    assert "bad.csv:6" in ledger.skipped[0]


def test_line_number_survives_a_quoted_multiline_field(tmp_path):
    path = tmp_path / "multiline.csv"
    path.write_text(
        'date,service,team,amount_usd\n2026-09-01,"com\npute",platform,1.00\n'
        "2026-09-02,compute,platform,oops\n",
        encoding="utf-8",
    )
    with pytest.raises(ParseError, match="multiline.csv:4"):
        Ledger.from_csv(path)


def test_credits_reduce_the_total():
    ledger = Ledger(
        [
            LineItem(date(2026, 9, 1), "compute", "platform", 10_000),
            LineItem(date(2026, 9, 1), "credit", "platform", -4_000),
        ]
    )
    assert ledger.total_cents == 6_000


def test_over_budget_refuses_a_multi_month_ledger():
    ledger = Ledger(
        [
            LineItem(date(2026, 8, 1), "compute", "platform", 100_000),
            LineItem(date(2026, 9, 1), "compute", "platform", 100_000),
        ]
    )
    with pytest.raises(ValueError, match="spans 2 months"):
        ledger.over_budget([Budget("platform", 150_000)])


def test_over_budget_accepts_a_single_month(usage):
    ledger = Ledger.from_csv(usage)
    assert ledger.months() == {(2026, 9)}
    assert set(ledger.over_budget([Budget("platform", 1500)])) == {"platform"}


def test_daily_series_fills_gaps_with_zero():
    ledger = Ledger(
        [
            LineItem(date(2026, 9, 1), "compute", "platform", 100),
            LineItem(date(2026, 9, 4), "compute", "platform", 100),
        ]
    )
    assert ledger.daily_series() == {
        date(2026, 9, 1): 100,
        date(2026, 9, 2): 0,
        date(2026, 9, 3): 0,
        date(2026, 9, 4): 100,
    }


def test_anomaly_on_sparse_data_is_not_hidden_by_missing_days():
    # Two quiet days, a gap of nothing, then a 50x spike. Baselining only on
    # days that have rows would raise the mean enough to bury it.
    items = [
        LineItem(date(2026, 9, 1), "compute", "platform", 100),
        LineItem(date(2026, 9, 2), "compute", "platform", 100),
        LineItem(date(2026, 9, 20), "egress", "platform", 5_000),
    ]
    assert Ledger(items).anomalies() == [(date(2026, 9, 20), 5_000)]
