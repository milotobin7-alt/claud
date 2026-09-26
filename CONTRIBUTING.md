# Contributing

Thanks for taking a look. This project is small on purpose; the bar for a change is
that it keeps the library dependency-free and the test suite green.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Before you open a pull request

```bash
ruff check . && ruff format --check .
pytest --cov=cloudledger --cov-report=term-missing
```

CI runs exactly these on Python 3.11, 3.12, and 3.13, so a clean local run means a
clean CI run.

## Conventions

- **No runtime dependencies.** The `cloudledger` package imports only the standard
  library. Dev-only tooling belongs in the `dev` extra.
- **Money stays in integer cents.** If you are introducing a float dollar amount
  anywhere outside a display path, there is probably a better way.
- **Every behavior change comes with a test**, including the edge case that motivated
  it — month boundaries, empty windows, and malformed rows are where the bugs live.
- Keep commits focused and write a subject line that says what changed and why.

## Reporting bugs

Open an issue with the CSV shape that triggered it (redacted amounts are fine), the
command you ran, and what you expected instead.
