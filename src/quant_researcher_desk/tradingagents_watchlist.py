"""Watchlist ingestion and digest rendering for TradingAgents packets."""

from __future__ import annotations

import dataclasses
import datetime as dt
import html
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from quant_researcher_desk.moomoo_options_report import RISK_NOTE
from quant_researcher_desk.tradingagents_packet import DecisionPacket


class WatchlistDigestError(Exception):
    """Raised when the watchlist digest cannot be built."""


@dataclass(frozen=True)
class WatchlistSecurity:
    symbol: str
    name: str
    group_name: str
    group_type: str


@dataclass(frozen=True)
class WatchlistDigest:
    title: str
    metadata: dict[str, object]
    sections: list[dict[str, object]]
    caption: str


@dataclass(frozen=True)
class WatchlistSymbolStatus:
    symbol: str
    status: str
    reason_code: str | None = None
    detail: str | None = None
    label: str | None = None


LABEL_PRIORITY = {
    "Research Candidate": 0,
    "Watchlist": 1,
    "Needs Human Review": 2,
    "Reject": 3,
}


def normalize_watchlist_symbol(raw_code: str) -> str:
    code = str(raw_code or "").strip().upper()
    if not code:
        raise WatchlistDigestError("Encountered an empty watchlist symbol.")
    if "." in code:
        return code
    if re.fullmatch(r"[A-Z][A-Z0-9.-]*", code):
        return f"US.{code}"
    raise WatchlistDigestError(f"Unsupported watchlist symbol format: {raw_code}")


def build_watchlist_securities(
    group_rows: Sequence[Mapping[str, Any]],
    rows_by_group: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    group_name: str | None = None,
    max_candidates: int | None = None,
) -> list[WatchlistSecurity]:
    groups = [row for row in group_rows if str(row.get("group_name", "")).strip()]
    if group_name:
        groups = [row for row in groups if str(row.get("group_name", "")).strip() == group_name]

    securities: list[WatchlistSecurity] = []
    seen: set[str] = set()
    for group in groups:
        current_group_name = str(group.get("group_name", "")).strip()
        current_group_type = str(group.get("group_type", "")).strip() or "UNKNOWN"
        for row in rows_by_group.get(current_group_name, []):
            try:
                symbol = normalize_watchlist_symbol(str(row.get("code", "")))
            except WatchlistDigestError:
                continue
            if symbol in seen:
                continue
            seen.add(symbol)
            securities.append(
                WatchlistSecurity(
                    symbol=symbol,
                    name=str(row.get("name", "")).strip() or symbol,
                    group_name=current_group_name,
                    group_type=current_group_type,
                )
            )
            if max_candidates and len(securities) >= max_candidates:
                return securities
    if not securities:
        raise WatchlistDigestError("No watchlist securities were returned by OpenD.")
    return securities


def rank_watchlist_packets(packets: Sequence[DecisionPacket], top_n: int) -> list[DecisionPacket]:
    ranked = sorted(
        packets,
        key=lambda packet: (
            LABEL_PRIORITY.get(packet.label, 99),
            -packet.evidence_pack.research_report.model_edge_pct,
            -packet.evidence_pack.research_report.contract.volume,
            -packet.evidence_pack.research_report.contract.open_interest,
            packet.symbol,
        ),
    )
    return ranked[:top_n]


