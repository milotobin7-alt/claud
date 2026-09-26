# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
