"""Cost and objective adapters. Only the off-grid diesel market exists today.

A market pack supplies: fuel cost as a function of output, and objective weights.
Everything reads existing JSON fields; nothing is invented.
"""

from __future__ import annotations

from typing import Any


def diesel_litres_per_hour(g_kw: float, station: dict[str, Any]) -> float:
    """Fuel L/h = 0 if the genset is off, else idle + slope * output (PROBLEM.md §7)."""
    if g_kw <= 1e-12:
        return 0.0
    p = station["power"]
    return float(p["diesel_litres_per_hour_idle"]) + float(p["diesel_litres_per_kwh"]) * float(g_kw)


def objective_weights(station: dict[str, Any]) -> dict[str, float]:
    """Objective coefficients from the station's own `objective` block."""
    o = station["objective"]
    return {
        "diesel_aud_per_litre": float(o["diesel_aud_per_litre"]),
        "unmet_water_aud_per_kl": float(o["unmet_water_aud_per_kl"]),
    }
