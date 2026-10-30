"""Shared state-transition helpers (PROBLEM.md §6). Pure functions, no hidden globals.

Do not change a formula here without editing PROBLEM.md first — the balances in
tests/test_balances.py and tests/test_dynamics.py are the contract.
"""

from __future__ import annotations

from typing import Any


def step_battery(S: float, c_kw: float, d_kw: float, station: dict[str, Any]) -> float:
    """S' = S + eta_c*c*dt - d*dt/eta_d, clipped to the SoC envelope."""
    p = station["power"]
    dt = float(station["timestep_hours"])
    s_min = float(p["soc_min_frac"]) * float(p["battery_kwh"])
    s_max = float(p["soc_max_frac"]) * float(p["battery_kwh"])
    s_next = S + float(p["eta_charge"]) * c_kw * dt - d_kw * dt / float(p["eta_discharge"])
    return float(min(s_max, max(s_min, s_next)))


def step_dam(
    V: float,
    inflow_kl_per_h: float,
    outflow_kl_per_h: float,
    dt: float,
    station: dict[str, Any],
) -> float:
    """V' = V + inflow*dt - outflow*dt, held within [reserve, spill]."""
    reserve = float(station["water"]["dam_reserve_kl"])
    spill = float(station["water"]["dam_spill_kl"])
    v_next = V + (float(inflow_kl_per_h) - float(outflow_kl_per_h)) * float(dt)
    return float(min(spill, max(reserve, v_next)))


def step_header(
    W: float,
    f_kl_per_h: float,
    demand_kl_per_h: float,
    unmet_kl_per_h: float,
    dt: float,
    cap_kl: float,
) -> tuple[float, float]:
    """W' = W + f*dt - D*dt + unmet*dt, floored at 0 and capped.

    Returns (w_next, extra_unmet_kl_per_h). If the update would go negative the
    shortfall is converted to unmet slack so W never goes below 0.
    """
    w = float(W) + float(f_kl_per_h) * float(dt) - float(demand_kl_per_h) * float(dt) \
        + float(unmet_kl_per_h) * float(dt)
    extra = 0.0
    if w < 0.0:
        extra = -w / float(dt)
        w = 0.0
    return float(min(float(cap_kl), w)), extra
