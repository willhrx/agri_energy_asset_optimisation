"""Dumb diesel baseline (PROBLEM.md §13).

No battery. PV may cover homestead when it is there, leftover is curtailed.
Diesel covers the residual in {0} ∪ [8, 24] kW. Pump only if the dam is in
the 1500 kL override band or a header would fail in 3 hours. Never charge.
"""

from __future__ import annotations

from typing import Any

from src.dispatch_greedy import (
    _bore_kl_per_h,
    _paddocks,
    headers_fail_next_3,
    pd_hour,
    release_water,
    select_bores,
)
from src.dynamics import step_dam, step_header


def allocate_dumb(
    homestead_kw: float,
    pv_avail: float,
    uA: int,
    uB: int,
    station: dict[str, Any],
) -> dict[str, float]:
    p = station["power"]
    g_min = float(p["diesel_kw_min"])
    g_max = float(p["diesel_kw_max"])
    bores = station["water"]["bores"]
    bore_kw = float(bores["bore_a"]["kw"]) * uA + float(bores["bore_b"]["kw"]) * uB
    load = homestead_kw + bore_kw
    pv_used = min(pv_avail, load)
    remain = load - pv_used
    diesel = 0.0
    dump = 0.0
    if remain > 1e-12:
        diesel = min(g_max, max(g_min, remain))
        if diesel + 1e-12 < remain:
            dump = remain - diesel
        else:
            dump = max(0.0, diesel - remain)
    return {
        "c_kw": 0.0,
        "d_kw": 0.0,
        "g_kw": float(diesel),
        "pv_used_kw": float(pv_used),
        "pv_curtailed_kw": float(pv_avail - pv_used),
        "dump_kw": float(dump),
        "bore_kw": float(bore_kw),
    }


def dispatch_dumb(station: dict[str, Any], series: dict[str, Any]) -> dict[str, Any]:
    paddocks = _paddocks(station)
    n = int(series["horizon_hours"])
    dt = float(station["timestep_hours"])
    demand = series["demand_kl_per_h"]
    pv = series["pv_kw"]
    load = series["homestead_kw"]
    timestamps = series["timestamps"]
    no_pump = set(int(h) for h in station["rules"]["no_pump_hours_local"])
    s_min = float(station["power"]["soc_min_frac"]) * float(station["power"]["battery_kwh"])

    S = float(station["initial"]["soc_kwh"])
    V = float(station["initial"]["dam_kl"])
    W = {p: float(station["initial"]["header_kl"][p]) for p in paddocks}
    override = float(station["rules"]["no_pump_override_if_dam_below_kl"])

    out: dict[str, Any] = {
        "policy": "dumb_diesel",
        "timestamps": list(timestamps),
        "uA": [],
        "uB": [],
        "c_kw": [],
        "d_kw": [],
        "g_kw": [],
        "pv_used_kw": [],
        "pv_curtailed_kw": [],
        "dump_kw": [],
        "f_kl": {p: [] for p in paddocks},
        "S_kwh": [],
        "V_kl": [],
        "W_kl": {p: [] for p in paddocks},
        "unmet_kl": {p: [] for p in paddocks},
        "S_kwh_end": [],
        "V_kl_end": [],
        "W_kl_end": {p: [] for p in paddocks},
    }

    for t in range(n):
        D = {p: float(demand[p][t]) for p in paddocks}
        f, unmet = release_water(V, W, D, station)
        hour_local = pd_hour(timestamps[t])
        # Dumber pump trigger than greedy: reserve-override or header failure only.
        need_pump = V < override or headers_fail_next_3(V, W, demand, t, station)
        uA, uB = select_bores(
            need_pump=need_pump,
            no_pump_hour=hour_local in no_pump,
            V=V,
            W=W,
            homestead_kw=float(load[t]),
            pv_avail=float(pv[t]),
            S=s_min,
            station=station,
        )
        power = allocate_dumb(float(load[t]), float(pv[t]), uA, uB, station)
        inflow = _bore_kl_per_h(station, "bore_a") * uA + _bore_kl_per_h(station, "bore_b") * uB
        v_next = step_dam(V, inflow, sum(f[p] for p in paddocks), dt, station)
        w_next = {}
        for p in paddocks:
            extra, w_next[p] = step_header(
                W[p], f[p], D[p], unmet[p], dt,
                float(station["water"]["paddocks"][p]["header_kl"]),
            )
            unmet[p] += extra

        out["uA"].append(int(uA))
        out["uB"].append(int(uB))
        out["c_kw"].append(0.0)
        out["d_kw"].append(0.0)
        out["g_kw"].append(power["g_kw"])
        out["pv_used_kw"].append(power["pv_used_kw"])
        out["pv_curtailed_kw"].append(power["pv_curtailed_kw"])
        out["dump_kw"].append(power["dump_kw"])
        out["S_kwh"].append(S)
        out["V_kl"].append(V)
        out["S_kwh_end"].append(S)
        out["V_kl_end"].append(v_next)
        for p in paddocks:
            out["f_kl"][p].append(f[p])
            out["W_kl"][p].append(W[p])
            out["W_kl_end"][p].append(w_next[p])
            out["unmet_kl"][p].append(unmet[p])
        V, W = v_next, w_next

    return out
