import argparse
import json

import pytest

from cloudledger.cli import main

CSV = """date,service,team,amount_usd
2026-09-01,compute,platform,10.00
2026-09-02,compute,platform,10.00
2026-09-03,storage,data,5.00
"""


@pytest.fixture
def usage(tmp_path):
    path = tmp_path / "usage.csv"
    path.write_text(CSV, encoding="utf-8")
    return str(path)


def test_report_json(usage, capsys):
    assert main(["report", usage, "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["total_usd"] == 25.0
    assert payload["by_team"] == {"data": 5.0, "platform": 20.0}


def test_report_flags_a_breached_budget(usage, capsys):
    assert main(["report", usage, "--json", "--budget", "platform=15"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert "platform" in payload["over_budget"]


def test_forecast_json(usage, capsys):
    assert main(["forecast", usage, "--json", "--as-of", "2026-09-03"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["spent_usd"] == 25.0
    assert payload["days_remaining"] == 27


def test_human_output_is_not_json(usage, capsys):
    assert main(["report", usage]) == 0
    assert "total usd: 25.0" in capsys.readouterr().out


def test_missing_file_exits_nonzero(tmp_path, capsys):
    assert main(["report", str(tmp_path / "nope.csv")]) == 1
    assert "cloudledger:" in capsys.readouterr().err


def test_bad_row_exits_nonzero_unless_lenient(tmp_path, capsys):
    path = tmp_path / "bad.csv"
    path.write_text(CSV + "2026-09-04,compute,platform,oops\n", encoding="utf-8")
    assert main(["report", str(path)]) == 1
    capsys.readouterr()
    assert main(["report", str(path), "--lenient", "--json"]) == 0


def test_budget_argument_must_be_name_equals_amount(usage):
    with pytest.raises(SystemExit):
        main(["report", usage, "--budget", "platform"])


def test_team_filter_narrows_the_report(usage, capsys):
    assert main(["report", usage, "--json", "--team", "data"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["total_usd"] == 5.0
    assert list(payload["by_team"]) == ["data"]


def test_service_filter_narrows_the_forecast(usage, capsys):
    assert main(["forecast", usage, "--json", "--as-of", "2026-09-03", "--service", "storage"]) == 0
    assert json.loads(capsys.readouterr().out)["spent_usd"] == 5.0


def test_filters_compose(usage, capsys):
    assert main(["report", usage, "--json", "--team", "data", "--service", "compute"]) == 0
    assert json.loads(capsys.readouterr().out)["total_usd"] == 0


MULTI_MONTH = """date,service,team,amount_usd
2026-08-15,compute,platform,1000.00
2026-09-15,compute,platform,1000.00
"""


def test_forecast_scopes_each_budget_to_its_own_team(tmp_path, capsys):
    path = tmp_path / "two-teams.csv"
    path.write_text(
        "date,service,team,amount_usd\n"
        "2026-09-01,compute,platform,100.00\n"
        "2026-09-01,compute,data,900.00\n",
        encoding="utf-8",
    )
    assert (
        main(
            ["forecast", str(path), "--json", "--as-of", "2026-09-01", "--budget", "platform=5000"]
        )
        == 0
    )
    verdict = json.loads(capsys.readouterr().out)["budgets"][0]
    # platform spent $100/day, so it projects $3,000 — under a $5,000 cap. The
    # org-wide projection is $30,000 and would wrongly read as "over".
    assert "under" in verdict


def test_report_refuses_budgets_on_a_multi_month_export(tmp_path, capsys):
    path = tmp_path / "multi.csv"
    path.write_text(MULTI_MONTH, encoding="utf-8")
    assert main(["report", str(path), "--budget", "platform=1500"]) == 1
    assert "spans 2 months" in capsys.readouterr().err


def test_month_flag_narrows_to_one_billing_month(tmp_path, capsys):
    path = tmp_path / "multi.csv"
    path.write_text(MULTI_MONTH, encoding="utf-8")
    assert (
        main(["report", str(path), "--json", "--month", "2026-09", "--budget", "platform=1500"])
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["total_usd"] == 1000.0
    assert payload["over_budget"] == {}


def test_bad_month_is_rejected(usage):
    with pytest.raises(SystemExit):
        main(["report", usage, "--month", "September"])


def test_window_days_must_be_positive(usage):
    with pytest.raises(SystemExit):
        main(["forecast", usage, "--window-days", "0"])


def test_huge_window_days_clamps_instead_of_crashing(usage, capsys):
    assert (
        main(["forecast", usage, "--json", "--as-of", "2026-09-03", "--window-days", "999999"]) == 0
    )
    assert json.loads(capsys.readouterr().out)["spent_usd"] == 25.0


def test_budget_amount_is_parsed_as_decimal(usage):
    from cloudledger.cli import _parse_budget

    # float(1234.565) * 100 rounds to 123456 under banker's rounding.
    assert _parse_budget("platform=1234.565").monthly_cents == 123457


@pytest.mark.parametrize(
    "bad",
    ["platform=", "platform=abc", "platform=nan", "platform=1E+1000000000", "=100", "platform"],
)
def test_bad_budget_values_are_rejected(bad):
    from cloudledger.cli import _parse_budget

    with pytest.raises(argparse.ArgumentTypeError):
        _parse_budget(bad)


def test_large_but_finite_budget_is_accepted():
    from cloudledger.cli import _parse_budget

    # Decimal plus Python's arbitrary-precision ints: no overflow to guard.
    assert _parse_budget("platform=1e400").monthly_cents == 10**402


def test_skipped_rows_are_reported_not_silent(tmp_path, capsys):
    path = tmp_path / "bad.csv"
    path.write_text(CSV + "2026-09-04,compute,platform,oops\n", encoding="utf-8")
    assert main(["report", str(path), "--lenient", "--json"]) == 0
    captured = capsys.readouterr()
    assert "skipped" in captured.err
    assert json.loads(captured.out)["skipped_rows"]
