"""Dumb diesel baseline vs greedy / MILP."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from src.compare import compare_kpis
from src.dispatch_dumb import dispatch_dumb
from src.dispatch_greedy import dispatch_greedy
from src.dispatch_opt import dispatch_opt
from src.generate_series import generate_series
from src.kpis import compute_kpis

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def station() -> dict:
    return json.loads((ROOT / "data" / "wirra-bore.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def series(station: dict) -> dict:
    return generate_series(station, scenario="wirra-summer-clear")


@pytest.fixture(scope="module")
def dumb(station: dict, series: dict) -> dict:
    return dispatch_dumb(station, series)


@pytest.fixture(scope="module")
def greedy(station: dict, series: dict) -> dict:
    return dispatch_greedy(station, series)


@pytest.fixture(scope="module")
def opt(station: dict, series: dict) -> dict:
    return dispatch_opt(station, series)


def test_dumb_no_battery(dumb: dict, station: dict) -> None:
    assert dumb["policy"] == "dumb_diesel"
    assert np.allclose(dumb["c_kw"], 0.0)
    assert np.allclose(dumb["d_kw"], 0.0)
    s0 = float(station["initial"]["soc_kwh"])
    assert np.allclose(dumb["S_kwh"], s0)
    assert np.allclose(dumb["S_kwh_end"], s0)


def test_dumb_uses_more_diesel_than_greedy(station: dict, series: dict, dumb: dict, greedy: dict) -> None:
    kd = compute_kpis(station, series, dumb)
    kg = compute_kpis(station, series, greedy)
    assert kd["diesel_aud"] >= kg["diesel_aud"] - 1e-6
    assert kd["hours_diesel_on"] >= kg["hours_diesel_on"]


def test_dumb_power_balance(station: dict, series: dict, dumb: dict) -> None:
    kw_a = float(station["water"]["bores"]["bore_a"]["kw"])
    kw_b = float(station["water"]["bores"]["bore_b"]["kw"])
    for t in range(series["horizon_hours"]):
        lhs = dumb["pv_used_kw"][t] + dumb["d_kw"][t] + dumb["g_kw"][t]
        rhs = (
            series["homestead_kw"][t]
            + dumb["c_kw"][t]
            + kw_a * dumb["uA"][t]
            + kw_b * dumb["uB"][t]
            + dumb["dump_kw"][t]
        )
        assert lhs == pytest.approx(rhs, abs=1e-6)


def test_ordering_dumb_greedy_opt(station: dict, series: dict, dumb: dict, greedy: dict, opt: dict) -> None:
    kd = compute_kpis(station, series, dumb)
    kg = compute_kpis(station, series, greedy)
    ko = compute_kpis(station, series, opt)
    cmp = compare_kpis(kg, ko, dumb=kd)
    assert cmp["greedy_beats_or_ties_dumb"]
    assert cmp["opt_beats_or_ties_greedy"]
    assert ko["objective_aud"] <= kd["objective_aud"] + 1e-2