def build_watchlist_digest(
    packets: Sequence[DecisionPacket],
    symbol_statuses: Sequence[WatchlistSymbolStatus] | None = None,
) -> WatchlistDigest:
    ranked = list(packets)
    if not ranked:
        raise WatchlistDigestError("No decision packets were available for the watchlist digest.")
    statuses = list(symbol_statuses or [WatchlistSymbolStatus(symbol=packet.symbol, status="success", label=packet.label) for packet in ranked])
    generated_at = ranked[0].generated_at
    table_rows = []
    detail_sections = []
    top_symbols = []
    for index, packet in enumerate(ranked, start=1):
        report = packet.evidence_pack.research_report
        top_symbols.append(packet.symbol)
        table_rows.append(
            {
                "rank": index,
                "symbol": packet.symbol,
                "label": packet.label,
                "contract": report.contract.code,
                "edge_pct": f"{report.model_edge_pct:.1%}",
                "volume": report.contract.volume,
                "open_interest": report.contract.open_interest,
            }
        )
        detail_sections.append(
            {
                "title": f"{index}. {packet.symbol} - {packet.label}",
                "content": (
                    f"{packet.executive_summary}\n\n"
                    f"Contract: {report.contract.code}\n"
                    f"Edge: {report.model_edge_pct:.1%}\n"
                    f"IV/HV: {report.implied_volatility_used:.1%}/{report.historical_volatility:.1%}\n"
                    f"Top rationale: {packet.rationale[0]}"
                ),
            }
        )
    title = "TradingAgents Watchlist Digest"
    skipped_rows = [
        {
            "symbol": status.symbol,
            "status": status.status,
            "reason_code": status.reason_code or "",
            "detail": status.detail or "",
        }
        for status in statuses
        if status.status != "success"
    ]
    metadata = {
        "generated_at": generated_at.strftime("%Y-%m-%d %H:%M:%S %Z").strip(),
        "attempted": len(statuses),
        "succeeded": sum(1 for status in statuses if status.status == "success"),
        "skipped_optionability": sum(1 for status in statuses if status.status == "skipped_optionability"),
        "skipped_provider": sum(1 for status in statuses if status.status == "skipped_provider"),
        "skipped_debate_backend": sum(1 for status in statuses if status.status == "skipped_debate_backend"),
        "top_label": ranked[0].label,
    }
    sections = [
        {
            "title": "Run Summary",
            "summary": "Multi-symbol watchlist runs publish partial output when at least one packet survives evidence and debate generation.",
            "table": [
                {"metric": "Attempted", "value": metadata["attempted"]},
                {"metric": "Succeeded", "value": metadata["succeeded"]},
                {"metric": "Skipped Optionability", "value": metadata["skipped_optionability"]},
                {"metric": "Skipped Provider", "value": metadata["skipped_provider"]},
                {"metric": "Skipped Debate Backend", "value": metadata["skipped_debate_backend"]},
            ],
        },
        {
            "title": "Ranked Queue",
            "summary": (
                "Watchlist names were screened through the repo-owned options packet, then normalized into "
                "research-only labels for one desk digest."
            ),
            "table": table_rows,
        },
        *(
            [
                {
                    "title": "Skipped Symbols",
                    "summary": "Skipped symbols are preserved with typed reasons so partial digest publication stays auditable.",
                    "table": skipped_rows,
                }
            ]
            if skipped_rows
            else []
        ),
        *detail_sections,
        {"title": "Risk Note", "content": RISK_NOTE},
    ]
    caption = (
        f"<b>Quant Researcher Desk - TradingAgents Watchlist Digest</b>\n"
        f"Generated: <code>{html.escape(generated_at.strftime('%Y-%m-%d %H:%M:%S %Z').strip())}</code>\n"
        f"Ranked names: <code>{html.escape(', '.join(top_symbols))}</code>\n"
        f"Attempted: <code>{metadata['attempted']}</code> | Survived: <code>{metadata['succeeded']}</code>\n"
        f"{html.escape(RISK_NOTE)}"
    )
    return WatchlistDigest(
        title=title,
        metadata=metadata,
        sections=sections,
        caption=caption,
    )


def build_watchlist_digest_from_packets(
    packets: Sequence[DecisionPacket],
    top_n: int,
    symbol_statuses: Sequence[WatchlistSymbolStatus] | None = None,
) -> WatchlistDigest:
    return build_watchlist_digest(rank_watchlist_packets(packets, top_n=top_n), symbol_statuses=symbol_statuses)
