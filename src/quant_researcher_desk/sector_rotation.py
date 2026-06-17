"""Deterministic sector rotation for scheduled value-chain reports."""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SectorRotationEntry:
    market: str
    sector: str
    note: str


@dataclass(frozen=True)
class SectorRotationState:
    sent_at_epoch: int
    market: str
    sector: str
    cadence_minutes: int


DEFAULT_SECTOR_ROTATION: tuple[SectorRotationEntry, ...] = (
    SectorRotationEntry("HK", "tech", "China technology platforms, hardware, and semiconductor read-through."),
    SectorRotationEntry("US", "semiconductors", "AI infrastructure supply chain and capex sensitivity."),
    SectorRotationEntry("US", "energy", "Oil, LNG, services, and downstream demand transmission."),
    SectorRotationEntry("US", "banks", "Deposit cost, loan growth, capital markets, and credit-cycle read-through."),
    SectorRotationEntry("HK", "consumer", "China consumption, platform distribution, and discretionary demand."),
    SectorRotationEntry("US", "defense", "Prime contractors, mission systems, and aerospace supply chain."),
    SectorRotationEntry("HK", "internet platforms", "Platform economics, cloud, payments, and local services."),
)


def rotation_bucket(
    current_time: dt.datetime | None = None,
    cadence_minutes: int = 24 * 60,
) -> int:
    if cadence_minutes <= 0:
        raise ValueError("Rotation cadence must be positive.")

    anchor = (current_time or dt.datetime.now()).replace(second=0, microsecond=0)
    return int(anchor.timestamp() // (cadence_minutes * 60))


def select_sector_rotation_entry(
    current_time: dt.date | dt.datetime | None = None,
    rotation: tuple[SectorRotationEntry, ...] = DEFAULT_SECTOR_ROTATION,
    cadence_minutes: int = 24 * 60,
) -> SectorRotationEntry:
    if not rotation:
        raise ValueError("Sector rotation cannot be empty.")
    if cadence_minutes <= 0:
        raise ValueError("Rotation cadence must be positive.")

    value = current_time or dt.date.today()
    if isinstance(value, dt.datetime):
        anchor = value.replace(second=0, microsecond=0)
        bucket = int(anchor.timestamp() // (cadence_minutes * 60))
        return rotation[bucket % len(rotation)]

    return rotation[value.toordinal() % len(rotation)]


def load_sector_rotation_state(path: str | Path) -> SectorRotationState | None:
    state_path = Path(path)
    if not state_path.exists():
        return None

    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
        return SectorRotationState(
            sent_at_epoch=int(payload["sent_at_epoch"]),
            market=str(payload["market"]),
            sector=str(payload["sector"]),
            cadence_minutes=int(payload["cadence_minutes"]),
        )
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None


def save_sector_rotation_state(path: str | Path, state: SectorRotationState) -> None:
    state_path = Path(path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {
            "sent_at_epoch": state.sent_at_epoch,
            "market": state.market,
            "sector": state.sector,
            "cadence_minutes": state.cadence_minutes,
        },
        indent=2,
        sort_keys=True,
    )
    tmp_path = state_path.with_suffix(state_path.suffix + ".tmp")
    tmp_path.write_text(payload, encoding="utf-8")
    tmp_path.replace(state_path)


def select_rotation_entry_for_dispatch(
    current_time: dt.datetime,
    rotation: tuple[SectorRotationEntry, ...] = DEFAULT_SECTOR_ROTATION,
    cadence_minutes: int = 24 * 60,
    state_path: str | Path | None = None,
) -> tuple[SectorRotationEntry, bool]:
    entry = select_sector_rotation_entry(
        current_time=current_time,
        rotation=rotation,
        cadence_minutes=cadence_minutes,
    )
    if state_path is None:
        return entry, False

    existing = load_sector_rotation_state(state_path)
    if existing and existing.cadence_minutes == cadence_minutes:
        anchor = current_time.replace(second=0, microsecond=0)
        current_epoch = int(anchor.timestamp())
        cooldown_until = existing.sent_at_epoch + cadence_minutes * 60
        if current_epoch < cooldown_until:
            return entry, True

    return entry, False
