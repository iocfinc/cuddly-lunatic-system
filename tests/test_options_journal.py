from __future__ import annotations

import datetime as dt
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quant_researcher_desk.journal import OptionsJournalStore, entry_from_options_report  # noqa: E402
from quant_researcher_desk.options_research import (  # noqa: E402
    FixtureOptionsResearchProvider,
    OptionsResearchRequest,
    build_options_research_report,
)


def test_options_journal_store_writes_and_reads_entries(tmp_path: pathlib.Path) -> None:
    report = build_options_research_report(
        FixtureOptionsResearchProvider(),
        OptionsResearchRequest(symbol="US.TEST", option_code="US.TEST260515C100000"),
        now=dt.datetime(2026, 4, 28, 9, 30, tzinfo=dt.timezone.utc),
    )
    store = OptionsJournalStore(tmp_path)
    entry = entry_from_options_report(report, tmp_path / "report.html")

    path = store.upsert_entry(entry)
    entries = store.read_entries()

    assert path == tmp_path / "options-journal.json"
    assert len(entries) == 1
    assert entries[0].symbol == "US.TEST"
    assert entries[0].strategy == "Long Call"
    assert entries[0].verdict in {"Research Candidate", "Watchlist", "Reject"}
    assert entries[0].report_path.endswith("report.html")
    assert "Evidence:" in entries[0].thesis


def test_options_journal_store_updates_existing_outcome(tmp_path: pathlib.Path) -> None:
    report = build_options_research_report(
        FixtureOptionsResearchProvider(),
        OptionsResearchRequest(symbol="US.TEST", option_code="US.TEST260515C100000"),
        now=dt.datetime(2026, 4, 28, 9, 30, tzinfo=dt.timezone.utc),
    )
    store = OptionsJournalStore(tmp_path)
    entry = entry_from_options_report(report, tmp_path / "report.html")
    store.upsert_entry(entry)

    store.update_outcome(
        entry.id,
        status="confirmed",
        lesson="Move followed through before theta dominated.",
        underlying_price=104.2,
        option_price=5.1,
        updated_at=dt.datetime(2026, 5, 2, 12, 0, tzinfo=dt.timezone.utc),
    )

    updated = store.read_entries()[0]
    assert updated.outcome is not None
    assert updated.outcome.status == "confirmed"
    assert updated.outcome.underlying_price == pytest.approx(104.2)
    assert updated.outcome.option_price == pytest.approx(5.1)
    assert "theta" in updated.outcome.lesson


def test_options_journal_store_rejects_missing_outcome_entry(tmp_path: pathlib.Path) -> None:
    store = OptionsJournalStore(tmp_path)

    with pytest.raises(KeyError, match="No journal entry found"):
        store.update_outcome("missing", status="inconclusive", lesson="No entry.")
