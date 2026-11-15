#!/usr/bin/env python3
"""Send one catalyst-driven options screen report to Telegram."""

from __future__ import annotations

import argparse
import datetime as dt
import importlib
import json
import pathlib
import shutil
import shlex
import signal
import socket
import sys
import time
import urllib.error
from dataclasses import dataclass

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from quant_researcher_desk.catalyst_options_screen import (  # noqa: E402
    DEFAULT_CANDIDATES,
    CatalystCandidate,
    FixtureCatalystOptionsProvider,
    build_catalyst_options_screen,
    catalyst_report_sections,
    format_catalyst_telegram_html,
)
from quant_researcher_desk.moomoo_options_report import MoomooOpenDQuoteClient, OptionsReportError, normalize_records  # noqa: E402
from quant_researcher_desk.options_research import EarningsContext  # noqa: E402
from quant_researcher_desk.reporting import render_pdf_report  # noqa: E402
from scripts.telegram_notify import TelegramSendError, load_env, post_telegram_document  # noqa: E402


PROVIDER_GATE_TIMEOUT_SECONDS = 45


@dataclass(frozen=True)
class SourcedCatalystCandidate:
    symbol: str
    company: str
    event_date: str
    catalyst: str
    source_title: str
    source_url: str
    beginner_note: str
    bucket: str


WEEKLY_PRIMARY_CANDIDATES: tuple[SourcedCatalystCandidate, ...] = (
    SourcedCatalystCandidate("US.MNDY", "monday.com", "2026-08-10", "Q2 2026 financial results before the market, with AI work-platform demand in focus.", "monday.com Q2 2026 financial results announcement", "https://ir.monday.com/news-and-events/news-releases/news-details/2026/monday-com-to-Announce-Second-Quarter-2026-Financial-Results-on-Monday-August-10-2026/default.aspx", "Software earnings can gap on growth and margin guidance; avoid low-delta lottery tickets.", "primary"),
    SourcedCatalystCandidate("US.LITE", "Lumentum", "2026-08-11", "Fiscal Q4/FY2026 earnings after market close; optical and photonic AI infrastructure read-through.", "Lumentum Q4/FY2026 reporting date announcement", "https://investor.lumentum.com/financial-news-releases/news-details/2026/Lumentum-Announces-Reporting-Date-for-Fourth-Quarter-and-Fiscal-Year-2026-Results/default.aspx", "Smaller AI hardware names can have wide spreads; liquidity must lead the read.", "primary"),
    SourcedCatalystCandidate("US.AMD", "Advanced Micro Devices", "2026-08-11", "KeyBanc Technology Leadership Forum following Q2 results and AI infrastructure announcements.", "AMD IR calendar", "https://ir.amd.com/news-events/ir-calendar", "Conference catalysts are softer than earnings; require clean liquidity and realistic breakeven.", "primary"),
    SourcedCatalystCandidate("US.AMAT", "Applied Materials", "2026-08-13", "Q3 2026 Applied Materials earnings conference call.", "Applied Materials events calendar", "https://investor.appliedmaterials.com/events", "Semicap options can reprice on AI memory and wafer-equipment commentary.", "primary"),
    SourcedCatalystCandidate("US.HD", "The Home Depot", "2026-08-18", "Q2 2026 earnings release.", "The Home Depot investor relations", "https://ir.homedepot.com/", "Retail earnings contracts need enough volume because spreads can erase a small thesis.", "primary"),
    SourcedCatalystCandidate("US.TGT", "Target", "2026-08-19", "Q2 2026 earnings conference call.", "Target events and presentations", "https://corporate.target.com/investors/events-presentations", "Turnaround reads need both direction and time; premium can be unforgiving after the event.", "primary"),
    SourcedCatalystCandidate("US.LOW", "Lowe's", "2026-08-19", "Q2 2026 earnings conference call, listed as tentative by the company.", "Lowe's events and presentations", "https://corporate.lowes.com/investors/news-events/events-presentations", "Tentative timing means keep sizing conservative even when options liquidity is acceptable.", "primary"),
    SourcedCatalystCandidate("US.TJX", "TJX Companies", "2026-08-19", "Expected Q2 FY2027 earnings release date on the company reporting calendar.", "TJX reporting calendar", "https://www.tjx.com/investors/financial-information/reporting-calendar", "Expected dates can move; the contract still needs a clean exit lane.", "primary"),
    SourcedCatalystCandidate("US.WMT", "Walmart", "2026-08-20", "FY2027 Q2 earnings release and investor call.", "Walmart FY2027 Q2 earnings event", "https://corporate.walmart.com/news/events/fy2027-q2-earnings-release", "Mega-cap retail has deep chains, but the needed move still has to be realistic.", "primary"),
    SourcedCatalystCandidate("US.DE", "Deere", "2026-08-20", "John Deere 3Q earnings call.", "John Deere 3Q earnings call event", "https://investor.deere.com/events/event-details/2026/John-Deere---3Q-Earnings-Call/default.aspx", "Cyclicals can react to guidance and end-market tone; avoid paying for a huge move.", "primary"),
)


