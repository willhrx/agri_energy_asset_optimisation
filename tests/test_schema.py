"""Station schema validation: wirra-bore validates clean; mutations are detected."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from src.site_schema import validate_station

ROOT = Path(__file__).resolve().parents[1]


def _station() -> dict:
    return json.loads((ROOT / "data" / "wirra-bore.json").read_text(encoding="utf-8"))


def test_default_station_is_clean() -> None:
    assert validate_station(_station()) == []


def test_phi_break_detected() -> None:
    s = _station()
    s["phi_hourly"][0] = 0.5
    assert any("phi_hourly" in e for e in validate_station(s))


def test_missing_power_field_detected() -> None:
    s = _station()
    del s["power"]["battery_kwh"]
    assert any("power.battery_kwh" in e for e in validate_station(s))


def test_bad_initial_dam_detected() -> None:
    s = _station()
    s["initial"]["dam_kl"] = 500.0
    assert any("initial.dam_kl" in e for e in validate_station(s))


def test_header_key_mismatch_detected() -> None:
    s = _station()
    s["initial"]["header_kl"]["ghost"] = 15.0
    assert any("initial.header_kl" in e for e in validate_station(s))


def test_zero_azimuth_is_valid() -> None:
    # Regression: north-facing arrays have azimuth 0; it must not trip the >0 check.
    s = _station()
    s["power"]["pv_azimuth_deg"] = 0.0
    s["power"]["pv_tilt_deg"] = 0.0
    assert validate_station(s) == []


def test_out_of_range_tilt_and_azimuth_detected() -> None:
    s = _station()
    s["power"]["pv_tilt_deg"] = 95.0
    s["power"]["pv_azimuth_deg"] = 400.0
    errs = validate_station(s)
    assert any("pv_tilt_deg" in e for e in errs)
    assert any("pv_azimuth_deg" in e for e in errs)


def test_unknown_placement_mob_detected() -> None:
    s = copy.deepcopy(_station())
    s["placement"][0]["paddock_mobs"]["north"].append("ghost_mob")
    assert any("unknown mob" in e for e in validate_station(s))


def test_soc_outside_envelope_detected() -> None:
    s = _station()
    s["initial"]["soc_kwh"] = 100.0
    assert any("initial.soc_kwh" in e for e in validate_station(s))
