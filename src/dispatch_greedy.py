"""Greedy dispatch baseline for wirra-bore (sprint 1).

Policy (not optimal; approximates PROBLEM.md §8):

1. Meet homestead from PV, then battery above SoC min, then diesel.
2. Release from dam to headers to meet demand D and keep headers ≥ 30% if
   the dam can do so without breaching the 1 ML reserve or the 40 kL/h outlet.
3. If dam < 2500 kL, or dam→header releases cannot keep troughs ≥ 0 over the
   next 3 hours: run the cheapest feasible bore(s) that fit remaining
   PV + battery + diesel. Honour no-pump hours 11–15 unless dam < 1500 kL.
   Bore B is cheaper (kWh per kL) than A; both run only when dam < 1500 kL
   or a single bore cannot cover the trigger. Diesel is 0 or [8, 24] kW.
4. Charge the battery with leftover PV. Never start diesel in order to charge.
   If diesel is already on for load and the 8 kW floor creates a surplus that
   cannot be absorbed by a bore, incidental charge may close the power
   balance (last resort). Any leftover PV after charge is curtailed.
5. Do not start a bore if it would require diesel AND dam > 4000 kL AND
   all headers > 8 kL.

Troughs are not run negative: unmet slack s_p,t is recorded and W is held at 0.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.dynamics import step_battery, step_dam, step_header

# PROBLEM.md §8 greedy policy thresholds. Named constants, not JSON fields:
# if a field is not in data/wirra-bore.json, it does not exist.
DAM_PUMP_TRIGGER_KL = 2500.0        # rule 3: pump if dam below this
DAM_NO_BORE_WITH_DIESEL_KL = 4000.0  # rule 5: don't start diesel-fed bore above this
HEADER_SAFE_KL = 8.0                # rule 5: ... and all headers above this
HEADER_TARGET_FRAC = 0.30           # rule 2: keep headers >= 30% if dam allows


def _paddocks(station: dict[str, Any]) -> list[str]:
    return list(station["water"]["paddocks"].keys())


def _bore_kw(station: dict[str, Any], name: str) -> float:
    return float(station["water"]["bores"][name]["kw"])


def _bore_kl_per_h(station: dict[str, Any], name: str) -> float:
    return float(station["water"]["bores"][name]["litres_per_s"]) * 3.6


def release_water(
    V: float,
    W: dict[str, float],
    D: dict[str, float],
    station: dict[str, Any],
) -> tuple[dict[str, float], dict[str, float]]:
    """Dam → headers. Meet D first, then 30% header target. Reserve is sacred."""
    paddocks = _paddocks(station)
    reserve = float(station["water"]["dam_reserve_kl"])
    outlet = float(station["water"]["dam_outlet_kl_per_h"])
    header_cap = {p: float(station["water"]["paddocks"][p]["header_kl"]) for p in paddocks}
    target_frac = HEADER_TARGET_FRAC

    available = min(outlet, max(0.0, V - reserve))
    f = {p: 0.0 for p in paddocks}
    unmet = {p: 0.0 for p in paddocks}

    need1 = {}
    for p in paddocks:
        cover = max(0.0, D[p] - W[p])
        max_f = max(0.0, header_cap[p] - W[p] + D[p])
        need1[p] = min(cover, max_f)

    total1 = sum(need1.values())
    if total1 <= available + 1e-12:
        for p in paddocks:
            f[p] = need1[p]
        left = available - total1
    elif total1 > 0:
        scale = available / total1
        for p in paddocks:
            f[p] = need1[p] * scale
        left = 0.0
    else:
        left = available

    for p in paddocks:
        have = W[p] + f[p]
        if have + 1e-12 < D[p]:
            unmet[p] = D[p] - have

    if left > 1e-12:
        need2 = {}
        for p in paddocks:
            w_after = W[p] + f[p] - D[p] + unmet[p]
            target = target_frac * header_cap[p]
            extra = max(0.0, target - w_after)
            max_more = max(0.0, header_cap[p] - w_after)
            need2[p] = min(extra, max_more)
        total2 = sum(need2.values())
        if total2 <= left + 1e-12:
            for p in paddocks:
                f[p] += need2[p]
        elif total2 > 0:
            scale = left / total2
            for p in paddocks:
                f[p] += need2[p] * scale

    return f, unmet


def headers_fail_next_3(
    V: float,
    W: dict[str, float],
    demand: dict[str, list[float]],
    t: int,
    station: dict[str, Any],
) -> bool:
    """True if dam→header releases cannot keep troughs non-negative over 3 hours (no pumping)."""
    paddocks = _paddocks(station)
    n = len(next(iter(demand.values())))
    v = V
    w = dict(W)
    spill = float(station["water"]["dam_spill_kl"])
    reserve = float(station["water"]["dam_reserve_kl"])
    dt = float(station["timestep_hours"])
    for k in range(3):
        if t + k >= n:
            break
        D = {p: float(demand[p][t + k]) for p in paddocks}
        f, unmet = release_water(v, w, D, station)
        if any(u > 1e-9 for u in unmet.values()):
            return True
        v = v - sum(f[p] for p in paddocks) * dt
        v = min(spill, max(reserve, v))
        for p in paddocks:
            w[p] = max(0.0, w[p] + f[p] * dt - D[p] * dt + unmet[p] * dt)
    return False


def _power_room(
    homestead_kw: float,
    pv_avail: float,
    S: float,
    station: dict[str, Any],
) -> dict[str, float]:
    """Provisional homestead allocation; remaining PV / discharge / diesel for bores."""
    p = station["power"]
    dt = float(station["timestep_hours"])
    s_min = float(p["soc_min_frac"]) * float(p["battery_kwh"])
    batt_kw = float(p["battery_kw"])
    eta_d = float(p["eta_discharge"])
    g_min = float(p["diesel_kw_min"])
    g_max = float(p["diesel_kw_max"])

    max_d = min(batt_kw, max(0.0, (S - s_min) * eta_d / dt))
    pv_left = pv_avail
    discharge = 0.0
    diesel = 0.0

    need = homestead_kw
    take = min(pv_left, need)
    pv_left -= take
    need -= take

    take = min(max_d - discharge, need)
    discharge += take
    need -= take

    if need > 1e-12:
        diesel = min(g_max, max(g_min, need))
        diesel_surplus = max(0.0, diesel - need)
        need = 0.0
    else:
        diesel_surplus = 0.0

    return {
        "pv_left": pv_left,
        "discharge": discharge,
        "max_discharge": max_d,
        "diesel": diesel,
        "diesel_surplus": diesel_surplus,
        "g_min": g_min,
        "g_max": g_max,
        "batt_left": max(0.0, max_d - discharge),
    }


def _bore_feasible(kw: float, room: dict[str, float], V: float, W: dict[str, float]) -> bool:
    if kw <= 1e-12:
        return True
    free = room["pv_left"] + room["batt_left"] + room["diesel_surplus"]
    diesel_need = max(0.0, kw - free)
    g = room["diesel"]
    g_max = room["g_max"]
    g_min = room["g_min"]
    if diesel_need > 1e-12:
        if g > 1e-12:
            if g + diesel_need > g_max + 1e-9:
                return False
        else:
            proposed = diesel_need
            if proposed < g_min:
                proposed = g_min
            if proposed > g_max + 1e-9:
                return False
            # diesel min bump: remaining load after free power must be serveable
            if kw > free + g_max + 1e-9:
                return False
        requires_diesel = True
    else:
        requires_diesel = False

    if requires_diesel and V > DAM_NO_BORE_WITH_DIESEL_KL and all(W[p] > HEADER_SAFE_KL for p in W):
        return False
    return True


def select_bores(
    need_pump: bool,
    no_pump_hour: bool,
    V: float,
    W: dict[str, float],
    homestead_kw: float,
    pv_avail: float,
    S: float,
    station: dict[str, Any],
) -> tuple[int, int]:
    if not need_pump:
        return 0, 0
    override_kl = float(station["rules"]["no_pump_override_if_dam_below_kl"])
    if no_pump_hour and V >= override_kl - 1e-12:
        return 0, 0

    room = _power_room(homestead_kw, pv_avail, S, station)
    kw_a = _bore_kw(station, "bore_a")
    kw_b = _bore_kw(station, "bore_b")

    # B is cheaper kWh/kL. Run both when the dam is in the override band.
    if V < override_kl:
        order = [(1, 1), (0, 1), (1, 0)]
    else:
        order = [(0, 1), (1, 0), (1, 1)]

    for uA, uB in order:
        kw = kw_a * uA + kw_b * uB
        if _bore_feasible(kw, room, V, W):
            return uA, uB
    return 0, 0


def allocate_power(
    homestead_kw: float,
    pv_avail: float,
    S: float,
    uA: int,
    uB: int,
    station: dict[str, Any],
) -> dict[str, float]:
    """Serve homestead+bores from PV, battery, then diesel; charge leftover PV only."""
    p = station["power"]
    dt = float(station["timestep_hours"])
    s_min = float(p["soc_min_frac"]) * float(p["battery_kwh"])
    s_max = float(p["soc_max_frac"]) * float(p["battery_kwh"])
    batt_kw = float(p["battery_kw"])
    eta_c = float(p["eta_charge"])
    eta_d = float(p["eta_discharge"])
    g_min = float(p["diesel_kw_min"])
    g_max = float(p["diesel_kw_max"])
    bore_kw = _bore_kw(station, "bore_a") * uA + _bore_kw(station, "bore_b") * uB

    max_d = min(batt_kw, max(0.0, (S - s_min) * eta_d / dt))
    max_c = min(batt_kw, max(0.0, (s_max - S) / (eta_c * dt)))

    load = homestead_kw + bore_kw
    pv_to_load = min(pv_avail, load)
    pv_left = pv_avail - pv_to_load
    remain = load - pv_to_load

    charge = 0.0
    discharge = 0.0
    diesel = 0.0
    dump = 0.0

    if remain <= max_d + 1e-12:
        discharge = max(0.0, remain)
        if discharge <= 1e-12:
            take = min(max_c, pv_left)
            charge += take
            pv_left -= take
    else:
        # Diesel required. Band is 0 or [g_min, g_max]. Size g so battery
        # covers the rest; if g_min exceeds remain, do not discharge, and
        # absorb the floor with incidental charge (never start diesel to charge).
        min_g = remain - max_d
        diesel = min(g_max, max(g_min, min_g))
        discharge = min(max_d, max(0.0, remain - diesel))
        served = pv_to_load + discharge + diesel
        if served + 1e-12 < load:
            dump += load - served
        surplus = max(0.0, served - load)
        if discharge <= 1e-12:
            take = min(max_c - charge, pv_left)
            charge += take
            pv_left -= take
            if surplus > 1e-12:
                take = min(max_c - charge, surplus)
                charge += take
                surplus -= take
        dump += surplus

    if charge < 1e-12:
        charge = 0.0
    if discharge < 1e-12:
        discharge = 0.0
    if diesel < 1e-12:
        diesel = 0.0
    if dump < 1e-12:
        dump = 0.0

    return {
        "c_kw": float(charge),
        "d_kw": float(discharge),
        "g_kw": float(diesel),
        "pv_used_kw": float(pv_avail - pv_left),
        "pv_curtailed_kw": float(pv_left),
        "dump_kw": float(dump),
        "bore_kw": float(bore_kw),
    }


def dispatch_greedy(station: dict[str, Any], series: dict[str, Any]) -> dict[str, Any]:
    paddocks = _paddocks(station)
    n = int(series["horizon_hours"])
    dt = float(station["timestep_hours"])
    demand = series["demand_kl_per_h"]
    pv = series["pv_kw"]
    load = series["homestead_kw"]
    timestamps = series["timestamps"]
    no_pump = set(int(h) for h in station["rules"]["no_pump_hours_local"])

    S = float(station["initial"]["soc_kwh"])
    V = float(station["initial"]["dam_kl"])
    W = {p: float(station["initial"]["header_kl"][p]) for p in paddocks}

    out: dict[str, Any] = {
        "policy": "greedy",
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
        need_pump = V < DAM_PUMP_TRIGGER_KL or headers_fail_next_3(V, W, demand, t, station)
        uA, uB = select_bores(
            need_pump=need_pump,
            no_pump_hour=hour_local in no_pump,
            V=V,
            W=W,
            homestead_kw=float(load[t]),
            pv_avail=float(pv[t]),
            S=S,
            station=station,
        )

        power = allocate_power(float(load[t]), float(pv[t]), S, uA, uB, station)

        inflow = _bore_kl_per_h(station, "bore_a") * uA + _bore_kl_per_h(station, "bore_b") * uB
        v_next = step_dam(V, inflow, sum(f[p] for p in paddocks), dt, station)

        w_next = {}
        for p in paddocks:
            w_next[p], extra = step_header(
                W[p], f[p], D[p], unmet[p], dt,
                float(station["water"]["paddocks"][p]["header_kl"]),
            )
            unmet[p] += extra

        s_next = step_battery(S, power["c_kw"], power["d_kw"], station)

        out["uA"].append(int(uA))
        out["uB"].append(int(uB))
        out["c_kw"].append(power["c_kw"])
        out["d_kw"].append(power["d_kw"])
        out["g_kw"].append(power["g_kw"])
        out["pv_used_kw"].append(power["pv_used_kw"])
        out["pv_curtailed_kw"].append(power["pv_curtailed_kw"])
        out["dump_kw"].append(power["dump_kw"])
        out["S_kwh"].append(S)
        out["V_kl"].append(V)
        out["S_kwh_end"].append(s_next)
        out["V_kl_end"].append(v_next)
        for p in paddocks:
            out["f_kl"][p].append(f[p])
            out["W_kl"][p].append(W[p])
            out["W_kl_end"][p].append(w_next[p])
            out["unmet_kl"][p].append(unmet[p])

        S, V, W = s_next, v_next, w_next

    return out


def pd_hour(ts: str) -> int:
    """Local wall-clock hour of an ISO timestamp (offset is kept, not converted)."""
    return int(pd.Timestamp(ts).hour)