WEEKLY_RESERVE_CANDIDATES: tuple[SourcedCatalystCandidate, ...] = (
    SourcedCatalystCandidate("US.NVDA", "NVIDIA", "2026-08-26", "Second-quarter fiscal 2027 results call after results are released.", "NVIDIA Q2 FY2027 results call announcement", "https://investor.nvidia.com/news/press-release-details/2026/NVIDIA-Sets-Conference-Call-for-Second-Quarter-Financial-Results/default.aspx", "Very liquid, but IV can be crowded; prefer readable deltas over cheap far OTM strikes.", "reserve"),
    SourcedCatalystCandidate("US.NTAP", "NetApp", "2026-09-02", "Target date for Q1 FY2027 financial results.", "NetApp financial results webcast note", "https://investors.netapp.com/news/news-details/2026/NetApp-Hosts-Fourth-Quarter-and-Fiscal-Year-2026-Financial-Results-Webcast/default.aspx", "Storage and AI infrastructure read-through is useful, but options depth can thin out.", "reserve"),
    SourcedCatalystCandidate("US.DELL", "Dell Technologies", "2026-09-03", "Fiscal 2027 second-quarter results event.", "Dell Technologies fiscal 2027 Q2 results event", "https://investors.delltechnologies.com/events/event-details/dell-technologies-fiscal-year-2027-second-quarter-results", "AI server demand is the catalyst; avoid contracts that need a heroic gap.", "reserve"),
)


WEEKLY_SOURCED_CANDIDATES = WEEKLY_PRIMARY_CANDIDATES + WEEKLY_RESERVE_CANDIDATES


def write_run_ledger(
    ledger_path: pathlib.Path,
    *,
    status: str,
    mode: str,
    output_dir: pathlib.Path,
    artifact_path: pathlib.Path | None,
    blocker: str | None,
    started_at: dt.datetime,
    evaluated_count: int = 0,
    promoted_count: int = 0,
    refill_count: int = 0,
    reject_count: int = 0,
    unused_reserve_count: int = 0,
    provider_gates: dict[str, str] | None = None,
) -> None:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    finished_at = dt.datetime.now(dt.timezone.utc)
    entry = {
        "timestamp": finished_at.isoformat(),
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "status": status,
        "mode": mode,
        "command_shape": " ".join(shlex.quote(part) for part in sys.argv),
        "argv": sys.argv,
        "output_dir": str(output_dir),
        "artifact_path": str(artifact_path) if artifact_path is not None else None,
        "evaluated_count": evaluated_count,
        "promoted_count": promoted_count,
        "refill_count": refill_count,
        "reject_count": reject_count,
        "unused_reserve_count": unused_reserve_count,
        "blocker": blocker,
        "exact_blocker": blocker,
        "provider_gates": provider_gates or {},
    }
    with ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(f"{json.dumps(entry, sort_keys=True)}\n")


def timestamped_output_path(output_dir: pathlib.Path, now: dt.datetime) -> pathlib.Path:
    return output_dir / f"{now.astimezone().strftime('%Y%m%d-%H%M%S')}-catalyst-options-screen.pdf"


def latest_output_path(output_dir: pathlib.Path) -> pathlib.Path:
    return output_dir / "catalyst-options-screen.pdf"


def sourced_catalyst_candidates(
    sourced: tuple[SourcedCatalystCandidate, ...] = WEEKLY_SOURCED_CANDIDATES,
) -> tuple[CatalystCandidate, ...]:
    return tuple(
        CatalystCandidate(
            item.symbol,
            item.company,
            f"{item.catalyst} Source: {item.source_title}.",
            f"{item.event_date}; source={item.source_url}",
            item.beginner_note,
        )
        for item in sourced
    )


