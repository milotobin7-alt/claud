# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
pip install -e ".[dev]"                              # setup; the CLI entry point needs this
pytest                                               # full suite
pytest tests/test_forecast.py                        # one file
pytest tests/test_forecast.py::test_steady_spend_projects_the_full_month   # one test
pytest -k "anomal"                                   # by name pattern
pytest --cov=cloudledger --cov-report=term-missing   # what CI runs
ruff check . && ruff format --check .                # lint + format gate
ruff check --fix . && ruff format .                  # autofix both
cloudledger report examples/usage-2026-09.csv --budget platform=4000
cloudledger forecast examples/usage-2026-09.csv --as-of 2026-09-21 --team platform
```

Without an editable install, run the CLI as `PYTHONPATH=src python -m cloudledger.cli`.
`pyproject.toml` sets `pythonpath = ["src"]` for pytest, so tests run from a bare
checkout, but the `cloudledger` console script does not exist until you install.

CI (`.github/workflows/ci.yml`) runs lint, format check, the suite on Python
3.11/3.12/3.13, and a CLI smoke test against `examples/usage-2026-09.csv`. A clean
local `ruff` + `pytest` means a clean CI run.

## Architecture

A `src/` layout package with no runtime dependencies. Four modules, layered bottom-up —
`models` knows nothing about the others, `cli` is a thin shell over the rest:

- **`models.py`** — `LineItem` (one charge) and `Budget` (a monthly cap), both frozen
  slotted dataclasses that validate in `__post_init__`. `LineItem.from_row` is the only
  CSV-to-object path. `ParseError` subclasses `ValueError`.
- **`ledger.py`** — `Ledger` wraps a list of `LineItem` and is the whole aggregation
  surface: `from_csv`, `filter`, the `by_*` groupers, `over_budget`, `anomalies`.
- **`forecast.py`** — `forecast_month_end` returns a `Forecast`; the only module that
  reasons about calendar months.
- **`cli.py`** — argparse, dict-building `_report`/`_forecast`, and two renderers
  (`--json` or the human printer). Business logic does not belong here.

### Invariants that will bite you

**Money is integer cents everywhere except display.** `LineItem.cents` is an `int`.
Parsing goes through `Decimal(...).scaleb(2).to_integral_value(ROUND_HALF_UP)` — not
`round()`, which is banker's rounding and drifts a ledger low on half-cent charges.
Division to dollars happens only in `dollars`, in `Forecast.against`, and in `cli.py`'s
payload builders. Introducing a float dollar amount anywhere else is a bug.

**`Ledger.filter` returns a new `Ledger`, and both date bounds are inclusive.** Chaining
filters is the intended way to narrow; nothing mutates in place except `add`.

**The forecast is a trailing window, not a month-to-date average.** `window_days`
(default 7) is clamped to the start of the month, and days inside it with no usage count
as zero rather than being skipped — that is deliberate, so one early backfill cannot
inflate the projection for the rest of the month. `test_trailing_window_ignores_an_early_backfill`
pins this.

**`from_csv` is strict by default** and raises `ParseError` tagged with file and line
number. `strict=False` silently drops bad rows; that mode exists for vendor exports and
is what the CLI's `--lenient` sets.

**`anomalies()` returns nothing below three days of history or on zero-variance data**,
by design — not a bug to "fix".

## Conventions

- The `cloudledger` package imports only the standard library. Tooling goes in the
  `dev` extra in `pyproject.toml`.
- Ruff with `select = ["E", "F", "I", "UP", "B", "SIM"]`, line length 100.
- Every behavior change gets a test, including its edge case. Month boundaries, leap
  years, empty windows, and malformed rows are where this code breaks.
- Keep `CHANGELOG.md` current under `## [Unreleased]`.
