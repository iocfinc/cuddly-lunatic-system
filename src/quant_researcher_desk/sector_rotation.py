"""Deterministic sector rotation for scheduled value-chain reports."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass


@dataclass(frozen=True)
class SectorRotationEntry:
    market: str
    sector: str
    note: str


DEFAULT_SECTOR_ROTATION: tuple[SectorRotationEntry, ...] = (
    SectorRotationEntry("HK", "tech", "China technology platforms, hardware, and semiconductor read-through."),
    SectorRotationEntry("US", "semiconductors", "AI infrastructure supply chain and capex sensitivity."),
    SectorRotationEntry("US", "energy", "Oil, LNG, services, and downstream demand transmission."),
    SectorRotationEntry("US", "banks", "Deposit cost, loan growth, capital markets, and credit-cycle read-through."),
    SectorRotationEntry("HK", "consumer", "China consumption, platform distribution, and discretionary demand."),
    SectorRotationEntry("US", "defense", "Prime contractors, mission systems, and aerospace supply chain."),
    SectorRotationEntry("HK", "internet platforms", "Platform economics, cloud, payments, and local services."),
)


def select_sector_rotation_entry(
    current_date: dt.date | None = None,
    rotation: tuple[SectorRotationEntry, ...] = DEFAULT_SECTOR_ROTATION,
) -> SectorRotationEntry:
    if not rotation:
        raise ValueError("Sector rotation cannot be empty.")
    day = current_date or dt.date.today()
    return rotation[day.toordinal() % len(rotation)]

