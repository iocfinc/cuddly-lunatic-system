#!/usr/bin/env python3
"""Send local Codex and hook notifications through Telegram."""

from __future__ import annotations

import argparse
import json
import mimetypes
import pathlib
import re
import sys
import uuid
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
SECRET_KEYS = ("TOKEN", "KEY", "SECRET", "PASSWORD")
PRIVATE_CHANNEL_PREFIX = "-100"
MAX_EVENT_TEXT_LENGTH = 700


class TelegramSendError(Exception):
    """Raised when Telegram rejects a notification request."""


def load_env(path: pathlib.Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def redact(text: str, env: dict[str, str]) -> str:
    redacted = text
    for key, value in env.items():
        if not value or not any(marker in key.upper() for marker in SECRET_KEYS):
            continue
        redacted = redacted.replace(value, f"<redacted:{key}>")
    return redacted


def stdin_payload() -> str:
    if sys.stdin.isatty():
        return ""
    return sys.stdin.read().strip()


def truncate_text(text: str, limit: int = MAX_EVENT_TEXT_LENGTH) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 1].rstrip()}..."


def html_line(label: str, value: object) -> str:
    return f"<b>{html_escape(label)}:</b> {html_escape(value)}"


def html_escape(value: object) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def format_codex_event(data: dict[str, object]) -> str | None:
    event_type = str(data.get("type", "")).strip()
    if not event_type:
        return None

    title_by_type = {
        "agent-turn-complete": "✅ Agent Turn Complete",
        "agent-turn-start": "🚀 Agent Turn Started",
        "task-started": "🚀 Task Started",
        "task-complete": "✅ Task Complete",
        "error": "🚨 Codex Error",
    }
    title = title_by_type.get(event_type, f"🤖 Codex Event · {event_type.replace('-', ' ').title()}")
    lines = [f"<b>{html_escape(title)}</b>"]

    cwd = data.get("cwd")
    if cwd:
        lines.append(html_line("Repo", pathlib.Path(str(cwd)).name))
    client = data.get("client")
    if client:
        lines.append(html_line("Client", client))
    turn_id = data.get("turn-id") or data.get("turn_id")
    if turn_id:
        lines.append(html_line("Turn", str(turn_id)[:12]))

    input_messages = data.get("input-messages") or data.get("input_messages")
    if isinstance(input_messages, list) and input_messages:
        latest = str(input_messages[-1])
        lines.extend(["", f"📝 <b>Prompt</b>\n{html_escape(truncate_text(latest))}"])
    elif data.get("message"):
        lines.extend(["", html_escape(truncate_text(str(data["message"])))])

    return "\n".join(lines)


def normalize_message(cli_parts: list[str], stdin_text: str) -> str:
    raw_text = " ".join(cli_parts).strip() if cli_parts else stdin_text
    if not raw_text:
        return ""
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        return raw_text
    if isinstance(data, dict):
        event_message = format_codex_event(data)
        if event_message:
            return event_message
        for key in ("message", "text", "summary", "title"):
            if key in data and data[key]:
                return str(data[key])
        return json.dumps(data, sort_keys=True)
    return str(data)


def chat_id_hint(chat_id: str) -> str:
    if not chat_id:
        return "Set TELEGRAM_CHAT_ID in .env."
    if chat_id.startswith(("https://t.me/", "http://t.me/", "t.me/")):
        return (
            "Telegram invite links cannot be used as chat_id values. Add the bot "
            "as a channel admin, then set TELEGRAM_CHAT_ID to the channel's "
            "numeric -100... id."
        )
    if chat_id.startswith("@") or chat_id.startswith(PRIVATE_CHANNEL_PREFIX):
        return "Confirm the bot is a member of the chat and has permission to post."
    if re.fullmatch(r"-?\d+", chat_id):
        return "Private channel ids usually start with -100. Confirm the full numeric chat id."
    return (
        "Telegram does not accept a private channel display name. Use a public "
        "@channel_username, or add the bot as a channel admin and set the numeric "
        "private channel id that starts with -100."
    )


