"""Local options research journal store."""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import re
from dataclasses import asdict, dataclass
from typing import Any

from quant_researcher_desk.options_research import OptionsResearchReport, analyst_desk_note


JOURNAL_FILENAME = "options-journal.json"
OUTCOME_STATUSES = {"confirmed", "invalidated", "inconclusive"}


@dataclass(frozen=True)
class OptionsOutcome:
    status: str
    updated_at: str
    underlying_price: float | None = None
    option_price: float | None = None
    lesson: str = ""


@dataclass(frozen=True)
class OptionsJournalEntry:
    id: str
    timestamp: str
    symbol: str
    strategy: str
    thesis: str
    risk: str
    verdict: str
    report_path: str
    option_code: str
    outcome: OptionsOutcome | None = None


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", value.strip()).strip("-").lower()


def build_entry_id(report: OptionsResearchReport) -> str:
    generated = report.generated_at.strftime("%Y%m%dT%H%M%S")
    return _slug(f"{generated}-{report.symbol}-{report.contract.code}") or generated


def entry_from_options_report(report: OptionsResearchReport, report_path: pathlib.Path) -> OptionsJournalEntry:
    strategy = report.strategy_candidates[0].name if report.strategy_candidates else f"Long {report.contract.option_type.title()}"
    return OptionsJournalEntry(
        id=build_entry_id(report),
        timestamp=report.generated_at.isoformat(),
        symbol=report.symbol,
        strategy=strategy,
        thesis=analyst_desk_note(report),
        risk=report.risks[0] if report.risks else "No explicit risk recorded.",
        verdict=report.verdict,
        report_path=str(report_path),
        option_code=report.contract.code,
    )


class OptionsJournalStore:
    def __init__(self, output_dir: pathlib.Path, filename: str = JOURNAL_FILENAME) -> None:
        self.output_dir = output_dir
        self.path = output_dir / filename

    def read_entries(self) -> list[OptionsJournalEntry]:
        if not self.path.exists():
            return []
        raw_entries = json.loads(self.path.read_text(encoding="utf-8"))
        entries: list[OptionsJournalEntry] = []
        for raw_entry in raw_entries:
            raw_outcome = raw_entry.get("outcome")
            outcome = OptionsOutcome(**raw_outcome) if isinstance(raw_outcome, dict) else None
            entries.append(
                OptionsJournalEntry(
                    id=str(raw_entry["id"]),
                    timestamp=str(raw_entry["timestamp"]),
                    symbol=str(raw_entry["symbol"]),
                    strategy=str(raw_entry["strategy"]),
                    thesis=str(raw_entry["thesis"]),
                    risk=str(raw_entry["risk"]),
                    verdict=str(raw_entry["verdict"]),
                    report_path=str(raw_entry["report_path"]),
                    option_code=str(raw_entry["option_code"]),
                    outcome=outcome,
                )
            )
        return entries

    def write_entries(self, entries: list[OptionsJournalEntry]) -> pathlib.Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        payload: list[dict[str, Any]] = []
        for entry in entries:
            raw_entry = asdict(entry)
            if entry.outcome is None:
                raw_entry["outcome"] = None
            payload.append(raw_entry)
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return self.path

    def upsert_entry(self, entry: OptionsJournalEntry) -> pathlib.Path:
        entries = [existing for existing in self.read_entries() if existing.id != entry.id]
        entries.append(entry)
        entries.sort(key=lambda item: item.timestamp)
        return self.write_entries(entries)

    def update_outcome(
        self,
        entry_id: str,
        *,
        status: str,
        lesson: str,
        underlying_price: float | None = None,
        option_price: float | None = None,
        updated_at: dt.datetime | None = None,
    ) -> pathlib.Path:
        if status not in OUTCOME_STATUSES:
            allowed = ", ".join(sorted(OUTCOME_STATUSES))
            raise ValueError(f"Unsupported outcome status: {status}. Expected one of: {allowed}.")
        entries = self.read_entries()
        updated_entries: list[OptionsJournalEntry] = []
        matched = False
        timestamp = (updated_at or dt.datetime.now(dt.timezone.utc)).isoformat()
        for entry in entries:
            if entry.id != entry_id:
                updated_entries.append(entry)
                continue
            matched = True
            updated_entries.append(
                OptionsJournalEntry(
                    id=entry.id,
                    timestamp=entry.timestamp,
                    symbol=entry.symbol,
                    strategy=entry.strategy,
                    thesis=entry.thesis,
                    risk=entry.risk,
                    verdict=entry.verdict,
                    report_path=entry.report_path,
                    option_code=entry.option_code,
                    outcome=OptionsOutcome(
                        status=status,
                        updated_at=timestamp,
                        underlying_price=underlying_price,
                        option_price=option_price,
                        lesson=lesson,
                    ),
                )
            )
        if not matched:
            raise KeyError(f"No journal entry found for id: {entry_id}")
        return self.write_entries(updated_entries)
