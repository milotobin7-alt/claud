# cloudledger

[![CI](https://github.com/milotobin7-alt/claud/actions/workflows/ci.yml/badge.svg)](https://github.com/milotobin7-alt/claud/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Track cloud spend against budgets, catch the day a bill went sideways, and project
where the month lands — from a plain CSV usage export. No agent, no vendor API key,
no dependencies beyond the standard library.

Cloud consoles tell you what you spent. They are worse at telling you, on the 12th,
whether you are on track to blow the month's budget. `cloudledger` answers that from
an export you already have.

## Install

```bash
pip install -e ".[dev]"    # from a checkout
```

Requires Python 3.11 or newer. The library itself has zero runtime dependencies.

## Usage

Point it at a CSV with `date,service,team,amount_usd` columns:

```bash
$ cloudledger report examples/usage-2026-09.csv --budget platform=4000
line items: 252
total usd: 20516.84
by team:
  data: 6631.59
  growth: 6946.82
  platform: 6938.43
by service:
  compute: 10689.4
  egress: 1920.62
  managed-db: 5418.13
  storage: 2488.69
over budget:
  platform: 1.735
anomalies:
  {'date': '2026-09-14', 'usd': 1443.51}
```

That last line is the point of the tool: the 14th cost roughly nine times a normal
day's egress, and nothing in the monthly total would have made that visible.

Project where a team's month ends up:

```bash
$ cloudledger forecast examples/usage-2026-09.csv \
    --as-of 2026-09-21 --team platform --budget platform=9000
as of: 2026-09-21
spent usd: 6938.43
projected usd: 9973.23
daily run rate usd: 337.2
days remaining: 9
budgets:
  platform: projected $9,973.23 vs $9,000.00 budget (111% — over)
```

Add `--json` to either command for machine-readable output, `--lenient` to skip
malformed rows instead of exiting, and `--service` to slice by service.

## As a library

```python
from datetime import date
from cloudledger import Budget, Ledger, forecast_month_end

ledger = Ledger.from_csv("examples/usage-2026-09.csv")

print(ledger.by_service())                      # {'compute': 1068940, ...} in cents
print(ledger.anomalies(sigma=2.0))              # [(date(2026, 9, 14), 144351)]
print(ledger.over_budget([Budget("platform", 400_000)]))

result = forecast_month_end(ledger.filter(team="platform"), as_of=date(2026, 9, 21))
print(result.against(Budget("platform", 900_000)))
```

## Design notes

**Money is integer cents, never floats.** Summing thousands of float dollars drifts;
parsing goes through `Decimal` with half-up rounding so a half-cent charge rounds the
way an accountant expects rather than the way `round()` does.

**The forecast uses a trailing window, not a month-to-date average.** One backfill or
migration on the 2nd otherwise poisons the projection for the remaining 28 days. The
window defaults to 7 days and is clamped to the start of the month. Days inside the
window with no usage count as zero — a quiet Sunday is real data, not a gap.

**Anomaly detection is deliberately boring.** A day is flagged when it sits more than
`sigma` population deviations above the mean. With fewer than three days of history,
or with perfectly flat spend, it reports nothing rather than inventing signal.

**Strict by default when reading.** `Ledger.from_csv` raises with the offending file
and line number, because a vendor export that silently lost rows is worse than one
that failed loudly. Pass `strict=False` when you genuinely want best-effort parsing.

## Development

```bash
pip install -e ".[dev]"
pytest                      # 38 tests
ruff check . && ruff format --check .
```

CI runs the suite on Python 3.11, 3.12, and 3.13, lints, and smoke-tests the CLI
against the bundled example export on every push and pull request.

## Roadmap

- Native AWS Cost and Usage Report / GCP billing export column mappings
- Commitment coverage (reserved instances, savings plans) against on-demand spend
- Alerting hook that exits non-zero when a projection breaches a budget, for CI use

## License

MIT — see [LICENSE](LICENSE).
