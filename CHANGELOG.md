# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- Truncated rows, non-finite amounts (`nan`/`Infinity`), and out-of-range exponents now
  raise `ParseError` instead of escaping as `AttributeError`/`Overflow`, so they honor
  line-number tagging, `--lenient`, and the CLI's exit-1 path.
- `forecast --budget` scopes each budget to its own team instead of comparing a team cap
  against the org-wide projection.
- `over_budget` refuses a ledger spanning several months rather than reporting a breach
  against a monthly cap.
- `anomalies()` baselines on a zero-filled daily series, so spikes on sparse data are no
  longer hidden by absent days.
- CSV files are read as `utf-8-sig`; a BOM from Excel no longer drops every row.
- Parse errors report the physical line number, correct across quoted multi-line fields.
- `--window-days` is validated by the parser, and a very large value clamps to the start
  of the month instead of overflowing.
- CLI budget amounts parse through the same half-up `Decimal` path as line items.

### Added

- `--month YYYY-MM` to narrow a multi-month export to one billing month.
- Negative line items (credits, refunds, committed-use discounts) are now kept rather
  than rejected; `LineItem.is_credit` identifies them.
- `Ledger.skipped` records what `--lenient` dropped; the CLI reports it on stderr and in
  the JSON payload.
- `Ledger.daily_series()` and `Ledger.months()`.

## [0.1.0] - 2026-09-26

### Added

- `Ledger` with CSV loading (strict and lenient), filtering by team, service, and
  date range, and grouping by team, service, and day.
- Budget tracking via `Budget` and `Ledger.over_budget`.
- Standard-deviation anomaly detection over daily totals.
- `forecast_month_end` projecting month-end spend from a trailing usage window.
- `cloudledger` CLI with `report` and `forecast` commands, JSON output, and
  `--team` / `--service` filters.
- CI across Python 3.11–3.13 with lint, tests, and a CLI smoke test.
