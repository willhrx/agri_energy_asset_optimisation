"""Sprint 2: MILP vs greedy on the same series."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from src.compare import compare_kpis
from src.dispatch_greedy import dispatch_greedy
from src.dispatch_opt import dispatch_opt
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
def greedy(station: dict, series: dict) -> dict:
    return dispatch_greedy(station, series)


@pytest.fixture(scope="module")
def opt(station: dict, series: dict) -> dict:
    return dispatch_opt(station, series)


@pytest.fixture(scope="module")
def kpis_g(station: dict, series: dict, greedy: dict) -> dict:
    return compute_kpis(station, series, greedy)


@pytest.fixture(scope="module")
def kpis_o(station: dict, series: dict, opt: dict) -> dict:
    return compute_kpis(station, series, opt)


def test_opt_solves(opt: dict) -> None:
    assert opt["solver_status"] == "Optimal"
    assert opt["policy"] == "milp"
    assert len(opt["uA"]) == 48


def test_same_series_horizon(series: dict, greedy: dict, opt: dict) -> None:
    assert greedy["timestamps"] == opt["timestamps"] == series["timestamps"]


def test_opt_objective_beats_or_ties_greedy(kpis_g: dict, kpis_o: dict) -> None:
    cmp = compare_kpis(kpis_g, kpis_o)
    assert cmp["opt_beats_or_ties_greedy"]
    assert kpis_o["objective_aud"] <= kpis_g["objective_aud"] + 1e-2


def test_opt_unmet_zero_or_documented(kpis_o: dict) -> None:
    if kpis_o["unmet_kl_total"] > 1e-6:
        assert kpis_o.get("unmet_hours")
    else:
        assert kpis_o["unmet_kl_total"] == pytest.approx(0.0, abs=1e-6)


def test_opt_power_balance(station: dict, series: dict, opt: dict) -> None:
    kw_a = float(station["water"]["bores"]["bore_a"]["kw"])
    kw_b = float(station["water"]["bores"]["bore_b"]["kw"])
    for t in range(series["horizon_hours"]):
        lhs = opt["pv_used_kw"][t] + opt["d_kw"][t] + opt["g_kw"][t]
        rhs = (
            series["homestead_kw"][t]
            + opt["c_kw"][t]
            + kw_a * opt["uA"][t]
            + kw_b * opt["uB"][t]
            + opt["dump_kw"][t]
        )
        assert lhs == pytest.approx(rhs, abs=5e-3)


def test_opt_battery_dynamics(station: dict, opt: dict) -> None:
    eta_c = float(station["power"]["eta_charge"])
    eta_d = float(station["power"]["eta_discharge"])
    dt = float(station["timestep_hours"])
    s_min = float(station["power"]["soc_min_frac"]) * float(station["power"]["battery_kwh"])
    s_max = float(station["power"]["soc_max_frac"]) * float(station["power"]["battery_kwh"])
    assert opt["S_kwh"][0] == pytest.approx(36.0, abs=1e-4)
    for t in range(len(opt["S_kwh"])):
        predicted = opt["S_kwh"][t] + eta_c * opt["c_kw"][t] * dt - opt["d_kw"][t] * dt / eta_d
        predicted = min(s_max, max(s_min, predicted))
        assert opt["S_kwh_end"][t] == pytest.approx(predicted, abs=5e-3)
        assert s_min - 1e-3 <= opt["S_kwh"][t] <= s_max + 1e-3


def test_opt_diesel_band_and_no_dual(station: dict, opt: dict) -> None:
    g_min = float(station["power"]["diesel_kw_min"])
    g_max = float(station["power"]["diesel_kw_max"])
    c = np.asarray(opt["c_kw"])
    d = np.asarray(opt["d_kw"])
    assert np.all((c <= 1e-3) | (d <= 1e-3))
    for g in opt["g_kw"]:
        if g <= 1e-3:
            continue
        assert g_min - 5e-3 <= g <= g_max + 5e-3


def test_opt_no_pump_hours(station: dict, opt: dict) -> None:
    no_pump = set(station["rules"]["no_pump_hours_local"])
    override = float(station["rules"]["no_pump_override_if_dam_below_kl"])
    for t, ts in enumerate(opt["timestamps"]):
        hour = int(ts.split("T", 1)[1][0:2])
        if hour in no_pump and opt["V_kl"][t] >= override - 1e-6:
            assert opt["uA"][t] == 0
            assert opt["uB"][t] == 0


def test_opt_dam_and_headers(station: dict, series: dict, opt: dict) -> None:
    reserve = float(station["water"]["dam_reserve_kl"])
    dam = np.asarray(opt["V_kl"] + [opt["V_kl_end"][-1]])
    if sum(sum(opt["unmet_kl"][p]) for p in station["water"]["paddocks"]) <= 1e-6:
        assert dam.min() >= reserve - 1e-3
    assert opt["V_kl"][0] == pytest.approx(5500.0, abs=1e-3)
    cap = float(station["water"]["dam_outlet_kl_per_h"])
    paddocks = list(station["water"]["paddocks"])
    dt = float(station["timestep_hours"])
    inflow_a = float(station["water"]["bores"]["bore_a"]["litres_per_s"]) * 3.6
    inflow_b = float(station["water"]["bores"]["bore_b"]["litres_per_s"]) * 3.6
    for t in range(len(opt["uA"])):
        assert sum(opt["f_kl"][p][t] for p in paddocks) <= cap + 1e-3
        inflow = inflow_a * opt["uA"][t] + inflow_b * opt["uB"][t]
        outflow = sum(opt["f_kl"][p][t] for p in paddocks)
        predicted = opt["V_kl"][t] + inflow * dt - outflow * dt
        predicted = min(float(station["water"]["dam_spill_kl"]), max(reserve, predicted))
        assert opt["V_kl_end"][t] == pytest.approx(predicted, abs=5e-3)
        for p in paddocks:
            assert opt["W_kl"][p][t] >= -1e-6
            pred_w = (
                opt["W_kl"][p][t]
                + opt["f_kl"][p][t] * dt
                - series["demand_kl_per_h"][p][t] * dt
                + opt["unmet_kl"][p][t] * dt
            )
            cap_h = float(station["water"]["paddocks"][p]["header_kl"])
            pred_w = min(cap_h, max(0.0, pred_w))
            assert opt["W_kl_end"][p][t] == pytest.approx(pred_w, abs=5e-3)
