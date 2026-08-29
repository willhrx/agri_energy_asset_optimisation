"""48-hour PuLP/CBC MILP dispatch (sprint 2).

Same output schema as dispatch_greedy. Minimises diesel AUD plus unmet-water
penalty (PROBLEM.md §8). Unlike greedy, charging from diesel is allowed.

Power (each hour t):
    pv_used + d + g = L + c + 11*uA + 15*uB

Diesel g is 0 or [8, 24] via binary ug. No simultaneous charge and discharge.
Battery: S_{t+1} = S_t + 0.95*c*dt - d*dt/0.95, S in [9, 57] kWh, |c|,|d| <= 15 kW.
Dam: V_{t+1} = V_t + 3.6*(4*uA + 6*uB) - sum f, V in [1000, 10000] kL.
Headers: 0 <= W_p <= 20, sum f <= 40, unmet slack s keeps W >= 0.
No-pump hours 11–15 unless V < 1500, linearized with a binary indicator.
"""

from __future__ import annotations

from typing import Any

import pulp

from src.dispatch_greedy import pd_hour


def _paddocks(station: dict[str, Any]) -> list[str]:
    return list(station["water"]["paddocks"].keys())


def _bore_kw(station: dict[str, Any], name: str) -> float:
    return float(station["water"]["bores"][name]["kw"])


def _bore_kl_per_h(station: dict[str, Any], name: str) -> float:
    return float(station["water"]["bores"][name]["litres_per_s"]) * 3.6


def _val(var) -> float:
    v = pulp.value(var)
    if v is None:
        return 0.0
    return float(v)


def _cbc_solver() -> pulp.LpSolver:
    kwargs = dict(msg=False, timeLimit=60, threads=1)
    try:
        return pulp.PULP_CBC_CMD(gapRel=1e-6, **kwargs)
    except TypeError:
        return pulp.PULP_CBC_CMD(fracGap=1e-6, **kwargs)


