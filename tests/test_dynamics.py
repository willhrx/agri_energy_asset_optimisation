"""Shared dynamics helpers reproduce PROBLEM.md §6 exactly."""

from __future__ import annotations

import json
from pathlib import Path

from src.dynamics import step_battery, step_dam, step_header

ROOT = Path(__file__).resolve().parents[1]


def _station() -> dict:
    return json.loads((ROOT / "data" / "wirra-bore.json").read_text(encoding="utf-8"))


def test_battery_charge_and_discharge() -> None:
    st = _station()
    assert step_battery(36.0, 10.0, 0.0, st) == 36.0 + 0.95 * 10.0
    assert abs(step_battery(36.0, 0.0, 10.0, st) - (36.0 - 10.0 / 0.95)) < 1e-12


def test_battery_clips_envelope() -> None:
    st = _station()
    assert step_battery(9.0, 100.0, 0.0, st) == 57.0
    assert step_battery(9.0, 0.0, 100.0, st) == 9.0


def test_dam_balance_and_clips() -> None:
    st = _station()
    assert step_dam(5000.0, 36.0, 40.0, 1.0, st) == 4996.0
    assert step_dam(10500.0, 0.0, 0.0, 1.0, st) == 10000.0
    assert step_dam(900.0, 0.0, 0.0, 1.0, st) == 1000.0


def test_header_unmet_and_cap() -> None:
    w_next, extra = step_header(1.0, 0.0, 2.0, 0.0, 1.0, 20.0)
    assert w_next == 0.0
    assert extra == 1.0
    w_next, extra = step_header(19.5, 5.0, 0.0, 0.0, 1.0, 20.0)
    assert w_next == 20.0
    assert extra == 0.0


def test_header_uses_existing_unmet() -> None:
    w_next, extra = step_header(1.0, 0.0, 2.0, 0.5, 1.0, 20.0)
    assert w_next == 0.0
    assert extra == 0.0
