"""Command line interface.

Usage::

    calc "<expression>"     evaluate, store, and print the result
    calc list [-n N]        show recent calculations, newest first
    calc show <id>          show a single stored calculation
    calc clear --yes        delete all stored calculations

The result is written to stdout on its own line; the "stored as #id"
confirmation goes to stderr so stdout stays script-friendly.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from . import db
from .db import Calculation, StorageError
from .evaluator import ExpressionError, evaluate, format_result

PROG = "calc"

EPILOG = """\
examples:
  calc "2+3*4"        -> 14, stored in the database
  calc "7/2"          -> 3.5
  calc list -n 5      -> five most recent calculations
  calc show 3         -> details of calculation #3
  calc clear --yes    -> delete the whole history
"""

DEFAULT_LIMIT = 20
MAX_EXPRESSION_COLUMN = 48


def _shorten(text: str, width: int) -> str:
    if len(text) <= width:
        return text
    return text[: width - 3] + "..."


def _print_table(records: Sequence[Calculation]) -> None:
    headers = ("ID", "CREATED", "EXPRESSION", "RESULT")
    rows = [
        (
            str(record.id),
            record.created_at,
            _shorten(record.expression, MAX_EXPRESSION_COLUMN),
            record.result,
        )
        for record in records
    ]
    widths = [
        max(len(headers[column]), *(len(row[column]) for row in rows))
        for column in range(len(headers))
    ]

    print("  ".join(header.ljust(widths[i]) for i, header in enumerate(headers)).rstrip())
    print("  ".join("-" * width for width in widths))
    for row in rows:
        print("  ".join(row[i].ljust(widths[i]) for i in range(len(headers))).rstrip())


def _cmd_evaluate(parts: Sequence[str]) -> int:
    # Joining lets `calc 2 + 3` rebuild "2 + 3" from the shell's word splitting.
    expression = " ".join(parts).strip()

    try:
        value = evaluate(expression)
    except ExpressionError as exc:
        print(f"{PROG}: cannot evaluate {expression!r}: {exc}", file=sys.stderr)
        return 1

    result = format_result(value)

    try:
        record = db.save(expression, result)
    except StorageError as exc:
        print(f"{PROG}: computed {result} but could not store it: {exc}", file=sys.stderr)
        return 1

    print(result)
    print(f"stored as #{record.id} at {record.created_at}", file=sys.stderr)
    return 0


def _cmd_list(args: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog=f"{PROG} list", description="List stored calculations.")
    parser.add_argument(
        "-n", "--limit", type=int, default=DEFAULT_LIMIT,
        help=f"how many records to show (default {DEFAULT_LIMIT})",
    )
    parsed = parser.parse_args(list(args))

    if parsed.limit < 1:
        print(f"{PROG}: --limit must be at least 1", file=sys.stderr)
        return 1

    records = db.history(parsed.limit)
    if not records:
        print("no calculations stored yet", file=sys.stderr)
        return 0

    _print_table(records)
    return 0


def _cmd_show(args: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog=f"{PROG} show", description="Show one calculation.")
    parser.add_argument("id", type=int, help="id of the calculation to show")
    parsed = parser.parse_args(list(args))

    record = db.get(parsed.id)
    if record is None:
        print(f"{PROG}: no calculation with id {parsed.id}", file=sys.stderr)
        return 1

    print(f"id:         {record.id}")
    print(f"expression: {record.expression}")
    print(f"result:     {record.result}")
    print(f"created:    {record.created_at}")
    return 0


def _cmd_clear(args: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog=f"{PROG} clear", description="Delete all stored calculations."
    )
    parser.add_argument(
        "-y", "--yes", action="store_true", help="required: confirm the deletion"
    )
    parsed = parser.parse_args(list(args))

    if not parsed.yes:
        print(f"{PROG}: refusing to delete the history without --yes", file=sys.stderr)
        return 1

    removed = db.clear()
    print(f"deleted {removed} calculation(s)")
    return 0


def _dispatch(args: list[str]) -> int:
    command = args[0]
    if command == "list":
        return _cmd_list(args[1:])
    if command == "show":
        return _cmd_show(args[1:])
    if command == "clear":
        return _cmd_clear(args[1:])
    return _cmd_evaluate(args)


def _build_parser() -> argparse.ArgumentParser:
    """Parser used only to render ``--help`` and the usage line.

    Dispatch itself is manual, so that a bare expression can be the common case
    without having to fight argparse over subcommand parsing.
    """
    parser = argparse.ArgumentParser(
        prog=PROG,
        description=(
            "Evaluate an arithmetic expression and store the result in SQLite. "
            "Calculations are evaluated safely: only numeric literals and the "
            "operators + - * / // % ** are accepted."
        ),
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("expression", nargs="*", help="expression to evaluate, e.g. \"2+3*4\"")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    parser = _build_parser()

    if args and args[0] in ("-h", "--help", "help"):
        parser.print_help()
        return 0
    if not args:
        parser.print_usage(sys.stderr)
        print(f"{PROG}: an expression is required", file=sys.stderr)
        return 2

    try:
        return _dispatch(args)
    except StorageError as exc:
        print(f"{PROG}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