def dispatch_opt(station: dict[str, Any], series: dict[str, Any]) -> dict[str, Any]:
    paddocks = _paddocks(station)
    n = int(series["horizon_hours"])
    dt = float(station["timestep_hours"])
    demand = series["demand_kl_per_h"]
    pv = [float(x) for x in series["pv_kw"]]
    load = [float(x) for x in series["homestead_kw"]]
    timestamps = list(series["timestamps"])

    pwr = station["power"]
    water = station["water"]
    obj = station["objective"]
    s_min = float(pwr["soc_min_frac"]) * float(pwr["battery_kwh"])
    s_max = float(pwr["soc_max_frac"]) * float(pwr["battery_kwh"])
    batt_kw = float(pwr["battery_kw"])
    eta_c = float(pwr["eta_charge"])
    eta_d = float(pwr["eta_discharge"])
    g_min = float(pwr["diesel_kw_min"])
    g_max = float(pwr["diesel_kw_max"])
    idle_l = float(pwr["diesel_litres_per_hour_idle"])
    slope_l = float(pwr["diesel_litres_per_kwh"])
    aud_per_l = float(obj["diesel_aud_per_litre"])
    unmet_aud = float(obj["unmet_water_aud_per_kl"])
    kw_a = _bore_kw(station, "bore_a")
    kw_b = _bore_kw(station, "bore_b")
    q_a = _bore_kl_per_h(station, "bore_a")
    q_b = _bore_kl_per_h(station, "bore_b")
    reserve = float(water["dam_reserve_kl"])
    spill = float(water["dam_spill_kl"])
    outlet = float(water["dam_outlet_kl_per_h"])
    header_cap = {pk: float(water["paddocks"][pk]["header_kl"]) for pk in paddocks}
    no_pump = set(int(h) for h in station["rules"]["no_pump_hours_local"])
    override_kl = float(station["rules"]["no_pump_override_if_dam_below_kl"])

    T = list(range(n))
    prob = pulp.LpProblem("wirra_bore_dispatch", pulp.LpMinimize)

    uA = pulp.LpVariable.dicts("uA", T, cat="Binary")
    uB = pulp.LpVariable.dicts("uB", T, cat="Binary")
    ug = pulp.LpVariable.dicts("ug", T, cat="Binary")
    uc = pulp.LpVariable.dicts("uc", T, cat="Binary")
    c = pulp.LpVariable.dicts("c", T, lowBound=0, upBound=batt_kw)
    d = pulp.LpVariable.dicts("d", T, lowBound=0, upBound=batt_kw)
    g = pulp.LpVariable.dicts("g", T, lowBound=0, upBound=g_max)
    pv_used = [pulp.LpVariable(f"pv_used_{t}", lowBound=0, upBound=pv[t]) for t in T]
    S = pulp.LpVariable.dicts("S", list(range(n + 1)), lowBound=s_min, upBound=s_max)
    V = pulp.LpVariable.dicts("V", list(range(n + 1)), lowBound=reserve, upBound=spill)
    W = {
        pk: pulp.LpVariable.dicts(f"W_{pk}", list(range(n + 1)), lowBound=0, upBound=header_cap[pk])
        for pk in paddocks
    }
    f = {pk: pulp.LpVariable.dicts(f"f_{pk}", T, lowBound=0) for pk in paddocks}
    s_unmet = {pk: pulp.LpVariable.dicts(f"s_{pk}", T, lowBound=0) for pk in paddocks}

    # Small epsilon so "unless V < 1500" is strict at the 1500 kL boundary.
    v_eps = 1e-3

    for t in T:
        hour = pd_hour(timestamps[t])
        if hour in no_pump:
            z_low = pulp.LpVariable(f"z_low_{t}", cat="Binary")
            # z=1 ⇒ V_t <= 1500 - eps (pumping allowed). z=0 ⇒ no pumping.
            prob += V[t] <= (override_kl - v_eps) * z_low + spill * (1 - z_low)
            prob += uA[t] <= z_low
            prob += uB[t] <= z_low

        # g is 0 or [g_min, g_max]
        prob += g[t] >= g_min * ug[t]
        prob += g[t] <= g_max * ug[t]

        # no simultaneous charge and discharge
        prob += c[t] <= batt_kw * uc[t]
        prob += d[t] <= batt_kw * (1 - uc[t])

        # pv_used + d + g = L + c + 11*uA + 15*uB
        prob += pv_used[t] + d[t] + g[t] == load[t] + c[t] + kw_a * uA[t] + kw_b * uB[t]

        prob += pulp.lpSum(f[pk][t] for pk in paddocks) <= outlet
        for pk in paddocks:
            D = float(demand[pk][t])
            prob += s_unmet[pk][t] <= D
            prob += W[pk][t + 1] == W[pk][t] + f[pk][t] * dt - D * dt + s_unmet[pk][t] * dt

        prob += S[t + 1] == S[t] + eta_c * c[t] * dt - d[t] * dt / eta_d
        inflow = q_a * uA[t] + q_b * uB[t]
        prob += V[t + 1] == V[t] + inflow * dt - pulp.lpSum(f[pk][t] for pk in paddocks) * dt

    prob += S[0] == float(station["initial"]["soc_kwh"])
    prob += V[0] == float(station["initial"]["dam_kl"])
    for pk in paddocks:
        prob += W[pk][0] == float(station["initial"]["header_kl"][pk])

    # 2.00 * (1.2*ug + 0.28*g) + 50000 * unmet kL
    diesel_aud = pulp.lpSum(aud_per_l * (idle_l * ug[t] + slope_l * g[t]) * dt for t in T)
    unmet_cost = pulp.lpSum(unmet_aud * s_unmet[pk][t] * dt for t in T for pk in paddocks)
    prob += diesel_aud + unmet_cost

    status_code = prob.solve(_cbc_solver())
    status = pulp.LpStatus.get(status_code, str(status_code))
    if status_code != pulp.LpStatusOptimal:
        raise RuntimeError(f"MILP did not solve to optimality (status={status})")

    out: dict[str, Any] = {
        "policy": "milp",
        "solver_status": status,
        "timestamps": timestamps,
        "uA": [],
        "uB": [],
        "c_kw": [],
        "d_kw": [],
        "g_kw": [],
        "pv_used_kw": [],
        "pv_curtailed_kw": [],
        "dump_kw": [],
        "f_kl": {pk: [] for pk in paddocks},
        "S_kwh": [],
        "V_kl": [],
        "W_kl": {pk: [] for pk in paddocks},
        "unmet_kl": {pk: [] for pk in paddocks},
        "S_kwh_end": [],
        "V_kl_end": [],
        "W_kl_end": {pk: [] for pk in paddocks},
    }
    for t in T:
        out["uA"].append(int(round(_val(uA[t]))))
        out["uB"].append(int(round(_val(uB[t]))))
        c_t = max(0.0, _val(c[t]))
        d_t = max(0.0, _val(d[t]))
        g_t = max(0.0, _val(g[t]))
        if c_t < 1e-9:
            c_t = 0.0
        if d_t < 1e-9:
            d_t = 0.0
        if g_t < 1e-9:
            g_t = 0.0
        used = min(max(0.0, _val(pv_used[t])), pv[t])
        out["c_kw"].append(c_t)
        out["d_kw"].append(d_t)
        out["g_kw"].append(g_t)
        out["pv_used_kw"].append(used)
        out["pv_curtailed_kw"].append(max(0.0, pv[t] - used))
        out["dump_kw"].append(0.0)
        out["S_kwh"].append(_val(S[t]))
        out["V_kl"].append(_val(V[t]))
        out["S_kwh_end"].append(_val(S[t + 1]))
        out["V_kl_end"].append(_val(V[t + 1]))
        for pk in paddocks:
            out["f_kl"][pk].append(max(0.0, _val(f[pk][t])))
            out["W_kl"][pk].append(_val(W[pk][t]))
            out["W_kl_end"][pk].append(_val(W[pk][t + 1]))
            out["unmet_kl"][pk].append(max(0.0, _val(s_unmet[pk][t])))

    out["objective_aud"] = float(pulp.value(diesel_aud + unmet_cost) or 0.0)
    return out