class SourcedCatalystQuoteClient:
    def __init__(self, inner: MoomooOpenDQuoteClient, sourced: tuple[SourcedCatalystCandidate, ...]) -> None:
        self.inner = inner
        self._by_symbol = {item.symbol: item for item in sourced}

    def get_underlying_snapshot(self, symbol: str) -> dict[str, object]:
        return self.inner.get_underlying_snapshot(symbol)

    def get_option_expirations(self, symbol: str) -> list[str]:
        return self.inner.get_option_expirations(symbol)

    def get_option_chain(self, symbol: str, expiry: str) -> list[dict[str, object]]:
        return self.inner.get_option_chain(symbol, expiry)

    def get_market_snapshots(self, codes: list[str]) -> list[dict[str, object]]:
        return self.inner.get_market_snapshots(codes)

    def get_daily_bars(self, symbol: str, count: int = 250) -> list[dict[str, object]]:
        return self.inner.get_daily_bars(symbol, count=count)

    def get_earnings_context(self, symbol: str) -> EarningsContext:
        item = self._by_symbol.get(symbol)
        if item is None:
            return EarningsContext(
                next_date=None,
                phase="unknown",
                summary="No sourced catalyst is attached to this weekly candidate.",
                risk_level="unknown",
                within_holding_window=None,
                source="weekly_sourced_candidates",
            )
        return EarningsContext(
            next_date=item.event_date,
            phase="verified-catalyst",
            summary=f"{item.catalyst} Source: {item.source_title}.",
            risk_level="high" if item.bucket == "primary" else "medium",
            within_holding_window=True,
            source=item.source_url,
        )


def _timeout_handler(signum: int, frame: object) -> None:
    del signum, frame
    raise TimeoutError(f"Moomoo import/provider connection exceeded {PROVIDER_GATE_TIMEOUT_SECONDS} seconds.")


def run_live_provider_gates(host: str, port: int) -> dict[str, str]:
    """Run the required live provider gates in fail-fast order."""

    gates: dict[str, str] = {}
    started = time.monotonic()
    previous_handler = signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(PROVIDER_GATE_TIMEOUT_SECONDS)
    ctx = None
    try:
        try:
            moomoo = importlib.import_module("moomoo")
        except Exception as exc:
            raise OptionsReportError(f"Moomoo Python import failed: {type(exc).__name__}: {exc}") from exc
        gates["python_moomoo_import"] = f"passed; version={getattr(moomoo, '__version__', 'unknown')}"

        try:
            with socket.create_connection((host, port), timeout=2):
                pass
        except OSError as exc:
            raise OptionsReportError(f"Cannot connect to OpenD at {host}:{port}. Start and log into OpenD first.") from exc
        gates["tcp_reachability"] = f"passed; host={host}; port={port}"

        OpenQuoteContext = getattr(moomoo, "OpenQuoteContext")
        ret_ok = getattr(moomoo, "RET_OK")
        try:
            ctx = OpenQuoteContext(host=host, port=port, ai_type=1)
        except TypeError:
            ctx = OpenQuoteContext(host=host, port=port)
        server_version = "unknown"
        if hasattr(ctx, "get_global_state"):
            ret, data = ctx.get_global_state()
            if ret != ret_ok:
                raise OptionsReportError(f"OpenD failed readiness/version gate: {data}")
            rows = normalize_records(data)
            state = rows[0] if rows else {}
            server_version = str(state.get("server_ver") or "unknown")
            program_status = str(state.get("program_status_type") or "")
            if program_status and program_status != "READY":
                raise OptionsReportError(f"OpenD is not ready: {program_status} {state.get('program_status_desc', '')}".strip())
            qot_logined = state.get("qot_logined")
            if qot_logined is False or str(qot_logined).lower() in {"false", "0", "no"}:
                raise OptionsReportError("OpenD quote login is false in get_global_state.")
        gates["opend_readiness_version"] = f"passed; server_ver={server_version}"

        ret, data = ctx.get_market_snapshot(["US.SPY"])
        if ret != ret_ok:
            raise OptionsReportError(f"OpenD failed quote login gate: {data}")
        if not normalize_records(data):
            raise OptionsReportError("OpenD quote login gate returned no US.SPY snapshot rows.")
        gates["quote_login"] = "passed; probe=US.SPY"

        ret, data = ctx.get_option_expiration_date("US.SPY")
        if ret != ret_ok:
            raise OptionsReportError(f"OpenD failed US options entitlement gate: {data}")
        expiration_rows = normalize_records(data)
        expiries = [str(row.get("strike_time") or row.get("expiry") or row.get("expiration_date") or row.get("date") or row.get("time") or "")[:10] for row in expiration_rows]
        today = dt.datetime.now(dt.timezone.utc).date().isoformat()
        expiries = sorted({expiry for expiry in expiries if expiry and expiry >= today})
        if not expiries:
            raise OptionsReportError("OpenD returned no future US.SPY option expirations.")
        gates["us_options_entitlement"] = f"passed; expirations={len(expiries)}"

        expiry = expiries[0]
        ret, data = ctx.get_option_chain("US.SPY", start=expiry, end=expiry)
        if ret != ret_ok:
            raise OptionsReportError(f"OpenD failed static option chain gate for US.SPY {expiry}: {data}")
        chain_rows = normalize_records(data)
        if not chain_rows:
            raise OptionsReportError(f"OpenD returned empty static option chain for US.SPY {expiry}.")
        gates["static_option_chain"] = f"passed; expiry={expiry}; rows={len(chain_rows)}"

        codes = [str(row.get("code") or row.get("stock") or "").strip() for row in chain_rows]
        codes = [code for code in codes if code][:20]
        ret, data = ctx.get_market_snapshot(codes)
        if ret != ret_ok:
            raise OptionsReportError(f"OpenD failed dynamic snapshots gate for US.SPY {expiry}: {data}")
        snapshot_rows = normalize_records(data)
        if not snapshot_rows:
            raise OptionsReportError(f"OpenD returned empty dynamic option snapshots for US.SPY {expiry}.")
        gates["dynamic_snapshots"] = f"passed; rows={len(snapshot_rows)}"
        gates["provider_gate_elapsed_seconds"] = f"{time.monotonic() - started:.3f}"
        return gates
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous_handler)
        if ctx is not None:
            ctx.close()


