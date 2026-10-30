"""Grid archetype (PROBLEM-AU-NEM.md): schema + series checks for trangie-grid."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from src.generate_series import generate_series
from src.site_schema import validate_station

ROOT = Path(__file__).resolve().parents[1]
GRID_PATH = ROOT / "data" / "trangie-grid.json"


def _grid() -> dict:
    return json.loads(GRID_PATH.read_text(encoding="utf-8"))


def test_grid_station_validates_clean() -> None:
    assert validate_station(_grid()) == []


def test_off_grid_station_has_no_market_or_grid_fields() -> None:
    wirra = json.loads((ROOT / "data" / "wirra-bore.json").read_text(encoding="utf-8"))
    assert "market" not in wirra
    assert "grid_import_kw_max" not in wirra["power"]


def test_grid_station_must_not_define_diesel_fields() -> None:
    s = _grid()
    s["power"]["diesel_kw_max"] = 24.0
    assert any("must not define diesel" in e for e in validate_station(s))


def test_off_grid_station_must_not_define_grid_fields() -> None:
    wirra = json.loads((ROOT / "data" / "wirra-bore.json").read_text(encoding="utf-8"))
    wirra["power"]["grid_import_kw_max"] = 30.0
    assert any("must not define grid" in e for e in validate_station(wirra))


def test_grid_station_requires_market_block() -> None:
    s = _grid()
    del s["market"]
    assert any(e == "market missing for grid-connected station" for e in validate_station(s))


def test_off_grid_station_with_market_is_rejected() -> None:
    wirra = json.loads((ROOT / "data" / "wirra-bore.json").read_text(encoding="utf-8"))
    wirra["market"] = {
        "type": "au_nem_tou",
        "import_tariff_c_per_kwh": {"offpeak": 18, "shoulder": 38, "peak": 62},
        "tou_hours": {"offpeak": [22, 7], "shoulder": [7, 17], "peak": [17, 22]},
        "feed_in_c_per_kwh": 8,
    }
    assert any("requires grid power fields" in e for e in validate_station(wirra))


def test_tou_windows_must_tile_day() -> None:
    s = _grid()
    s["market"]["tou_hours"]["peak"] = [17, 21]  # leaves hour 21 uncovered
    assert any("tile the 24-hour day" in e for e in validate_station(s))


def test_tariff_names_are_exact() -> None:
    s = _grid()
    s["market"]["import_tariff_c_per_kwh"]["superpeak"] = 99.0
    assert any("offpeak/shoulder/peak" in e for e in validate_station(s))


def test_grid_objective_extra_diesel_price_is_tolerated() -> None:
    s = _grid()
    s["objective"]["diesel_aud_per_litre"] = 2.0
    errors = validate_station(s)
    assert not any("diesel_aud_per_litre missing" in e for e in errors)


def test_grid_series_generation() -> None:
    series = generate_series(_grid(), scenario="trangie-summer-clear")
    assert series["horizon_hours"] == 48
    assert series["timestamps"][0].startswith("2026-02-13T00:00:00")
    pv = np.asarray(series["pv_kw"], dtype=float)
    day0 = float(pv[:24].sum())
    assert 180.0 <= day0 <= 320.0
    back = np.asarray(series["demand_kl_per_h"]["back"], dtype=float)
    assert np.allclose(back, 0.0)
    heat = np.asarray(series["heat_factor"], dtype=float)
    expected = 220.0 * 70.0 * float(np.mean(heat[:24])) / 1000.0
    north = np.asarray(series["demand_kl_per_h"]["north"][:24], dtype=float)
    assert float(north.sum()) == pytest.approx(expected, rel=0.15)


def test_grid_schema_errors_surface_in_series_path() -> None:
    s = _grid()
    s["phi_hourly"][0] = 0.5
    assert any("phi_hourly" in e for e in validate_station(s))
