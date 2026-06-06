"""Build a local Moomoo OpenD options report for Telegram delivery."""

from __future__ import annotations

import datetime as dt
import html
import math
import socket
from dataclasses import dataclass
from typing import Any, Iterable, Protocol


RET_OK_VALUE = 0
DEFAULT_BATCH_SIZE = 400
RISK_NOTE = "Research output only, not a trading instruction."


class OptionsReportError(Exception):
    """Raised when the options report cannot be built."""


class QuoteClient(Protocol):
    def get_underlying_snapshot(self, symbol: str) -> dict[str, Any]:
        ...

    def get_option_expirations(self, symbol: str) -> list[str]:
        ...

    def get_option_chain(self, symbol: str, expiry: str) -> list[dict[str, Any]]:
        ...

    def get_market_snapshots(self, codes: list[str]) -> list[dict[str, Any]]:
        ...

    def get_plate_list(self, market: str, plate_type: str = "ALL") -> list[dict[str, Any]]:
        ...

    def get_plate_constituents(self, plate_code: str) -> list[dict[str, Any]]:
        ...

    def get_daily_bars(self, symbol: str, count: int = 250) -> list[dict[str, Any]]:
        ...

    def close(self) -> None:
        ...


@dataclass(frozen=True)
class RankedOption:
    code: str
    option_type: str
    strike: float
    last_price: float | None
    implied_volatility: float | None
    delta: float | None
    open_interest: int
    volume: int
    strike_distance: float


@dataclass(frozen=True)
class OptionsReport:
    symbol: str
    generated_at: dt.datetime
    underlying_price: float | None
    expiry: str
    scanned_contract_count: int
    calls: list[RankedOption]
    puts: list[RankedOption]


@dataclass(frozen=True)
class OpenDCapability:
    name: str
    method_name: str
    status: str
    workflow_stage: str
    ranking_eligible: bool
    notes: str


def opend_capability_contract() -> tuple[OpenDCapability, ...]:
    """Verified OpenD wrapper surface for this repo's current production lane."""

    return (
        OpenDCapability(
            name="plate_list",
            method_name="get_plate_list",
            status="verified",
            workflow_stage="universe_discovery",
            ranking_eligible=False,
            notes="Broad market and sector plate discovery for seeding weekly underlyings.",
        ),
        OpenDCapability(
            name="plate_constituents",
            method_name="get_plate_constituents",
            status="verified",
            workflow_stage="universe_discovery",
            ranking_eligible=False,
            notes="Underlying membership expansion from selected plates.",
        ),
        OpenDCapability(
            name="daily_bars",
            method_name="get_daily_bars",
            status="verified",
            workflow_stage="stock_context",
            ranking_eligible=False,
            notes="Daily price history for trend-regime classification.",
        ),
        OpenDCapability(
            name="option_expirations",
            method_name="get_option_expirations",
            status="verified",
            workflow_stage="weekly_expiry",
            ranking_eligible=False,
            notes="Weekly holding-window expiry selection.",
        ),
        OpenDCapability(
            name="option_chain",
            method_name="get_option_chain",
            status="verified",
            workflow_stage="contract_quality",
            ranking_eligible=False,
            notes="Contract discovery for the selected expiry window.",
        ),
        OpenDCapability(
            name="market_snapshots",
            method_name="get_market_snapshots",
            status="verified",
            workflow_stage="contract_quality",
            ranking_eligible=False,
            notes="Batch snapshot transport for underlying and contract records.",
        ),
        OpenDCapability(
            name="underlying_snapshot",
            method_name="get_underlying_snapshot",
            status="verified",
            workflow_stage="contract_quality",
            ranking_eligible=False,
            notes="Underlying price used for contract selection and pricing inputs.",
        ),
        OpenDCapability(
            name="implied_volatility",
            method_name="get_market_snapshots",
            status="verified_when_present",
            workflow_stage="valuation",
            ranking_eligible=True,
            notes="Use only when the snapshot row includes an IV field; otherwise fall back to solver-derived IV.",
        ),
        OpenDCapability(
            name="delta",
            method_name="get_market_snapshots",
            status="verified_when_present",
            workflow_stage="ranking",
            ranking_eligible=True,
            notes="Use only when the snapshot row includes delta; current weekly lane uses it for delta-band filtering.",
        ),
        OpenDCapability(
            name="open_interest",
            method_name="get_market_snapshots",
            status="verified_when_present",
            workflow_stage="ranking",
            ranking_eligible=True,
            notes="Use only when the snapshot row includes open interest.",
        ),
        OpenDCapability(
            name="volume",
            method_name="get_market_snapshots",
            status="verified_when_present",
            workflow_stage="ranking",
            ranking_eligible=True,
            notes="Use only when the snapshot row includes contract volume.",
        ),
        OpenDCapability(
            name="watchlist_groups",
            method_name="get_user_security_groups",
            status="verified",
            workflow_stage="universe_discovery",
            ranking_eligible=False,
            notes="Repo-owned watchlist workflows can source universes from saved groups.",
        ),
        OpenDCapability(
            name="watchlist_securities",
            method_name="get_user_security",
            status="verified",
            workflow_stage="universe_discovery",
            ranking_eligible=False,
            notes="Repo-owned watchlist workflows can source names from saved groups.",
        ),
        OpenDCapability(
            name="bid_ask_spread",
            method_name="get_market_snapshots",
            status="unsupported_for_scoring",
            workflow_stage="ranking",
            ranking_eligible=False,
            notes="Do not score real spread width until the wrapper exposes and tests reliable bid/ask fields.",
        ),
        OpenDCapability(
            name="event_calendar",
            method_name="n/a",
            status="unsupported_for_scoring",
            workflow_stage="event_context",
            ranking_eligible=False,
            notes="Weekly lane must treat event timing as provider-optional until a repo-owned event seam is wired in.",
        ),
    )


