from __future__ import annotations

import json
import pathlib
import subprocess
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from quant_researcher_desk.weekly_screen_journal import WeeklyOptionAgentReviewResult  # noqa: E402
from test_notion_trade_journal import TRADE_JOURNAL_SCHEMA, _FakeNotionClient  # noqa: E402
from scripts import send_weekly_options_packet  # noqa: E402
from scripts import run_weekly_options_screen  # noqa: E402


def run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=True,
    )


def test_weekly_options_screen_script_fixture_writes_csv_json_and_html(tmp_path: pathlib.Path) -> None:
    result = run_script(
        "scripts/run_weekly_options_screen.py",
        "--fixture",
        "--market",
        "US",
        "--top-n",
        "3",
        "--report-format",
        "html",
        "--output-dir",
        str(tmp_path),
    )

    assert result.returncode == 0, result.stderr
    assert "Weekly Options Screen" in result.stdout
    assert "csv:" in result.stdout
    assert "json:" in result.stdout
    assert "html:" in result.stdout
    assert "attempted-symbols:" in result.stdout
    assert "skipped-symbols:" in result.stdout
    assert "gate-stage: universe_discovery:" in result.stdout

    csv_files = list(tmp_path.glob("*-weekly-shortlist.csv"))
    json_files = list(tmp_path.glob("*-weekly-shortlist.json"))
    html_files = list(tmp_path.glob("*-weekly-shortlist.html"))
    assert csv_files and json_files and html_files

    payload = json.loads(json_files[0].read_text(encoding="utf-8"))
    assert payload["market"] == "US"
    assert payload["ranked_options"]
    assert "required_columns" in payload
    assert payload["request"]["analysis_mode"] == "stock-first"
    assert payload["request"]["stock_review"] is True
    assert payload["run_summary"]["attempted_symbols"] >= payload["run_summary"]["successful_symbol_count"]
    assert payload["gate_results"]
    assert payload["gate_summary"]["stage_rows"]
    assert payload["skipped_symbols"]


def test_weekly_options_screen_script_can_review_shortlist_and_emit_reviewer_fields(tmp_path: pathlib.Path) -> None:
    result = run_script(
        "scripts/run_weekly_options_screen.py",
        "--fixture",
        "--market",
        "US",
        "--top-n",
        "3",
        "--shadow-compare",
        "--review-shortlist",
        "--report-format",
        "html",
        "--output-dir",
        str(tmp_path),
    )

    assert result.returncode == 0, result.stderr
    json_files = list(tmp_path.glob("*-weekly-shortlist.json"))
    assert json_files

    payload = json.loads(json_files[0].read_text(encoding="utf-8"))
    assert payload["pricing_engine"] == "legacy"
    assert payload["shadow_compare"] is True
    assert payload["reviewed_shortlist"] is True
    assert payload["review_summary"]
    assert payload["ranked_options"][0]["review_status"] in {"Candidate", "Watch", "Reject", "Needs Human Review"}


def test_weekly_options_screen_script_live_mode_reports_exact_opend_error(tmp_path: pathlib.Path) -> None:
    result = run_script(
        "scripts/run_weekly_options_screen.py",
        "--market",
        "US",
        "--output-dir",
        str(tmp_path),
        "--opend-port",
        "1",
    )

    assert result.returncode == 1
    assert "Cannot connect to OpenD at 127.0.0.1:1. Start and log into OpenD first." in result.stderr


def test_weekly_options_screen_script_dry_run_converts_html_report_to_pdf_attachment(tmp_path: pathlib.Path) -> None:
    result = run_script(
        "scripts/run_weekly_options_screen.py",
        "--fixture",
        "--market",
        "US",
        "--top-n",
        "3",
        "--report-format",
        "html",
        "--dry-run",
        "--output-dir",
        str(tmp_path),
    )

    assert result.returncode == 0, result.stderr
    assert "html:" in result.stdout
    assert "attachment:" in result.stdout

    html_files = list(tmp_path.glob("*-weekly-shortlist.html"))
    pdf_files = list(tmp_path.glob("*-weekly-shortlist.pdf"))
    assert html_files and pdf_files


