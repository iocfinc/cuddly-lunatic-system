from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.telegram_notify import (  # noqa: E402
    MAX_TELEGRAM_CAPTION_LENGTH,
    TelegramSendError,
    validate_attachment_path,
    validate_caption,
    validate_parse_mode,
)


def test_telegram_caption_rejects_oversized_payload() -> None:
    with pytest.raises(TelegramSendError, match="caption is too long"):
        validate_caption("x" * (MAX_TELEGRAM_CAPTION_LENGTH + 1))


def test_telegram_parse_mode_rejects_unsupported_value() -> None:
    with pytest.raises(TelegramSendError, match="Unsupported Telegram parse_mode"):
        validate_parse_mode("HTML<script>")


def test_telegram_photo_rejects_unsupported_file_type(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "preview.txt"
    path.write_text("not an image", encoding="utf-8")

    with pytest.raises(TelegramSendError, match="unsupported file type"):
        validate_attachment_path(path, photo=True)


def test_telegram_document_rejects_empty_file(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "empty.pdf"
    path.write_bytes(b"")

    with pytest.raises(TelegramSendError, match="is empty"):
        validate_attachment_path(path)
