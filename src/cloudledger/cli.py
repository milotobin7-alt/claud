"""Command line entry point: ``cloudledger report usage.csv``."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date

from cloudledger.forecast import forecast_month_end
from cloudledger.ledger import Ledger
from cloudledger.models import Budget, ParseError


def _parse_budget(raw: str) -> Budget:
    name, _, amount = raw.partition("=")
    if not name or not amount:
        raise argparse.ArgumentTypeError(f"expected NAME=AMOUNT, got {raw!r}")
    try:
        return Budget(name=name, monthly_cents=round(float(amount) * 100))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


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
        help="treat this date as today (YYYY-MM-DD)",
    )
    parser.add_argument("--window-days", type=int, default=7)
    parser.add_argument("--team", help="restrict the report or forecast to one team")
    parser.add_argument("--service", help="restrict the report or forecast to one service")
    parser.add_argument("--json", action="store_true", help="emit machine-readable output")
    parser.add_argument(
        "--lenient",
        action="store_true",
        help="skip rows that fail to parse instead of exiting",
    )
    return parser


def _report(ledger: Ledger, args: argparse.Namespace) -> dict:
    return {
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


def _forecast(ledger: Ledger, args: argparse.Namespace) -> dict:
    result = forecast_month_end(ledger, as_of=args.as_of, window_days=args.window_days)
    return {
        "as_of": result.as_of.isoformat(),
        "spent_usd": round(result.spent_cents / 100, 2),
        "projected_usd": round(result.projected_cents / 100, 2),
        "daily_run_rate_usd": round(result.daily_run_rate_cents / 100, 2),
        "days_remaining": result.days_remaining,
        "budgets": [result.against(budget) for budget in args.budget],
    }


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

    if args.team or args.service:
        ledger = ledger.filter(team=args.team, service=args.service)

    payload = _report(ledger, args) if args.command == "report" else _forecast(ledger, args)
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        _print_human(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