def report_counts(report: object, *, unused_reserve_count: int = 0) -> dict[str, int]:
    skipped = tuple(getattr(report, "skipped", ()))
    ideas = tuple(getattr(report, "ideas", ()))
    candidates = tuple(getattr(report, "candidates", ()))
    return {
        "evaluated_count": len(candidates),
        "promoted_count": len(ideas),
        "refill_count": 0,
        "reject_count": len(skipped),
        "unused_reserve_count": unused_reserve_count,
    }


def main() -> int:
    started_at = dt.datetime.now(dt.timezone.utc)
    env = load_env(ROOT / ".env.example")
    env.update(load_env(ROOT / ".env"))

    parser = argparse.ArgumentParser(description="Build and send a catalyst options screen.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--post", action="store_true")
    parser.add_argument("--output-dir", type=pathlib.Path, default=ROOT / "reports" / "catalyst-options")
    parser.add_argument("--run-ledger", type=pathlib.Path, default=None)
    parser.add_argument("--fixture", action="store_true")
    parser.add_argument("--skip-telegram", action="store_true")
    parser.add_argument("--opend-host", default=env.get("MOOMOO_OPEND_HOST", "127.0.0.1"))
    parser.add_argument("--opend-port", type=int, default=int(env.get("MOOMOO_OPEND_PORT", "11111")))
    parser.add_argument("--min-promoted", type=int, default=5)
    parser.add_argument("--use-static-default-candidates", action="store_true")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    run_ledger = args.run_ledger or args.output_dir / "catalyst-options-run-ledger.jsonl"
    mode = "dry-run" if args.dry_run or not args.post else "post"
    output_path = timestamped_output_path(args.output_dir, started_at)
    stable_output_path = latest_output_path(args.output_dir)

    if args.fixture and args.post and not args.dry_run and not args.skip_telegram:
        blocker = "telegram notification blocked: fixture reports cannot be posted as live catalyst reports"
        write_run_ledger(
            run_ledger,
            status="failed",
            mode=mode,
            output_dir=args.output_dir,
            artifact_path=None,
            blocker=blocker,
            started_at=started_at,
        )
        print(blocker, file=sys.stderr)
        return 1

    provider_gates: dict[str, str] = {"fixture_mode": "skipped"} if args.fixture else {}
    try:
        if not args.fixture:
            provider_gates = run_live_provider_gates(args.opend_host, args.opend_port)
        if args.fixture:
            client = FixtureCatalystOptionsProvider()
            report = build_catalyst_options_screen(client, DEFAULT_CANDIDATES)
        else:
            with MoomooOpenDQuoteClient(host=args.opend_host, port=args.opend_port) as client:
                candidates = DEFAULT_CANDIDATES if args.use_static_default_candidates else sourced_catalyst_candidates()
                quote_client = client if args.use_static_default_candidates else SourcedCatalystQuoteClient(client, WEEKLY_SOURCED_CANDIDATES)
                report = build_catalyst_options_screen(quote_client, candidates)
    except Exception as exc:
        blocker = f"catalyst options screen failed: {exc}"
        write_run_ledger(
            run_ledger,
            status="failed",
            mode=mode,
            output_dir=args.output_dir,
            artifact_path=None,
            blocker=blocker,
            started_at=started_at,
            provider_gates=provider_gates,
        )
        print(blocker, file=sys.stderr)
        return 1

    counts = report_counts(report)
    if counts["promoted_count"] < args.min_promoted:
        blocker = (
            f"promotion gate failed: {counts['promoted_count']} ranked ideas; "
            f"minimum required is {args.min_promoted}. rejected={counts['reject_count']}."
        )
        write_run_ledger(
            run_ledger,
            status="failed",
            mode=mode,
            output_dir=args.output_dir,
            artifact_path=None,
            blocker=blocker,
            started_at=started_at,
            provider_gates=provider_gates,
            **counts,
        )
        print(f"catalyst options screen failed: {blocker}", file=sys.stderr)
        return 1

    metadata = {
        "generated_at": report.generated_at.strftime("%Y-%m-%d %H:%M:%S %Z").strip(),
        "universe": len(report.candidates),
        "ranked_ideas": len(report.ideas),
        "candidate_source": "static-default" if args.fixture or args.use_static_default_candidates else "weekly-sourced-ir-events",
    }
    attachment = render_pdf_report("Catalyst Options Screen", catalyst_report_sections(report), metadata, output_path)
    if attachment != stable_output_path:
        shutil.copyfile(attachment, stable_output_path)
    caption = format_catalyst_telegram_html(report)

    if args.dry_run or not args.post:
        print(caption)
        print(f"attachment: {attachment}")
        print(f"latest_attachment: {stable_output_path}")
        write_run_ledger(
            run_ledger,
            status="succeeded",
            mode=mode,
            output_dir=args.output_dir,
            artifact_path=attachment,
            blocker=None,
            started_at=started_at,
            provider_gates=provider_gates,
            **counts,
        )
        return 0

    if args.skip_telegram or env.get("TELEGRAM_NOTIFY_ENABLED", "false").lower() != "true":
        blocker = (
            "telegram notification skipped: --skip-telegram was set"
            if args.skip_telegram
            else "telegram notification skipped: TELEGRAM_NOTIFY_ENABLED is not true"
        )
        print(blocker)
        write_run_ledger(
            run_ledger,
            status="skipped",
            mode=mode,
            output_dir=args.output_dir,
            artifact_path=attachment,
            blocker=blocker,
            started_at=started_at,
            provider_gates=provider_gates,
            **counts,
        )
        return 0
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = env.get("TELEGRAM_CHAT_ID", "")
    if not token or token.startswith("replace-with-") or not chat_id or chat_id.startswith("replace-with-"):
        blocker = "telegram notification skipped: Telegram credentials are not configured"
        write_run_ledger(
            run_ledger,
            status="failed",
            mode=mode,
            output_dir=args.output_dir,
            artifact_path=attachment,
            blocker=blocker,
            started_at=started_at,
            provider_gates=provider_gates,
            **counts,
        )
        print(blocker, file=sys.stderr)
        return 1

    try:
        post_telegram_document(token, chat_id, attachment, caption=caption, parse_mode="HTML")
    except TelegramSendError as exc:
        blocker = f"telegram notification failed: {exc}"
        write_run_ledger(
            run_ledger,
            status="failed",
            mode=mode,
            output_dir=args.output_dir,
            artifact_path=attachment,
            blocker=blocker,
            started_at=started_at,
            provider_gates=provider_gates,
            **counts,
        )
        print(blocker, file=sys.stderr)
        return 1
    except (TimeoutError, urllib.error.URLError) as exc:
        blocker = f"telegram notification failed: {exc}"
        write_run_ledger(
            run_ledger,
            status="failed",
            mode=mode,
            output_dir=args.output_dir,
            artifact_path=attachment,
            blocker=blocker,
            started_at=started_at,
            provider_gates=provider_gates,
            **counts,
        )
        print(blocker, file=sys.stderr)
        return 1
    print("telegram report sent")
    write_run_ledger(
        run_ledger,
        status="succeeded",
        mode=mode,
        output_dir=args.output_dir,
        artifact_path=attachment,
        blocker=None,
        started_at=started_at,
        provider_gates=provider_gates,
        **counts,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
