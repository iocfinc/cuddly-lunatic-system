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
