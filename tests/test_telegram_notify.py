from __future__ import annotations

import pathlib
import sys
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import telegram_notify  # noqa: E402


class FakeResponse:
    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def read(self) -> bytes:
        return b'{"ok":true}'


def test_normalize_message_reads_text_field_from_json_stdin() -> None:
    assert telegram_notify.normalize_message([], '{"text":"preflight failed"}') == "preflight failed"


def test_normalize_message_formats_codex_hook_event_as_html_update() -> None:
    payload = {
        "type": "agent-turn-complete",
        "turn-id": "019dd4c5-1007-7011-855e-1c6c5606adc7",
        "cwd": "/Users/example/naval-analyst",
        "client": "codex-tui",
        "input-messages": ["Implement the plan and send the report to Telegram."],
    }

    message = telegram_notify.normalize_message([], telegram_notify.json.dumps(payload))

    assert message.startswith("<b>✅ Agent Turn Complete</b>")
    assert "<b>Repo:</b> naval-analyst" in message
    assert "📝 <b>Prompt</b>" in message
    assert "Implement the plan" in message
    assert "input-messages" not in message


def test_normalize_message_formats_codex_hook_event_from_cli_arg() -> None:
    payload = telegram_notify.json.dumps(
        {
            "type": "agent-turn-complete",
            "turn-id": "019dd4e0-bae2-70b2-96f1-4f18286af41a",
            "cwd": "/Users/example/naval-analyst",
            "input-messages": ["Rerun reports."],
        }
    )

    message = telegram_notify.normalize_message([payload], "")

    assert message.startswith("<b>✅ Agent Turn Complete</b>")
    assert "<b>Repo:</b> naval-analyst" in message
    assert "Rerun reports." in message
    assert '"type"' not in message


def test_post_telegram_includes_parse_mode(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
        captured["timeout"] = timeout
        captured["body"] = request.data.decode("utf-8")
        return FakeResponse()

    monkeypatch.setattr(telegram_notify.urllib.request, "urlopen", fake_urlopen)

    telegram_notify.post_telegram("token", "chat", "<b>hello</b>", parse_mode="HTML")

    body = urllib.parse.parse_qs(str(captured["body"]))
    assert captured["timeout"] == 15
    assert body["chat_id"] == ["chat"]
    assert body["text"] == ["<b>hello</b>"]
    assert body["parse_mode"] == ["HTML"]


def test_post_telegram_document_uses_send_document_multipart(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    document_path = tmp_path / "report.html"
    document_path.write_text("<html>report</html>", encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
        captured["timeout"] = timeout
        captured["url"] = request.full_url
        captured["content_type"] = request.headers["Content-type"]
        captured["body"] = request.data
        return FakeResponse()

    monkeypatch.setattr(telegram_notify.urllib.request, "urlopen", fake_urlopen)

    telegram_notify.post_telegram_document(
        "token",
        "chat",
        document_path,
        caption="<b>daily</b>",
        parse_mode="HTML",
    )

    body = captured["body"]
    assert isinstance(body, bytes)
    assert captured["timeout"] == 30
    assert str(captured["url"]).endswith("/sendDocument")
    assert "multipart/form-data" in str(captured["content_type"])
    assert b'name="chat_id"' in body
    assert b"chat" in body
    assert b'name="caption"' in body
    assert b"<b>daily</b>" in body
    assert b'name="parse_mode"' in body
    assert b"HTML" in body
    assert b'name="document"; filename="report.html"' in body
    assert b"<html>report</html>" in body


def test_post_telegram_photo_uses_send_photo_multipart(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    photo_path = tmp_path / "report.png"
    photo_path.write_bytes(b"png-bytes")
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
        captured["timeout"] = timeout
        captured["url"] = request.full_url
        captured["content_type"] = request.headers["Content-type"]
        captured["body"] = request.data
        return FakeResponse()

    monkeypatch.setattr(telegram_notify.urllib.request, "urlopen", fake_urlopen)

    telegram_notify.post_telegram_photo("token", "chat", photo_path, caption="<b>preview</b>", parse_mode="HTML")

    body = captured["body"]
    assert isinstance(body, bytes)
    assert captured["timeout"] == 30
    assert str(captured["url"]).endswith("/sendPhoto")
    assert "multipart/form-data" in str(captured["content_type"])
    assert b'name="caption"' in body
    assert b"<b>preview</b>" in body
    assert b'name="photo"; filename="report.png"' in body
    assert b"png-bytes" in body
