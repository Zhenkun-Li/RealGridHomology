from __future__ import annotations

import argparse
import json
import sys

from .stages.hat_homology import HAT_METHOD_AUTO, HAT_METHOD_DENSE, HAT_METHOD_LOW_MEMORY
from .workflow import available_knots, run_workflow


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m real_grid_homology",
        description="Run the RealGridHomology workflow on a bundled knot dataset.",
    )
    parser.add_argument(
        "knot",
        nargs="?",
        default="3_1",
        help="Knot identifier from data/knots (default: 3_1).",
    )
    parser.add_argument(
        "--mode",
        choices=["overwrite", "skip", "delete"],
        default="overwrite",
        help="How to treat existing generated outputs.",
    )
    parser.add_argument(
        "--hat-method",
        choices=[HAT_METHOD_AUTO, HAT_METHOD_DENSE, HAT_METHOD_LOW_MEMORY],
        default=HAT_METHOD_AUTO,
        help="Hat homology computation strategy.",
    )
    parser.add_argument(
        "--check-diff",
        action="store_true",
        help="Verify differential consistency during homology computations.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the workflow summary as JSON.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List bundled knot templates and exit.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list:
        for knot_name in available_knots():
            print(knot_name)
        return 0

    progress_callback = None if args.json else print
    try:
        summary = run_workflow(
            args.knot,
            mode=args.mode,
            check_diff=args.check_diff,
            hat_method=args.hat_method,
            progress_callback=progress_callback,
        )
    except FileNotFoundError as exc:
        available = ", ".join(available_knots()) or "<none>"
        parser.error(f"{exc} Available bundled knots: {available}")
        return 2

    if args.json:
        json.dump(summary, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
