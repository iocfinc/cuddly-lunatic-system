"""Shared deterministic market fixtures for options reporting workflows."""

from __future__ import annotations

import datetime as dt
import math
import re
from collections.abc import Iterable

FIXTURE_UNDERLYINGS: dict[str, dict[str, float | str]] = {
    "US.AAPL": {"company": "Apple", "spot": 195.0},
    "US.MSFT": {"company": "Microsoft", "spot": 430.0},
    "US.NVDA": {"company": "NVIDIA", "spot": 118.0},
    "US.AMZN": {"company": "Amazon", "spot": 181.0},
    "US.META": {"company": "Meta", "spot": 502.0},
    "US.NFLX": {"company": "Netflix", "spot": 622.0},
    "US.AMD": {"company": "AMD", "spot": 162.0},
    "US.GOOGL": {"company": "Alphabet", "spot": 176.0},
    "US.TSM": {"company": "Taiwan Semiconductor", "spot": 168.0},
    "US.LRCX": {"company": "Lam Research", "spot": 415.0},
    "US.LLY": {"company": "Eli Lilly", "spot": 890.0},
    "US.XOM": {"company": "Exxon Mobil", "spot": 112.0},
    "US.CVX": {"company": "Chevron", "spot": 154.0},
    "US.KLAC": {"company": "KLA", "spot": 865.0},
    "US.NOOPT": {"company": "No Options Co", "spot": 88.0},
    "US.TEST": {"company": "Test Fixture", "spot": 100.0},
}

FIXTURE_TREND_REGIMES: dict[str, str] = {
    "US.AAPL": "bullish",
    "US.MSFT": "bearish",
    "US.NVDA": "mixed",
    "US.AMZN": "bullish",
    "US.META": "bullish",
    "US.NFLX": "bearish",
    "US.AMD": "bullish",
    "US.GOOGL": "bearish",
    "US.TSM": "bullish",
    "US.LRCX": "bullish",
    "US.LLY": "bullish",
    "US.XOM": "mixed",
    "US.CVX": "mixed",
    "US.KLAC": "bullish",
    "US.NOOPT": "bullish",
    "US.TEST": "bullish",
}

FIXTURE_PLATES: dict[str, dict[str, object]] = {
    "US.TECH": {"plate_name": "US Technology", "symbols": ["US.NVDA", "US.MSFT", "US.AMD", "US.GOOGL"]},
    "US.MEGA": {"plate_name": "US Mega Caps", "symbols": ["US.AAPL", "US.MSFT", "US.AMZN", "US.NOOPT"]},
    "US.PLATFORMS": {"plate_name": "US Platforms", "symbols": ["US.META", "US.NFLX", "US.GOOGL", "US.AMZN"]},
    "US.FABS": {"plate_name": "US Semiconductor Platforms", "symbols": ["US.NVDA", "US.AMD", "US.TSM"]},
}

_STRIKE_OFFSETS = (-0.10, -0.05, 0.0, 0.05, 0.10)
_CALL_DELTAS = {
    -0.10: 0.72,
    -0.05: 0.61,
    0.0: 0.52,
    0.05: 0.35,
    0.10: 0.18,
}
_PUT_DELTAS = {
    -0.10: -0.16,
    -0.05: -0.28,
    0.0: -0.43,
    0.05: -0.61,
    0.10: -0.76,
}

_OPTION_CODE_RE = re.compile(
    r"^(?P<symbol>US\.[A-Z]+)(?P<expiry>\d{6})(?P<side>[CP])(?P<strike>\d{6})$"
)


def fixture_expiries(anchor_date: dt.date) -> list[str]:
    return [(anchor_date + dt.timedelta(days=7)).isoformat(), (anchor_date + dt.timedelta(days=14)).isoformat()]


def fixture_chain_expiry(anchor_date: dt.date) -> str:
    return fixture_expiries(anchor_date)[0]


def fixture_plate_list() -> list[dict[str, str]]:
    return [{"code": code, "plate_name": str(payload["plate_name"])} for code, payload in FIXTURE_PLATES.items()]


def fixture_plate_constituents(plate_code: str) -> list[dict[str, str]]:
    payload = FIXTURE_PLATES.get(plate_code, {})
    rows = []
    for symbol in payload.get("symbols", []):
        underlying = FIXTURE_UNDERLYINGS[str(symbol)]
        rows.append({"code": str(symbol), "stock_name": str(underlying["company"])})
    return rows


def fixture_spot(symbol: str) -> float:
    return float(FIXTURE_UNDERLYINGS[symbol]["spot"])