def test_weekly_options_screen_script_fixture_can_sync_weekly_screen_pages_to_notion(monkeypatch, tmp_path: pathlib.Path) -> None:
    client = _FakeNotionClient(schema=TRADE_JOURNAL_SCHEMA)

    def fake_load_env(_path):  # type: ignore[no-untyped-def]
        return {
            "NOTION_API_TOKEN": "test-token",
            "NOTION_TRADE_JOURNAL_DATABASE_ID": "trade-journal-db",
            "NOTION_TEMPLATE_PAGE_ID": "",
        }

    def fake_reviews(result, config):  # type: ignore[no-untyped-def]
        selected = result.ranked_options[:5]
        reviews = {
            option.option_code: WeeklyOptionAgentReviewResult(
                option_code=option.option_code,
                symbol=option.symbol,
                model_used=config.model,
                review_disposition="follow_up",
                summary=f"{option.symbol} deserves deeper review.",
                why_this_contract="It ranked high on the deterministic screen.",
                main_risks=("Liquidity can move quickly.",),
                invalidation="Lose stock-context alignment.",
                follow_up_checks=("Refresh quotes.",),
            )
            for option in selected
        }
        return reviews, {}

    monkeypatch.setattr(run_weekly_options_screen, "load_env", fake_load_env)
    monkeypatch.setattr(run_weekly_options_screen, "create_notion_client", lambda config: client)
    monkeypatch.setattr(run_weekly_options_screen, "request_weekly_option_reviews", fake_reviews)
    monkeypatch.setattr(
        run_weekly_options_screen.sys,
        "argv",
        [
            "run_weekly_options_screen.py",
            "--fixture",
            "--dry-run",
            "--notion-sync",
            "--option-agent-review",
            "--option-agent-top-k",
            "5",
            "--output-dir",
            str(tmp_path),
        ],
    )

    result = run_weekly_options_screen.main()

    assert result == 0
    assert len(client.pages_store) == 6


def test_weekly_options_screen_script_can_use_process_env_for_notion_sync(monkeypatch, tmp_path: pathlib.Path) -> None:
    client = _FakeNotionClient(schema=TRADE_JOURNAL_SCHEMA)

    def fake_load_env(_path):  # type: ignore[no-untyped-def]
        return {}

    def fake_reviews(result, config):  # type: ignore[no-untyped-def]
        selected = result.ranked_options[:5]
        reviews = {
            option.option_code: WeeklyOptionAgentReviewResult(
                option_code=option.option_code,
                symbol=option.symbol,
                model_used=config.model,
                review_disposition="follow_up",
                summary=f"{option.symbol} deserves deeper review.",
                why_this_contract="It ranked high on the deterministic screen.",
                main_risks=("Liquidity can move quickly.",),
                invalidation="Lose stock-context alignment.",
                follow_up_checks=("Refresh quotes.",),
            )
            for option in selected
        }
        return reviews, {}

    monkeypatch.setattr(run_weekly_options_screen, "load_env", fake_load_env)
    monkeypatch.setattr(run_weekly_options_screen, "create_notion_client", lambda config: client)
    monkeypatch.setattr(run_weekly_options_screen, "request_weekly_option_reviews", fake_reviews)
    monkeypatch.setenv("NOTION_API_TOKEN", "test-token")
    monkeypatch.setenv("NOTION_TRADE_JOURNAL_DATABASE_ID", "trade-journal-db")
    monkeypatch.setenv("NOTION_TEMPLATE_PAGE_ID", "")
    monkeypatch.setattr(
        run_weekly_options_screen.sys,
        "argv",
        [
            "run_weekly_options_screen.py",
            "--fixture",
            "--dry-run",
            "--notion-sync",
            "--option-agent-review",
            "--option-agent-top-k",
            "5",
            "--output-dir",
            str(tmp_path),
        ],
    )

    result = run_weekly_options_screen.main()

    assert result == 0
    assert len(client.pages_store) == 6


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_send_weekly_options_packet_script_fixture_agent_review_dry_run(monkeypatch, tmp_path: pathlib.Path) -> None:
    models: list[str] = []

    def fake_load_env(_path):  # type: ignore[no-untyped-def]
        return {"OPENROUTER_API_KEY": "test-key"}

    def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
        body = json.loads(request.data.decode("utf-8"))
        models.append(body["model"])
        content = json.dumps(
            {
                "synthesis": "Synthesis text",
                "reflection": "Reflection text",
                "deliberation": "Deliberation text",
                "proposed_trading_idea": "No action pending spread review.",
                "top_candidate": {
                    "rank": "1",
                    "symbol": "US.AAPL",
                    "option_code": "US.AAPL260529C210000",
                    "reason": "Best contract in the fixture shortlist.",
                },
                "watchouts": ["Liquidity can still move."],
                "risk_controls": ["Keep this research-only."],
                "follow_up_checks": ["Refresh quotes before human review."],
            }
        )
        return FakeResponse({"choices": [{"message": {"content": content}}]})

    monkeypatch.setattr(send_weekly_options_packet, "load_env", fake_load_env)
    monkeypatch.setattr(
        send_weekly_options_packet.sys,
        "argv",
        [
            "send_weekly_options_packet.py",
            "--fixture",
            "--dry-run",
            "--report-format",
            "html",
            "--output-dir",
            str(tmp_path),
            "--agent-review",
        ],
    )
    monkeypatch.setattr(
        "quant_researcher_desk.weekly_agent_review.urllib.request.urlopen",
        fake_urlopen,
    )

    result = send_weekly_options_packet.main()

    assert result == 0
    assert models == ["deepseek/deepseek-v4-flash"]
    html_files = list(tmp_path.glob("*.html"))
    assert html_files
    html = html_files[0].read_text(encoding="utf-8")
    assert "Agent Review" in html
    assert "Portfolio-Level Synthesis" in html
