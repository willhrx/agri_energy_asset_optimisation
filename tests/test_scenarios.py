"""Sky / dry-dam / heat overlays. Phi table is not modified."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from src.dispatch_greedy import dispatch_greedy
from src.dispatch_opt import dispatch_opt
from src.generate_series import generate_series
from src.kpis import compute_kpis
from src.scenarios import overlay_station

ROOT = Path(__file__).resolve().parents[1]
PHI = [
    0.012, 0.010, 0.008, 0.008, 0.012, 0.020,
    0.042, 0.055, 0.058, 0.054, 0.048, 0.044,
    0.040, 0.036, 0.055, 0.080, 0.100, 0.095,
    0.070, 0.050, 0.040, 0.030, 0.020, 0.013,
]


@pytest.fixture(scope="module")
def station() -> dict:
    return json.loads((ROOT / "data" / "wirra-bore.json").read_text(encoding="utf-8"))


def test_phi_unchanged(station: dict) -> None:
    assert station["phi_hourly"] == PHI


def test_overcast_pv_below_clear(station: dict) -> None:
    clear = generate_series(station, scenario="wirra-summer-clear", sky="clear")
    over = generate_series(station, scenario="wirra-summer-overcast", sky="overcast")
    mixed = generate_series(station, scenario="wirra-summer-mixed", sky="mixed")
    e_clear = float(np.sum(clear["pv_kw"][:24]))
    e_over = float(np.sum(over["pv_kw"][:24]))
    e_mix0 = float(np.sum(mixed["pv_kw"][:24]))
    e_mix1 = float(np.sum(mixed["pv_kw"][24:]))
    assert 180.0 <= e_clear <= 320.0
    assert e_over < e_clear * 0.6
    assert 20.0 <= e_over <= 160.0
    assert e_mix0 == pytest.approx(e_clear, rel=0.05)
    assert e_mix1 < e_mix0


def test_heat_raises_demand(station: dict) -> None:
    cool = generate_series(station, scenario="wirra-heat-base", temp_max_c=37.0)
    hot = generate_series(station, scenario="wirra-heat", temp_max_c=42.0)
    n = np.sum(cool["demand_kl_per_h"]["north"])
    h = np.sum(hot["demand_kl_per_h"]["north"])
    assert h > n
    assert max(hot["heat_factor"]) == pytest.approx(1.8)


def test_dry_dam_pumps(station: dict) -> None:
    dry = overlay_station(station, dam_kl=1800.0, scenario="wirra-dry")
    series = generate_series(dry, scenario="wirra-dry")
    greedy = dispatch_greedy(dry, series)
    opt = dispatch_opt(dry, series)
    kg = compute_kpis(dry, series, greedy)
    ko = compute_kpis(dry, series, opt)
    assert greedy["V_kl"][0] == pytest.approx(1800.0)
    assert kg["water_pumped_kl"] + ko["water_pumped_kl"] > 0.0
    assert ko["unmet_kl_total"] == pytest.approx(0.0, abs=1e-4)
    assert ko["objective_aud"] <= kg["objective_aud"] + 1e-2
    assert min(greedy["V_kl"] + [greedy["V_kl_end"][-1]]) >= 1000.0 - 1e-3