def fixture_company(symbol: str) -> str:
    return str(FIXTURE_UNDERLYINGS[symbol]["company"])


def _strike_value(spot: float, offset: float) -> float:
    return round(spot * (1.0 + offset), 0)


def _option_code(symbol: str, expiry: str, side: str, strike: float) -> str:
    return f"{symbol}{expiry.replace('-', '')[2:]}{side}{int(round(strike * 1000)):06d}"


def fixture_option_chain(symbol: str, expiry: str) -> list[dict[str, object]]:
    if symbol == "US.NOOPT":
        return []
    spot = fixture_spot(symbol)
    rows: list[dict[str, object]] = []
    for offset in _STRIKE_OFFSETS:
        strike = _strike_value(spot, offset)
        for side in ("CALL", "PUT"):
            rows.append(
                {
                    "code": _option_code(symbol, expiry, "C" if side == "CALL" else "P", strike),
                    "option_type": side,
                    "strike_price": strike,
                    "strike_time": expiry,
                }
            )
    return rows


def _parse_option_code(code: str) -> tuple[str, str, float]:
    match = _OPTION_CODE_RE.match(code)
    if not match:
        raise ValueError(f"Unsupported fixture option code: {code}")
    symbol = match.group("symbol")
    side = "CALL" if match.group("side") == "C" else "PUT"
    strike = int(match.group("strike")) / 1000.0
    return symbol, side, strike


def fixture_market_snapshots(codes: Iterable[str]) -> list[dict[str, object]]:
    snapshots: list[dict[str, object]] = []
    for code in codes:
        symbol, side, strike = _parse_option_code(code)
        spot = fixture_spot(symbol)
        offset = min(_STRIKE_OFFSETS, key=lambda candidate: abs(_strike_value(spot, candidate) - strike))
        ratio = abs(strike / spot - 1.0)
        base_iv = 0.23 + (abs(hash(symbol)) % 4) * 0.01
        implied_volatility = round(base_iv + ratio * 0.42 + (0.015 if side == "PUT" else 0.0), 4)

        if side == "CALL":
            delta = _CALL_DELTAS[offset]
        else:
            delta = _PUT_DELTAS[offset]

        time_value = max(spot * (0.012 - ratio * 0.04), 0.4)
        if side == "CALL":
            premium = max(spot - strike, 0.0) * 0.38 + time_value
        else:
            premium = max(strike - spot, 0.0) * 0.38 + time_value * 0.92
        premium = round(max(premium, 0.4), 2)

        liquidity_factor = max(0.25, 1.0 - ratio * 5.5)
        volume = int(round((1550 + (abs(hash(symbol)) % 240)) * liquidity_factor))
        open_interest = int(round((2200 + (abs(hash(symbol)) % 360)) * (0.85 + liquidity_factor * 0.35)))

        snapshots.append(
            {
                "code": code,
                "last_price": premium,
                "implied_volatility": implied_volatility,
                "delta": delta,
                "open_interest": max(open_interest, 40),
                "volume": max(volume, 30),
            }
        )
    return snapshots


def fixture_daily_bars(symbol: str, count: int = 250) -> list[dict[str, object]]:
    regime = FIXTURE_TREND_REGIMES.get(symbol, "bullish")
    start = dt.date(2025, 1, 1)
    if regime == "bullish":
        closes = [80.0 + index * 0.65 for index in range(max(count, 250))]
    elif regime == "bearish":
        closes = [260.0 - index * 0.6 for index in range(max(count, 250))]
    else:
        closes = [120.0 + index * 0.18 for index in range(230)] + [161.0 - index * 1.15 for index in range(20)]
    series = closes[-count:]
    return [
        {"time_key": (start + dt.timedelta(days=index)).isoformat(), "close": close}
        for index, close in enumerate(series)
    ]


def monte_carlo_distribution_buckets(values: list[float], bucket_count: int = 12) -> list[dict[str, float | str]]:
    if not values:
        return []
    low = min(values)
    high = max(values)
    if math.isclose(low, high):
        return [{"label": f"{low:.2f}", "value": float(len(values))}]
    width = (high - low) / bucket_count
    buckets = [0 for _ in range(bucket_count)]
    for value in values:
        index = min(int((value - low) / width), bucket_count - 1)
        buckets[index] += 1
    rows: list[dict[str, float | str]] = []
    for index, count in enumerate(buckets):
        start = low + index * width
        end = start + width
        rows.append({"label": f"{start:.2f} to {end:.2f}", "value": float(count)})
    return rows
