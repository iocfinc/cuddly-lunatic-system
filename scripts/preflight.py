#!/usr/bin/env python3
"""Local scaffold checks for Quant Researcher Desk."""

from __future__ import annotations

import argparse
import pathlib
import re
import shutil
import subprocess
import sys
from typing import Iterable

ROOT = pathlib.Path(__file__).resolve().parents[1]
PLACEHOLDERS = {
    "",
    "replace-with-telegram-bot-token",
    "replace-with-telegram-chat-id",
}


class CheckFailure(Exception):
    pass


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


def check_python_version() -> None:
    if sys.version_info < (3, 10):
        raise CheckFailure(f"Python 3.10+ required, found {sys.version.split()[0]}")


def check_uv_available() -> None:
    if shutil.which("uv") is None:
        raise CheckFailure("uv is not available on PATH. Install with: brew install uv")


def check_pyproject() -> None:
    path = ROOT / "pyproject.toml"
    if not path.exists():
        raise CheckFailure("pyproject.toml is missing")
    text = path.read_text(encoding="utf-8")
    try:
        import tomllib  # type: ignore[attr-defined]
    except ModuleNotFoundError:
        required_patterns = [
            r"(?m)^\[project\]$",
            r'(?m)^name\s*=\s*"quant-researcher-desk"$',
            r'(?m)^requires-python\s*=\s*">=3\.10"$',
            r"(?m)^\[tool\.uv\]$",
            r"(?m)^package\s*=\s*false$",
        ]
        for pattern in required_patterns:
            if not re.search(pattern, text):
                raise CheckFailure(f"pyproject.toml missing expected pattern: {pattern}")
        return
    data = tomllib.loads(text)
    project = data.get("project", {})
    if project.get("name") != "quant-researcher-desk":
        raise CheckFailure("pyproject.toml project.name must be quant-researcher-desk")
    if project.get("requires-python") != ">=3.10":
        raise CheckFailure("pyproject.toml requires-python must be >=3.10")
    if data.get("tool", {}).get("uv", {}).get("package") is not False:
        raise CheckFailure("pyproject.toml must include tool.uv.package = false")


def check_env_example() -> None:
    env_example = ROOT / ".env.example"
    if not env_example.exists():
        raise CheckFailure(".env.example is missing")
    values = load_env(env_example)
    for key in ("TELEGRAM_NOTIFY_ENABLED", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        if key not in values:
            raise CheckFailure(f".env.example missing {key}")


def check_env_ignored() -> None:
    result = subprocess.run(
        ["git", "check-ignore", ".env"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise CheckFailure(".env is not ignored by git")


def check_telegram_env() -> None:
    values = load_env(ROOT / ".env.example")
    values.update(load_env(ROOT / ".env"))
    enabled = values.get("TELEGRAM_NOTIFY_ENABLED", "false").lower() == "true"
    if not enabled:
        return
    for key in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        if values.get(key, "").strip() in PLACEHOLDERS:
            raise CheckFailure(f"{key} must be set when TELEGRAM_NOTIFY_ENABLED=true")


def readable_files(paths: Iterable[pathlib.Path]) -> None:
    for path in paths:
        if not path.exists():
            raise CheckFailure(f"{path.relative_to(ROOT)} is missing")
        path.read_text(encoding="utf-8")


def check_markdown_readable() -> None:
    readable_files([ROOT / "AGENTS.md", *sorted((ROOT / "internal-notes").glob("*.md"))])


def check_agentic_codex_wiring() -> None:
    path = ROOT / ".codex" / "config.toml"
    if not path.exists():
        raise CheckFailure(".codex/config.toml is missing")
    text = path.read_text(encoding="utf-8")
    expected = [
        "[features]",
        "codex_hooks = true",
        "notify =",
        "scripts/telegram_notify.py",
    ]
    for value in expected:
        if value not in text:
            raise CheckFailure(f".codex/config.toml missing {value!r}")


def run_checks(hook: str) -> list[str]:
    checks = [
        ("python-version", check_python_version),
        ("uv-available", check_uv_available),
        ("pyproject", check_pyproject),
        ("env-example", check_env_example),
        ("env-ignored", check_env_ignored),
        ("telegram-env", check_telegram_env),
        ("markdown-readable", check_markdown_readable),
        ("agentic-codex-wiring", check_agentic_codex_wiring),
    ]
    passed: list[str] = []
    for name, check in checks:
        check()
        passed.append(name)
    return passed


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local scaffold preflight checks.")
    parser.add_argument("--hook", default="manual", choices=["manual", "pre-commit", "pre-push"])
    args = parser.parse_args()

    try:
        passed = run_checks(args.hook)
    except CheckFailure as exc:
        print(f"preflight failed during {args.hook}: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - keep hook diagnostics useful.
        print(f"preflight crashed during {args.hook}: {exc}", file=sys.stderr)
        return 1

    print(f"preflight passed for {args.hook}: {', '.join(passed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
