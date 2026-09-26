"""Command line entry point: ``cloudledger report usage.csv``."""

from __future__ import annotations

import argparse
import calendar
import json
import sys
from datetime import date

from cloudledger.forecast import forecast_month_end
from cloudledger.ledger import Ledger
from cloudledger.models import Budget, ParseError, parse_cents


def _parse_budget(raw: str) -> Budget:
    name, sep, amount = raw.partition("=")
    if not name or not sep or not amount:
        raise argparse.ArgumentTypeError(f"expected NAME=AMOUNT, got {raw!r}")
    try:
        # parse_cents, not float: the same half-up Decimal path the ledger uses,
        # so a budget and the spend it gates round identically.
        return Budget(name=name, monthly_cents=parse_cents(amount, field="budget"))
    except (ParseError, ValueError) as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _parse_month(raw: str) -> tuple[date, date]:
    try:
        first = date.fromisoformat(f"{raw}-01")
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected YYYY-MM, got {raw!r}") from exc
    last_day = calendar.monthrange(first.year, first.month)[1]
    return first, first.replace(day=last_day)


def _positive_int(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected an integer, got {raw!r}") from exc
    if value < 1:
        raise argparse.ArgumentTypeError(f"must be at least 1, got {value}")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cloudledger",
        description="Track cloud spend against budgets and project month-end totals.",
    )
    parser.add_argument("command", choices=["report", "forecast"])
    parser.add_argument("csv", help="usage export with date,service,team,amount_usd columns")
    parser.add_argument(
        "--budget",
        action="append",
        default=[],
        type=_parse_budget,
        metavar="TEAM=USD",
        help="monthly budget for a team; repeatable",
    )
    parser.add_argument(
        "--as-of",
        type=date.fromisoformat,
        default=date.today(),
        help="treat this date as today (YYYY-MM-DD); forecast only",
    )
    parser.add_argument(
        "--month",
        type=_parse_month,
        metavar="YYYY-MM",
        help="restrict to one billing month; required by report when budgets are given "
        "and the export spans several months",
    )
    parser.add_argument(
        "--window-days",
        type=_positive_int,
        default=7,
        help="trailing days used for the run rate; forecast only (default: 7)",
    )
    parser.add_argument("--team", help="restrict the report or forecast to one team")
    parser.add_argument("--service", help="restrict the report or forecast to one service")
    parser.add_argument("--json", action="store_true", help="emit machine-readable output")
    parser.add_argument(
        "--lenient",
        action="store_true",
        help="skip rows that fail to parse instead of exiting; skipped rows are reported",
    )
    return parser


def _report(ledger: Ledger, args: argparse.Namespace) -> dict:
    payload = {
        "line_items": len(ledger),
        "total_usd": round(ledger.total_cents / 100, 2),
        "by_team": {k: round(v / 100, 2) for k, v in sorted(ledger.by_team().items())},
        "by_service": {k: round(v / 100, 2) for k, v in sorted(ledger.by_service().items())},
        "over_budget": {
            name: round(util, 3) for name, util in ledger.over_budget(args.budget).items()
        },
        "anomalies": [
            {"date": day.isoformat(), "usd": round(total / 100, 2)}
            for day, total in ledger.anomalies()
        ],
    }
    if ledger.skipped:
        payload["skipped_rows"] = ledger.skipped
    return payload


def _forecast(ledger: Ledger, args: argparse.Namespace) -> dict:
    result = forecast_month_end(ledger, as_of=args.as_of, window_days=args.window_days)
    narrowed = bool(args.team or args.service)
    verdicts = []
    for budget in args.budget:
        # Scope each budget to its own team unless the caller already narrowed
        # the ledger. Otherwise a per-team cap is judged against org-wide spend
        # and every team looks catastrophically over budget.
        scoped = ledger if narrowed else ledger.filter(team=budget.name)
        scoped_result = forecast_month_end(scoped, as_of=args.as_of, window_days=args.window_days)
        verdicts.append(scoped_result.against(budget))

    payload = {
        "as_of": result.as_of.isoformat(),
        "spent_usd": round(result.spent_cents / 100, 2),
        "projected_usd": round(result.projected_cents / 100, 2),
        "daily_run_rate_usd": round(result.daily_run_rate_cents / 100, 2),
        "days_remaining": result.days_remaining,
        "budgets": verdicts,
    }
    if ledger.skipped:
        payload["skipped_rows"] = ledger.skipped
    return payload


def _print_human(payload: dict) -> None:
    for key, value in payload.items():
        label = key.replace("_", " ")
        if isinstance(value, dict):
            print(f"{label}:")
            for name, amount in value.items():
                print(f"  {name}: {amount}")
        elif isinstance(value, list):
            print(f"{label}:")
            for entry in value:
                print(f"  {entry}")
        else:
            print(f"{label}: {value}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        ledger = Ledger.from_csv(args.csv, strict=not args.lenient)
    except (OSError, ParseError) as exc:
        print(f"cloudledger: {exc}", file=sys.stderr)
        return 1

    if args.month:
        since, until = args.month
        ledger = ledger.filter(since=since, until=until)
    if args.team or args.service:
        ledger = ledger.filter(team=args.team, service=args.service)

    try:
        payload = _report(ledger, args) if args.command == "report" else _forecast(ledger, args)
    except ValueError as exc:
        print(f"cloudledger: {exc}", file=sys.stderr)
        return 1

    for skipped in ledger.skipped:
        print(f"cloudledger: skipped {skipped}", file=sys.stderr)

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        _print_human(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
