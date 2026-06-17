#!/usr/bin/env python3
"""Update an existing local options journal entry with outcome data."""

from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quant_researcher_desk.journal import OptionsJournalStore, OUTCOME_STATUSES  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Update an options research journal entry outcome.")
    parser.add_argument("--journal-dir", type=pathlib.Path, default=ROOT / "reports" / "journal")
    parser.add_argument("--entry-id", required=True)
    parser.add_argument("--status", choices=sorted(OUTCOME_STATUSES), required=True)
    parser.add_argument("--lesson", required=True)
    parser.add_argument("--underlying-price", type=float)
    parser.add_argument("--option-price", type=float)
    parser.add_argument("--updated-at", help="ISO timestamp. Defaults to now.")
    args = parser.parse_args()

    updated_at = dt.datetime.fromisoformat(args.updated_at) if args.updated_at else None
    store = OptionsJournalStore(args.journal_dir)
    try:
        journal_path = store.update_outcome(
            args.entry_id,
            status=args.status,
            lesson=args.lesson,
            underlying_price=args.underlying_price,
            option_price=args.option_price,
            updated_at=updated_at,
        )
    except (KeyError, ValueError) as exc:
        print(f"options journal update failed: {exc}", file=sys.stderr)
        return 1
    print(f"journal updated: {journal_path}#{args.entry_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
