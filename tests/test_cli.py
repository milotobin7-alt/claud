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
