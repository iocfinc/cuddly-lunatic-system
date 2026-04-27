#!/usr/bin/env python3
"""Send local Codex and hook notifications through Telegram."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
SECRET_KEYS = ("TOKEN", "KEY", "SECRET", "PASSWORD")


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


def normalize_message(cli_parts: list[str], stdin_text: str) -> str:
    if cli_parts:
        return " ".join(cli_parts).strip()
    if not stdin_text:
        return ""
    try:
        data = json.loads(stdin_text)
    except json.JSONDecodeError:
        return stdin_text
    if isinstance(data, dict):
        for key in ("message", "text", "summary", "title"):
            if key in data and data[key]:
                return str(data[key])
        return json.dumps(data, sort_keys=True)
    return str(data)


def post_telegram(token: str, chat_id: str, message: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = urllib.parse.urlencode({"chat_id": chat_id, "text": message}).encode("utf-8")
    request = urllib.request.Request(url, data=body, method="POST")
    with urllib.request.urlopen(request, timeout=15) as response:
        response.read()


def main() -> int:
    parser = argparse.ArgumentParser(description="Send a Telegram notification.")
    parser.add_argument("--dry-run", action="store_true", help="Print the redacted message without posting.")
    parser.add_argument("--post", action="store_true", help="Post when TELEGRAM_NOTIFY_ENABLED=true.")
    parser.add_argument("message", nargs="*", help="Message text. If omitted, stdin is used.")
    args = parser.parse_args()

    env = load_env(ROOT / ".env.example")
    env.update(load_env(ROOT / ".env"))
    message = normalize_message(args.message, stdin_payload())
    if not message:
        message = "Quant Researcher Desk notification"
    message = redact(message, env)

    if args.dry_run or not args.post:
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
        post_telegram(token, chat_id, message)
    except (TimeoutError, urllib.error.URLError) as exc:
        print(f"telegram notification failed: {exc}", file=sys.stderr)
        return 1
    print("telegram notification sent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
