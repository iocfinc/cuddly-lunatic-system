from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from quant_researcher_desk.weekly_options_screener import FixtureWeeklyScreenProvider, WeeklyScreenRequest, build_weekly_options_screen  # noqa: E402
from quant_researcher_desk.weekly_screen_journal import (  # noqa: E402
    WeeklyOptionAgentReviewConfig,
    WeeklyOptionAgentReviewError,
    WeeklyOptionAgentReviewResult,
    _request_single_option_review,
    build_weekly_screen_journal_payloads,
    request_weekly_option_reviews,
    select_weekly_screen_options_for_agent_review,
)
from test_notion_trade_journal import TRADE_JOURNAL_SCHEMA, _FakeNotionClient, _sync_config  # noqa: E402
from quant_researcher_desk.notion_trade_journal import sync_payloads  # noqa: E402


def _build_weekly_result(top_n: int = 6):
    now = dt.datetime(2026, 5, 26, 9, 30, tzinfo=dt.timezone.utc)
    return build_weekly_options_screen(
        FixtureWeeklyScreenProvider(anchor_date=now.date()),
        WeeklyScreenRequest(market="US", top_n=top_n, historical_volatility=0.22),
        now=now,
    )


def _fake_review(option_code: str, symbol: str) -> WeeklyOptionAgentReviewResult:
    return WeeklyOptionAgentReviewResult(
        option_code=option_code,
        symbol=symbol,
        model_used="gpt-5.5",
        review_disposition="follow_up",
        summary=f"{symbol} needs follow-up.",
        why_this_contract="Screen quality and alignment are good enough for deeper review.",
        main_risks=("Liquidity can change quickly.", "Event timing still needs confirmation."),
        invalidation="Lose stock-context alignment or see liquidity collapse.",
        follow_up_checks=("Refresh quotes.", "Check spreads before human review."),
    )


def test_select_weekly_screen_options_for_agent_review_uses_stable_top_five() -> None:
    result = _build_weekly_result(top_n=6)

    selected = select_weekly_screen_options_for_agent_review(result, top_k=5)

    assert len(selected) == 5
    assert [rank for rank, _ in selected] == [1, 2, 3, 4, 5]
    assert [option.option_code for _, option in selected] == [option.option_code for option in result.ranked_options[:5]]


def test_request_weekly_option_reviews_keeps_partial_failures(monkeypatch) -> None:
    result = _build_weekly_result(top_n=5)

    def fake_single_review(result, option, rank, config):  # type: ignore[no-untyped-def]
        if rank == 3:
            raise WeeklyOptionAgentReviewError(f"codex exec failed for {option.option_code}: model unavailable")
        return _fake_review(option.option_code, option.symbol)

    monkeypatch.setattr("quant_researcher_desk.weekly_screen_journal._request_single_option_review", fake_single_review)

    reviews, failures = request_weekly_option_reviews(
        result,
        WeeklyOptionAgentReviewConfig(enabled=True, top_k=5, concurrency=3),
    )

    assert len(reviews) == 4
    assert len(failures) == 1
    failed_option = result.ranked_options[2].option_code
    assert failed_option in failures


def test_single_option_review_raises_on_non_json_output(monkeypatch) -> None:
    result = _build_weekly_result(top_n=1)
    option = result.ranked_options[0]

    def fake_run(cmd, input, text, capture_output, check, cwd, env, timeout):  # type: ignore[no-untyped-def]
        output_index = cmd.index("-o") + 1
        pathlib.Path(cmd[output_index]).write_text("not-json", encoding="utf-8")
        return None

    monkeypatch.setattr("quant_researcher_desk.weekly_screen_journal.subprocess.run", fake_run)

    try:
        _request_single_option_review(
            result,
            option,
            1,
            WeeklyOptionAgentReviewConfig(enabled=True, top_k=1),
        )
    except WeeklyOptionAgentReviewError as exc:
        assert "non-JSON output" in str(exc)
    else:
        raise AssertionError("Expected WeeklyOptionAgentReviewError for non-JSON output")


def test_build_weekly_screen_journal_payloads_creates_one_run_and_top_five_option_pages() -> None:
    result = _build_weekly_result(top_n=6)
    reviews = {
        option.option_code: _fake_review(option.option_code, option.symbol)
        for option in result.ranked_options[:5]
    }

    payloads = build_weekly_screen_journal_payloads(
        result,
        review_results=reviews,
        review_failures={},
        run_path=pathlib.Path("/tmp/weekly-options"),
        artifact_paths=("csv: /tmp/weekly-options/run.csv", "json: /tmp/weekly-options/run.json"),
        top_k=5,
    )

    assert len(payloads) == 6
    assert payloads[0].entry_type == "Weekly Screen Run"
    assert any(
        block.get("heading_2", {}).get("rich_text", [{}])[0].get("text", {}).get("content") == "Gate Trace"
        for block in payloads[0].blocks
    )
    assert payloads[1].entry_type == "Weekly Screen Option"
    assert payloads[1].blocks[0]["heading_2"]["rich_text"][0]["text"]["content"] == "Stock Context"


def test_weekly_screen_journal_payloads_sync_idempotently_with_mocked_notion_client() -> None:
    client = _FakeNotionClient(schema=TRADE_JOURNAL_SCHEMA)
    result = _build_weekly_result(top_n=6)
    reviews = {
        option.option_code: _fake_review(option.option_code, option.symbol)
        for option in result.ranked_options[:5]
    }
    payloads = build_weekly_screen_journal_payloads(
        result,
        review_results=reviews,
        review_failures={},
        run_path=pathlib.Path("/tmp/weekly-options"),
        artifact_paths=("csv: /tmp/weekly-options/run.csv",),
        top_k=5,
    )

    first_results = sync_payloads(client, _sync_config(dry_run=False), payloads)
    second_results = sync_payloads(client, _sync_config(dry_run=False), payloads)

    assert len(first_results) == 6
    assert len(second_results) == 6
    assert all(result.action == "created" for result in first_results)
    assert all(result.action == "updated" for result in second_results)
    assert len(client.pages_store) == 6
