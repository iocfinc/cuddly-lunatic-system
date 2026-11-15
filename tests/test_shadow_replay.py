from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quant_researcher_desk.shadow_replay import ReplayTrade, compare_replay_sets


def test_shadow_replay_reports_improved_sharpe_and_alpha_against_underlying_baseline() -> None:
    old_trades = (
        ReplayTrade("US.OLD1", "old-a", (-0.10, -0.05, 0.02), (0.01, 0.01, 0.01)),
        ReplayTrade("US.OLD2", "old-b", (-0.08, -0.03, 0.01), (0.0, 0.01, 0.01)),
    )
    hardened_trades = (
        ReplayTrade("US.NEW1", "new-a", (0.04, 0.03, 0.02), (0.01, 0.01, 0.01)),
        ReplayTrade("US.NEW2", "new-b", (0.03, 0.02, 0.02), (0.0, 0.01, 0.01)),
    )

    comparison = compare_replay_sets(old_trades, hardened_trades)

    assert comparison.mode == "shadow_replay"
    assert comparison.old.trade_count == 2
    assert comparison.hardened.trade_count == 2
    assert comparison.hardened.alpha > comparison.old.alpha
    assert comparison.hardened.sharpe > comparison.old.sharpe
    assert comparison.alpha_improvement == pytest.approx(comparison.hardened.alpha - comparison.old.alpha)
