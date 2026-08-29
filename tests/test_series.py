"""PROBLEM.md §11 series / cattle / PV / homestead checks."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from src.generate_series import generate_series, heat_factor

ROOT = Path(__file__).resolve().parents[1]
STATION_PATH = ROOT / "data" / "wirra-bore.json"

# PROBLEM.md §9 — do not change without editing PROBLEM.md.
PHI = [
    0.012, 0.010, 0.008, 0.008, 0.012, 0.020,
    0.042, 0.055, 0.058, 0.054, 0.048, 0.044,
    0.040, 0.036, 0.055, 0.080, 0.100, 0.095,
    0.070, 0.050, 0.040, 0.030, 0.020, 0.013,
]


@pytest.fixture(scope="module")
def station() -> dict:
    return json.loads(STATION_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def series(station: dict) -> dict:
    return generate_series(station, scenario="wirra-summer-clear")


def test_phi_sums_to_one(station: dict) -> None:
    phi = station["phi_hourly"]
    assert phi == PHI
    assert abs(sum(PHI) - 1.0) < 1e-9
    assert abs(sum(phi) - 1.0) < 1e-9


def test_back_demand_all_zeros(series: dict) -> None:
    back = np.asarray(series["demand_kl_per_h"]["back"], dtype=float)
    assert back.shape == (48,)
    assert np.allclose(back, 0.0)


def test_cows_calves_daily_kl(station: dict, series: dict) -> None:
    north = np.asarray(series["demand_kl_per_h"]["north"][:24], dtype=float)
    h = np.asarray(series["heat_factor"][:24], dtype=float)
    expected = 220.0 * 70.0 * float(np.mean(h)) / 1000.0
    actual = float(north.sum())
    assert actual == pytest.approx(expected, rel=0.15)


def test_hour_16_is_peak_demand_stocked_paddocks(series: dict) -> None:
    stocked = ("north", "creek", "dam_paddock")
    for name in stocked:
        dem = np.asarray(series["demand_kl_per_h"][name], dtype=float)
        for day in range(2):
            day_dem = dem[day * 24 : (day + 1) * 24]
            assert day_dem[16] + 1e-12 >= day_dem.max()


def test_clear_day_pv_energy(series: dict) -> None:
    pv = np.asarray(series["pv_kw"], dtype=float)
    day0 = float(pv[:24].sum())
    assert 180.0 <= day0 <= 320.0


def test_homestead_daily_energy_and_cap(series: dict) -> None:
    load = np.asarray(series["homestead_kw"], dtype=float)
    assert load.max() <= 20.0 + 1e-12
    for day in range(2):
        energy = float(load[day * 24 : (day + 1) * 24].sum())
        assert 170.0 <= energy <= 230.0


def test_heat_factor_anchors() -> None:
    assert heat_factor(25.0) == 1.0
    assert heat_factor(10.0) == 1.0
    assert heat_factor(38.0) == 1.8
    assert heat_factor(50.0) == 1.8
    mid = heat_factor(31.5)
    assert mid == pytest.approx(1.4)


def test_horizon_and_timezone(series: dict, station: dict) -> None:
    assert series["horizon_hours"] == 48
    assert len(series["timestamps"]) == 48
    assert series["timestamps"][0].startswith("2026-01-16T00:00:00")
    assert "Australia/Sydney" in series["timezone"] or series["timestamps"][0].endswith("+11:00")
    assert series["timestamps"][0] == series["timestamps"][0]  # start-of-hour labels
    assert station["initial"]["soc_kwh"] == 36
    assert station["initial"]["dam_kl"] == 5500
    assert station["initial"]["header_kl"]["north"] == 15
