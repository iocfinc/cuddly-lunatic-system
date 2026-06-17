from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys
import urllib.error

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quant_researcher_desk.options_research import FixtureOptionsResearchProvider  # noqa: E402
from quant_researcher_desk.weekly_agent_review import (  # noqa: E402
    WeeklyAgentReviewConfig,
    WeeklyAgentReviewError,
    build_weekly_agent_review_evidence,
    load_weekly_agent_review_config,
    maybe_request_weekly_agent_review,
    request_weekly_agent_review,
)
from quant_researcher_desk.weekly_options_packet import build_weekly_options_packet  # noqa: E402
from quant_researcher_desk.weekly_options_screener import (  # noqa: E402
    FixtureWeeklyScreenProvider,
    WeeklyReviewerConfig,
    WeeklyScreenRequest,
    build_weekly_options_screen,
)


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def build_fixture_packet() -> object:
    now = dt.datetime(2026, 5, 26, 9, 30, tzinfo=dt.timezone.utc)
    weekly = build_weekly_options_screen(
        FixtureWeeklyScreenProvider(anchor_date=now.date()),
        WeeklyScreenRequest(market="US", top_n=3, historical_volatility=0.22, review_shortlist=True),
        now=now,
        reviewer_config=WeeklyReviewerConfig(enabled=False),
    )
    return build_weekly_options_packet(
        weekly,
        FixtureOptionsResearchProvider(anchor_date=now.date()),
        now=now,
        agent_review_config=WeeklyAgentReviewConfig(enabled=False),
    )


def test_load_weekly_agent_review_config_defaults_and_env_overrides() -> None:
    defaults = load_weekly_agent_review_config({})
    assert defaults.enabled is False
    assert defaults.provider == "openrouter"
    assert defaults.model == "deepseek/deepseek-v4-flash"
    assert defaults.fallback_model == "tencent/hy3-preview"
    assert defaults.timeout_seconds == 90
    assert defaults.max_tokens == 1800
    assert defaults.temperature == 0.2
    assert defaults.api_key is None

    overridden = load_weekly_agent_review_config(
        {
            "OPENROUTER_API_KEY": "test-key",
            "WEEKLY_AGENT_REVIEW_ENABLED": "true",
            "WEEKLY_AGENT_REVIEW_PROVIDER": "OPENROUTER",
            "WEEKLY_AGENT_REVIEW_BASE_URL": "https://example.test/v1",
            "WEEKLY_AGENT_REVIEW_MODEL": "model-a",
            "WEEKLY_AGENT_REVIEW_FALLBACK_MODEL": "model-b",
            "WEEKLY_AGENT_REVIEW_TIMEOUT_SECONDS": "45",
            "WEEKLY_AGENT_REVIEW_MAX_TOKENS": "999",
            "WEEKLY_AGENT_REVIEW_TEMPERATURE": "0.7",
        }
    )
    assert overridden.enabled is True
    assert overridden.provider == "openrouter"
    assert overridden.base_url == "https://example.test/v1"
    assert overridden.model == "model-a"
    assert overridden.fallback_model == "model-b"
    assert overridden.timeout_seconds == 45
    assert overridden.max_tokens == 999
    assert overridden.temperature == 0.7
    assert overridden.api_key == "test-key"


def test_request_weekly_agent_review_requires_openrouter_key_when_enabled() -> None:
    packet = build_fixture_packet()

    try:
        request_weekly_agent_review(packet, WeeklyAgentReviewConfig(enabled=True, api_key=None))
    except WeeklyAgentReviewError as exc:
        assert "OPENROUTER_API_KEY" in str(exc)
    else:
        raise AssertionError("Expected WeeklyAgentReviewError")


def test_request_weekly_agent_review_retries_with_fallback_model() -> None:
    packet = build_fixture_packet()
    seen_models: list[str] = []

    def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
        body = json.loads(request.data.decode("utf-8"))
        seen_models.append(body["model"])
        if body["model"] == "primary-model":
            raise urllib.error.URLError("primary down")
        content = json.dumps(
            {
                "synthesis": "Synthesis text",
                "reflection": "Reflection text",
                "deliberation": "Deliberation text",
                "proposed_trading_idea": "No action until liquidity improves.",
                "top_candidate": {
                    "rank": "1",
                    "symbol": "US.AAPL",
                    "option_code": "US.AAPL260529C210000",
                    "reason": "Best blend of liquidity and valuation discipline.",
                },
                "watchouts": ["Liquidity can reprice quickly."],
                "risk_controls": ["Keep it research-only."],
                "follow_up_checks": ["Refresh spread proxies before review."],
            }
        )
        return FakeResponse({"choices": [{"message": {"content": content}}]})

    result = request_weekly_agent_review(
        packet,
        WeeklyAgentReviewConfig(
            enabled=True,
            api_key="test-key",
            model="primary-model",
            fallback_model="fallback-model",
        ),
        urlopen=fake_urlopen,
    )

    assert seen_models == ["primary-model", "fallback-model"]
    assert result.model_used == "fallback-model"
    assert result.fallback_used is True
    assert result.top_candidate["symbol"] == "US.AAPL"
    assert any("primary-model" in warning for warning in result.warnings)


def test_maybe_request_weekly_agent_review_returns_warning_state_on_invalid_json() -> None:
    packet = build_fixture_packet()
    call_count = 0

    def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
        nonlocal call_count
        call_count += 1
        return FakeResponse({"choices": [{"message": {"content": "not-json"}}]})

    result, warnings = maybe_request_weekly_agent_review(
        packet,
        WeeklyAgentReviewConfig(
            enabled=True,
            api_key="test-key",
            model="primary-model",
            fallback_model="fallback-model",
        ),
        urlopen=fake_urlopen,
    )

    assert result is None
    assert call_count == 2
    assert any("primary-model" in warning for warning in warnings)
    assert any("fallback-model" in warning for warning in warnings)


def test_build_weekly_agent_review_evidence_includes_stock_context_fields() -> None:
    packet = build_fixture_packet()

    evidence = build_weekly_agent_review_evidence(packet)

    shortlist_row = evidence["shortlist_context"]["shortlist_table"][0]
    ranked_row = evidence["ranked_evidence"][0]

    assert shortlist_row["trend_regime"] in {"bullish", "bearish"}
    assert shortlist_row["stock_direction"] in {"bullish", "bearish"}
    assert shortlist_row["alignment_status"] == "Aligned"
    assert ranked_row["stock_context"]["trend_regime"] in {"bullish", "bearish"}
    assert ranked_row["stock_context"]["direction"] in {"bullish", "bearish"}
    assert ranked_row["stock_context"]["thesis_summary"]
    assert ranked_row["stock_context"]["invalidation"]
    assert ranked_row["stock_context"]["catalyst_view"]