def normalize_records(data: Any) -> list[dict[str, Any]]:
    if data is None:
        return []
    if hasattr(data, "to_dict"):
        return list(data.to_dict(orient="records"))
    if isinstance(data, dict):
        return [data]
    return [dict(row) for row in data]


def get_first(row: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return default


def as_float(value: Any) -> float | None:
    if value in (None, "", "N/A", "--"):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(result):
        return None
    return result


def as_int(value: Any) -> int:
    number = as_float(value)
    if number is None:
        return 0
    return int(number)


def normalize_option_type(value: Any) -> str:
    text = str(value or "").upper()
    if "CALL" in text or text in {"C", "涨", "认购"}:
        return "CALL"
    if "PUT" in text or text in {"P", "跌", "认沽"}:
        return "PUT"
    return text


def extract_expiry(row: dict[str, Any]) -> str | None:
    value = get_first(row, "strike_time", "expiry", "expiration_date", "date", "time")
    if value is None:
        return None
    text = str(value).strip()
    return text[:10] if len(text) >= 10 else text


def nearest_expiry(expiries: Iterable[str], today: dt.date | None = None) -> str:
    today = today or dt.date.today()
    parsed: list[tuple[dt.date, str]] = []
    for expiry in expiries:
        text = str(expiry).strip()
        if not text:
            continue
        try:
            date_value = dt.date.fromisoformat(text[:10])
        except ValueError:
            continue
        if date_value >= today:
            parsed.append((date_value, text[:10]))
    if not parsed:
        raise OptionsReportError("No future option expirations were returned by OpenD.")
    return min(parsed, key=lambda item: item[0])[1]


def target_expiry(
    expiries: Iterable[str],
    today: dt.date | None = None,
    *,
    minimum_days_out: int = 0,
    target_days_out: int | None = None,
) -> str:
    """Select an expiry far enough out, closest to the target holding window."""

    today = today or dt.date.today()
    target = today + dt.timedelta(days=target_days_out if target_days_out is not None else minimum_days_out)
    parsed: list[tuple[dt.date, str]] = []
    for expiry in expiries:
        text = str(expiry).strip()
        if not text:
            continue
        try:
            date_value = dt.date.fromisoformat(text[:10])
        except ValueError:
            continue
        if (date_value - today).days >= minimum_days_out:
            parsed.append((date_value, text[:10]))
    if not parsed:
        raise OptionsReportError(
            f"No option expirations at least {minimum_days_out} days out were returned by OpenD."
        )
    return min(parsed, key=lambda item: (abs((item[0] - target).days), item[0]))[1]


def merge_chain_and_snapshots(
    chain_rows: list[dict[str, Any]],
    snapshot_rows: list[dict[str, Any]],
    underlying_price: float | None,
) -> list[RankedOption]:
    snapshots_by_code = {str(row.get("code", "")): row for row in snapshot_rows}
    ranked: list[RankedOption] = []
    for chain_row in chain_rows:
        code = str(get_first(chain_row, "code", "stock", default="")).strip()
        if not code:
            continue
        snapshot = snapshots_by_code.get(code, {})
        merged = {**chain_row, **snapshot}
        strike = as_float(get_first(merged, "strike_price", "strike", default=None))
        if strike is None:
            continue
        option_type = normalize_option_type(get_first(merged, "option_type", "type", default=""))
        if option_type not in {"CALL", "PUT"}:
            continue
        last_price = as_float(get_first(merged, "last_price", "cur_price", "price", default=None))
        iv = as_float(
            get_first(
                merged,
                "implied_volatility",
                "implied_vol",
                "iv",
                "option_implied_volatility",
                default=None,
            )
        )
        delta = as_float(get_first(merged, "delta", "option_delta", default=None))
        open_interest = as_int(get_first(merged, "open_interest", "option_open_interest", default=0))
        volume = as_int(get_first(merged, "volume", "option_volume", default=0))
        distance = abs(strike - underlying_price) if underlying_price is not None else 0.0
        ranked.append(
            RankedOption(
                code=code,
                option_type=option_type,
                strike=strike,
                last_price=last_price,
                implied_volatility=iv,
                delta=delta,
                open_interest=open_interest,
                volume=volume,
                strike_distance=distance,
            )
        )
    return ranked


def rank_options(options: Iterable[RankedOption], option_type: str, rows: int) -> list[RankedOption]:
    matching = [option for option in options if option.option_type == option_type]
    return sorted(
        matching,
        key=lambda option: (-option.volume, -option.open_interest, option.strike_distance, option.strike),
    )[:rows]


def build_options_report(
    client: QuoteClient,
    symbol: str,
    expiry: str | None = None,
    rows: int = 5,
    now: dt.datetime | None = None,
    minimum_days_out: int = 0,
    target_days_out: int | None = None,
) -> OptionsReport:
    underlying = client.get_underlying_snapshot(symbol)
    underlying_price = as_float(get_first(underlying, "last_price", "cur_price", "price", default=None))
    today = (now or dt.datetime.now()).date()
    selected_expiry = expiry or target_expiry(
        client.get_option_expirations(symbol),
        today=today,
        minimum_days_out=minimum_days_out,
        target_days_out=target_days_out,
    )
    chain_rows = client.get_option_chain(symbol, selected_expiry)
    if not chain_rows:
        raise OptionsReportError(f"No option chain rows returned for {symbol} {selected_expiry}.")
    codes = [str(row.get("code", "")).strip() for row in chain_rows if str(row.get("code", "")).strip()]
    snapshot_rows = client.get_market_snapshots(codes) if codes else []
    merged_options = merge_chain_and_snapshots(chain_rows, snapshot_rows, underlying_price)
    return OptionsReport(
        symbol=symbol,
        generated_at=now or dt.datetime.now(dt.timezone.utc).astimezone(),
        underlying_price=underlying_price,
        expiry=selected_expiry,
        scanned_contract_count=len(chain_rows),
        calls=rank_options(merged_options, "CALL", rows),
        puts=rank_options(merged_options, "PUT", rows),
    )


def format_number(value: float | None, decimals: int = 2) -> str:
    if value is None:
        return "N/A"
    return f"{value:.{decimals}f}"


def format_int(value: int) -> str:
    return f"{value:,}"


def format_option_line(option: RankedOption) -> str:
    return (
        f"{format_number(option.strike)} | "
        f"{format_number(option.last_price)} | "
        f"{format_number(option.implied_volatility)} | "
        f"{format_number(option.delta, 3)} | "
        f"{format_int(option.open_interest)} | "
        f"{format_int(option.volume)}"
    )


def format_telegram_html(report: OptionsReport) -> str:
    generated = report.generated_at.strftime("%Y-%m-%d %H:%M:%S %Z").strip()
    title = html.escape(f"Quant Researcher Desk - {report.symbol} Options")
    lines = [
        f"<b>{title}</b>",
        f"Generated: <code>{html.escape(generated)}</code>",
        f"Underlying latest: <code>{html.escape(format_number(report.underlying_price))}</code>",
        f"Selected expiry: <code>{html.escape(report.expiry)}</code>",
        f"Scanned contracts: <code>{report.scanned_contract_count}</code>",
        "",
        "<b>Top Calls</b>",
        "<code>Strike | Last | IV | Delta | OI | Vol</code>",
    ]
    lines.extend(f"<code>{html.escape(format_option_line(option))}</code>" for option in report.calls)
    lines.extend(["", "<b>Top Puts</b>", "<code>Strike | Last | IV | Delta | OI | Vol</code>"])
    lines.extend(f"<code>{html.escape(format_option_line(option))}</code>" for option in report.puts)
    lines.extend(["", html.escape(RISK_NOTE)])
    return "\n".join(lines)


class MoomooOpenDQuoteClient:
    """Small wrapper around the moomoo OpenD quote context."""

    def __init__(self, host: str = "127.0.0.1", port: int = 11111, batch_size: int = DEFAULT_BATCH_SIZE) -> None:
        self.host = host
        self.port = port
        self.batch_size = batch_size
        self._ctx: Any = None
        self._ret_ok: Any = RET_OK_VALUE

    def __enter__(self) -> "MoomooOpenDQuoteClient":
        self.connect()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def connect(self) -> None:
        self._check_opend_reachable()
        from moomoo import OpenQuoteContext, RET_OK

        self._ret_ok = RET_OK
        try:
            self._ctx = OpenQuoteContext(host=self.host, port=self.port, ai_type=1)
        except TypeError:
            self._ctx = OpenQuoteContext(host=self.host, port=self.port)

    def _check_opend_reachable(self) -> None:
        try:
            with socket.create_connection((self.host, self.port), timeout=2):
                return
        except OSError as exc:
            raise OptionsReportError(f"Cannot connect to OpenD at {self.host}:{self.port}. Start and log into OpenD first.") from exc

    @property
    def ctx(self) -> Any:
        if self._ctx is None:
            self.connect()
        return self._ctx

    def check_ret(self, ret: Any, data: Any, action: str) -> Any:
        if ret != self._ret_ok:
            raise OptionsReportError(f"OpenD failed to {action}: {data}")
        return data

    def get_underlying_snapshot(self, symbol: str) -> dict[str, Any]:
        records = self.get_market_snapshots([symbol])
        if not records:
            raise OptionsReportError(f"No underlying snapshot returned for {symbol}.")
        return records[0]

    def get_option_expirations(self, symbol: str) -> list[str]:
        ret, data = self.ctx.get_option_expiration_date(symbol)
        rows = normalize_records(self.check_ret(ret, data, "get option expirations"))
        expiries = [expiry for row in rows if (expiry := extract_expiry(row))]
        if not expiries:
            raise OptionsReportError(f"No option expirations returned for {symbol}.")
        return expiries

    def get_option_chain(self, symbol: str, expiry: str) -> list[dict[str, Any]]:
        ret, data = self.ctx.get_option_chain(symbol, start=expiry, end=expiry)
        return normalize_records(self.check_ret(ret, data, "get option chain"))

    def get_market_snapshots(self, codes: list[str]) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for start in range(0, len(codes), self.batch_size):
            batch = codes[start : start + self.batch_size]
            if not batch:
                continue
            ret, data = self.ctx.get_market_snapshot(batch)
            records.extend(normalize_records(self.check_ret(ret, data, "get market snapshots")))
        return records

    def _resolve_market_enum(self, market: str) -> Any:
        normalized = market.strip().upper()
        try:
            from moomoo import Market
        except Exception:
            return normalized
        if not hasattr(Market, normalized):
            raise OptionsReportError(f"Unsupported market for plate discovery: {market}")
        return getattr(Market, normalized)

    def _resolve_plate_enum(self, plate_type: str) -> Any:
        normalized = plate_type.strip().upper()
        try:
            from moomoo import Plate
        except Exception:
            return normalized
        if not hasattr(Plate, normalized):
            raise OptionsReportError(f"Unsupported plate type for plate discovery: {plate_type}")
        return getattr(Plate, normalized)

    def get_plate_list(self, market: str, plate_type: str = "ALL") -> list[dict[str, Any]]:
        ret, data = self.ctx.get_plate_list(self._resolve_market_enum(market), self._resolve_plate_enum(plate_type))
        return normalize_records(self.check_ret(ret, data, f"get {market} plate list"))

    def get_plate_constituents(self, plate_code: str) -> list[dict[str, Any]]:
        ret, data = self.ctx.get_plate_stock(plate_code)
        return normalize_records(self.check_ret(ret, data, f"get plate constituents for {plate_code}"))

    def _resolve_kline_enum(self) -> Any:
        try:
            from moomoo import KLType
        except Exception:
            return "K_DAY"
        return getattr(KLType, "K_DAY", "K_DAY")

    def get_daily_bars(self, symbol: str, count: int = 250) -> list[dict[str, Any]]:
        kline_type = self._resolve_kline_enum()
        if hasattr(self.ctx, "request_history_kline"):
            ret, data, _ = self.ctx.request_history_kline(symbol, ktype=kline_type, max_count=count)
            return normalize_records(self.check_ret(ret, data, f"get daily bars for {symbol}"))
        if hasattr(self.ctx, "get_cur_kline"):
            ret, data = self.ctx.get_cur_kline(symbol, count, ktype=kline_type)
            return normalize_records(self.check_ret(ret, data, f"get daily bars for {symbol}"))
        raise OptionsReportError("OpenD quote client does not expose a daily-bar API in this environment.")

    def get_user_security_groups(self, group_type: str = "ALL") -> list[dict[str, Any]]:
        ret, data = self.ctx.get_user_security_group(group_type)
        return normalize_records(self.check_ret(ret, data, "get watchlist groups"))

    def get_user_security(self, group_name: str) -> list[dict[str, Any]]:
        ret, data = self.ctx.get_user_security(group_name)
        return normalize_records(self.check_ret(ret, data, f"get watchlist securities for {group_name}"))

    def close(self) -> None:
        if self._ctx is not None:
            self._ctx.close()
            self._ctx = None
