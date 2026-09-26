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
All dollar strings — line items *and* CLI budget amounts — go through
`models.parse_cents`, which is `Decimal(...).scaleb(2).to_integral_value(ROUND_HALF_UP)`,
not `round()` (banker's rounding, drifts a ledger low on half-cent charges). Division to
dollars happens only in `dollars`, in `Forecast.against`, and in `cli.py`'s payload
builders. A float dollar amount anywhere else is a bug.

**`cents` may be negative.** Credits and committed-use discounts are negative line items
in real exports. Do not reintroduce a non-negative check.

**Everything that can fail while parsing must raise `ParseError`**, so it flows through
the line-number tagging, `--lenient`, and the CLI's handler. Watch for the cases that
bypass it: `None` values from truncated rows, `Decimal("nan")`/`Decimal("Infinity")`
(which construct fine), and `decimal.Overflow` (a `DecimalException`, *not* an
`InvalidOperation`).

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

**`anomalies()` baselines on `daily_series()`, not `by_day()`.** `by_day` omits days
with no rows; `daily_series` fills them with zero across the ledger's span. Using the
former raises the mean and hides spikes on sparse data. `anomalies()` returning nothing
below three days of span, or on zero-variance data, is by design — not a bug to "fix".

**Budgets are monthly, so `over_budget` raises on a ledger spanning several months**
rather than reporting a fake breach. The CLI's `--month YYYY-MM` is how a caller narrows
one. On `forecast`, each budget is scoped to its own team unless `--team`/`--service`
already narrowed the ledger — otherwise a team cap gets judged against org-wide spend.

**`from_csv` reads `utf-8-sig`** (Excel BOM would corrupt the first header and drop every
row) and reports `reader.line_num`, not a row counter, since quoted fields span lines.

## Conventions

- The `cloudledger` package imports only the standard library. Tooling goes in the
  `dev` extra in `pyproject.toml`.
- Ruff with `select = ["E", "F", "I", "UP", "B", "SIM"]`, line length 100.
- Every behavior change gets a test, including its edge case. Month boundaries, leap
  years, empty windows, and malformed rows are where this code breaks.
- Keep `CHANGELOG.md` current under `## [Unreleased]`.
