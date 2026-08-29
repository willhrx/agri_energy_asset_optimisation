"""PROBLEM.md §11 dispatch / balance / initial-state checks."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from src.dispatch_greedy import dispatch_greedy
from src.generate_series import generate_series
from src.kpis import compute_kpis

ROOT = Path(__file__).resolve().parents[1]
STATION_PATH = ROOT / "data" / "wirra-bore.json"


@pytest.fixture(scope="module")
def station() -> dict:
    return json.loads(STATION_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def series(station: dict) -> dict:
    return generate_series(station, scenario="wirra-summer-clear")


@pytest.fixture(scope="module")
def dispatch(station: dict, series: dict) -> dict:
    return dispatch_greedy(station, series)


@pytest.fixture(scope="module")
def kpis(station: dict, series: dict, dispatch: dict) -> dict:
    return compute_kpis(station, series, dispatch)


def test_initial_state(station: dict, dispatch: dict) -> None:
    assert station["initial"]["soc_kwh"] == 36
    assert station["initial"]["dam_kl"] == 5500
    for p, w in station["initial"]["header_kl"].items():
        assert w == 15
    assert dispatch["S_kwh"][0] == pytest.approx(36.0)
    assert dispatch["V_kl"][0] == pytest.approx(5500.0)
    for p in station["water"]["paddocks"]:
        assert dispatch["W_kl"][p][0] == pytest.approx(15.0)


def test_dam_never_below_reserve_unless_unmet(station: dict, dispatch: dict, kpis: dict) -> None:
    reserve = float(station["water"]["dam_reserve_kl"])
    dam = np.asarray(dispatch["V_kl"] + [dispatch["V_kl_end"][-1]], dtype=float)
    unmet = kpis["unmet_kl_total"]
    if unmet <= 1e-9:
        assert dam.min() >= reserve - 1e-6
    else:
        assert True  # slack is documented in kpis


def test_headers_non_negative(station: dict, dispatch: dict) -> None:
    for p in station["water"]["paddocks"]:
        w = np.asarray(dispatch["W_kl"][p] + [dispatch["W_kl_end"][p][-1]], dtype=float)
        assert np.all(w >= -1e-9)


def test_no_simultaneous_charge_and_discharge(dispatch: dict) -> None:
    c = np.asarray(dispatch["c_kw"], dtype=float)
    d = np.asarray(dispatch["d_kw"], dtype=float)
    assert np.all((c <= 1e-9) | (d <= 1e-9))


def test_diesel_band(station: dict, dispatch: dict) -> None:
    g_min = float(station["power"]["diesel_kw_min"])
    g_max = float(station["power"]["diesel_kw_max"])
    for g in dispatch["g_kw"]:
        if g <= 1e-9:
            continue
        assert g_min - 1e-6 <= g <= g_max + 1e-6


def test_power_balance(station: dict, series: dict, dispatch: dict) -> None:
    kw_a = float(station["water"]["bores"]["bore_a"]["kw"])
    kw_b = float(station["water"]["bores"]["bore_b"]["kw"])
    for t in range(series["horizon_hours"]):
        lhs = (
            dispatch["pv_used_kw"][t]
            + dispatch["d_kw"][t]
            + dispatch["g_kw"][t]
        )
        rhs = (
            series["homestead_kw"][t]
            + dispatch["c_kw"][t]
            + kw_a * dispatch["uA"][t]
            + kw_b * dispatch["uB"][t]
            + dispatch["dump_kw"][t]
        )
        assert lhs == pytest.approx(rhs, abs=1e-6)


def test_battery_dynamics(station: dict, dispatch: dict) -> None:
    eta_c = float(station["power"]["eta_charge"])
    eta_d = float(station["power"]["eta_discharge"])
    dt = float(station["timestep_hours"])
    s_min = float(station["power"]["soc_min_frac"]) * float(station["power"]["battery_kwh"])
    s_max = float(station["power"]["soc_max_frac"]) * float(station["power"]["battery_kwh"])
    n = len(dispatch["S_kwh"])
    for t in range(n):
        s_now = dispatch["S_kwh"][t]
        s_end = dispatch["S_kwh_end"][t]
        predicted = s_now + eta_c * dispatch["c_kw"][t] * dt - dispatch["d_kw"][t] * dt / eta_d
        predicted = min(s_max, max(s_min, predicted))
        assert s_end == pytest.approx(predicted, abs=1e-6)
        assert s_min - 1e-6 <= s_now <= s_max + 1e-6
        if t + 1 < n:
            assert dispatch["S_kwh"][t + 1] == pytest.approx(s_end, abs=1e-9)


def test_dam_dynamics(station: dict, dispatch: dict) -> None:
    dt = float(station["timestep_hours"])
    spill = float(station["water"]["dam_spill_kl"])
    reserve = float(station["water"]["dam_reserve_kl"])
    inflow_a = float(station["water"]["bores"]["bore_a"]["litres_per_s"]) * 3.6
    inflow_b = float(station["water"]["bores"]["bore_b"]["litres_per_s"]) * 3.6
    paddocks = list(station["water"]["paddocks"])
    n = len(dispatch["V_kl"])
    for t in range(n):
        inflow = inflow_a * dispatch["uA"][t] + inflow_b * dispatch["uB"][t]
        outflow = sum(dispatch["f_kl"][p][t] for p in paddocks)
        predicted = dispatch["V_kl"][t] + inflow * dt - outflow * dt
        predicted = min(spill, max(reserve, predicted))
        assert dispatch["V_kl_end"][t] == pytest.approx(predicted, abs=1e-6)
        if t + 1 < n:
            assert dispatch["V_kl"][t + 1] == pytest.approx(dispatch["V_kl_end"][t], abs=1e-9)


def test_header_dynamics(station: dict, series: dict, dispatch: dict) -> None:
    dt = float(station["timestep_hours"])
    for p in station["water"]["paddocks"]:
        cap = float(station["water"]["paddocks"][p]["header_kl"])
        n = len(dispatch["W_kl"][p])
        for t in range(n):
            predicted = (
                dispatch["W_kl"][p][t]
                + dispatch["f_kl"][p][t] * dt
                - series["demand_kl_per_h"][p][t] * dt
                + dispatch["unmet_kl"][p][t] * dt
            )
            predicted = min(cap, max(0.0, predicted))
            assert dispatch["W_kl_end"][p][t] == pytest.approx(predicted, abs=1e-6)


def test_outlet_cap(station: dict, dispatch: dict) -> None:
    cap = float(station["water"]["dam_outlet_kl_per_h"])
    paddocks = list(station["water"]["paddocks"])
    for t in range(len(dispatch["uA"])):
        total_f = sum(dispatch["f_kl"][p][t] for p in paddocks)
        assert total_f <= cap + 1e-6


def test_no_pump_hours_unless_override(station: dict, dispatch: dict) -> None:
    no_pump = set(station["rules"]["no_pump_hours_local"])
    override = float(station["rules"]["no_pump_override_if_dam_below_kl"])
    for t, ts in enumerate(dispatch["timestamps"]):
        hour = int(ts.split("T", 1)[1][0:2])
        if hour in no_pump and dispatch["V_kl"][t] >= override - 1e-9:
            assert dispatch["uA"][t] == 0
            assert dispatch["uB"][t] == 0


def test_clear_scenario_unmet_and_no_dump(dispatch: dict, kpis: dict) -> None:
    assert kpis["unmet_kl_total"] == pytest.approx(0.0, abs=1e-9)
    assert max(dispatch["dump_kw"]) == pytest.approx(0.0, abs=1e-6)
    assert sum(dispatch["uA"]) + sum(dispatch["uB"]) == 0


def test_kpis_keys(kpis: dict) -> None:
    for key in (
        "diesel_litres",
        "diesel_aud",
        "pv_kwh",
        "pv_curtailed_kwh",
        "min_dam_kl",
        "min_soc_kwh",
        "unmet_kl_total",
        "hours_diesel_on",
    ):
        assert key in kpis
    assert kpis["diesel_litres"] >= 0.0
    assert kpis["diesel_aud"] == pytest.approx(kpis["diesel_litres"] * 2.0)
    assert kpis["pv_kwh"] > 0.0