def post_telegram(token: str, chat_id: str, message: str, parse_mode: str = "") -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    body = urllib.parse.urlencode(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            response.read()
    except urllib.error.HTTPError as exc:
        raw_body = exc.read().decode("utf-8", errors="replace")
        description = raw_body
        try:
            body = json.loads(raw_body)
        except json.JSONDecodeError:
            body = {}
        if isinstance(body, dict) and body.get("description"):
            description = str(body["description"])
        raise TelegramSendError(f"{description}. {chat_id_hint(chat_id)}") from exc


def _raise_telegram_error(exc: urllib.error.HTTPError, chat_id: str) -> None:
    raw_body = exc.read().decode("utf-8", errors="replace")
    description = raw_body
    try:
        body = json.loads(raw_body)
    except json.JSONDecodeError:
        body = {}
    if isinstance(body, dict) and body.get("description"):
        description = str(body["description"])
    raise TelegramSendError(f"{description}. {chat_id_hint(chat_id)}") from exc


def _multipart_form_data(fields: dict[str, str], files: dict[str, pathlib.Path]) -> tuple[bytes, str]:
    boundary = f"----quant-researcher-desk-{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                str(value).encode("utf-8"),
                b"\r\n",
            ]
        )
    for name, path in files.items():
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                (
                    f'Content-Disposition: form-data; name="{name}"; '
                    f'filename="{path.name}"\r\n'
                ).encode("utf-8"),
                f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
                path.read_bytes(),
                b"\r\n",
            ]
        )
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), boundary


def post_telegram_document(
    token: str,
    chat_id: str,
    document_path: str | pathlib.Path,
    caption: str = "",
    parse_mode: str = "",
) -> None:
    path = pathlib.Path(document_path)
    if not path.is_file():
        raise TelegramSendError(f"Telegram document does not exist: {path}")

    url = f"https://api.telegram.org/bot{token}/sendDocument"
    fields = {"chat_id": chat_id}
    if caption:
        fields["caption"] = caption
    if parse_mode:
        fields["parse_mode"] = parse_mode
    body, boundary = _multipart_form_data(fields, {"document": path})
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            response.read()
    except urllib.error.HTTPError as exc:
        _raise_telegram_error(exc, chat_id)


def post_telegram_photo(
    token: str,
    chat_id: str,
    photo_path: str | pathlib.Path,
    caption: str = "",
    parse_mode: str = "",
) -> None:
    path = pathlib.Path(photo_path)
    if not path.is_file():
        raise TelegramSendError(f"Telegram photo does not exist: {path}")

    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    fields = {"chat_id": chat_id}
    if caption:
        fields["caption"] = caption
    if parse_mode:
        fields["parse_mode"] = parse_mode
    body, boundary = _multipart_form_data(fields, {"photo": path})
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            response.read()
    except urllib.error.HTTPError as exc:
        _raise_telegram_error(exc, chat_id)


def main() -> int:
    parser = argparse.ArgumentParser(description="Send a Telegram notification.")
    parser.add_argument("--dry-run", action="store_true", help="Print the redacted message without posting.")
    parser.add_argument("--post", action="store_true", help="Post when TELEGRAM_NOTIFY_ENABLED=true.")
    parser.add_argument(
        "--parse-mode",
        choices=("HTML", "Markdown", "MarkdownV2"),
        default="",
        help="Optional Telegram parse_mode for formatted messages.",
    )
    parser.add_argument("--document", type=pathlib.Path, help="Attach a local file with Telegram sendDocument.")
    parser.add_argument("--photo", type=pathlib.Path, help="Attach a local image with Telegram sendPhoto.")
    parser.add_argument("message", nargs="*", help="Message text. If omitted, stdin is used.")
    args = parser.parse_args()

    env = load_env(ROOT / ".env.example")
    env.update(load_env(ROOT / ".env"))
    message = normalize_message(args.message, stdin_payload())
    if not message:
        message = "Quant Researcher Desk notification"
    message = redact(message, env)
    parse_mode = args.parse_mode or ("HTML" if message.startswith("<b>") else "")

    if args.dry_run or not args.post:
        if args.photo:
            print(f"telegram dry-run photo: {args.photo} caption: {message}")
            return 0
        if args.document:
            print(f"telegram dry-run document: {args.document} caption: {message}")
            return 0
        print(f"telegram dry-run: {message}")
        return 0

    token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = env.get("TELEGRAM_CHAT_ID", "")
    if env.get("TELEGRAM_NOTIFY_ENABLED", "false").lower() != "true":
        print("telegram notification skipped: TELEGRAM_NOTIFY_ENABLED is not true")
        return 0
    if not token or token.startswith("replace-with-") or not chat_id or chat_id.startswith("replace-with-"):
        print("telegram notification skipped: Telegram credentials are not configured", file=sys.stderr)
        return 1

    try:
        if args.photo:
            post_telegram_photo(token, chat_id, args.photo, message, parse_mode)
        elif args.document:
            post_telegram_document(token, chat_id, args.document, message, parse_mode)
        else:
            post_telegram(token, chat_id, message, parse_mode)
    except TelegramSendError as exc:
        print(f"telegram notification failed: {exc}", file=sys.stderr)
        return 1
    except (TimeoutError, urllib.error.URLError) as exc:
        print(f"telegram notification failed: {exc}", file=sys.stderr)
        return 1
    print("telegram notification sent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
