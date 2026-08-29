"""Greedy vs MILP KPI comparison (sprint 2)."""

from __future__ import annotations

from typing import Any


def compare_kpis(greedy: dict[str, Any], opt: dict[str, Any]) -> dict[str, Any]:
    g_obj = float(greedy.get("objective_aud", greedy.get("diesel_aud", 0.0)))
    o_obj = float(opt.get("objective_aud", opt.get("diesel_aud", 0.0)))
    g_d = float(greedy["diesel_aud"])
    o_d = float(opt["diesel_aud"])
    return {
        "greedy_diesel_litres": float(greedy["diesel_litres"]),
        "opt_diesel_litres": float(opt["diesel_litres"]),
        "greedy_diesel_aud": g_d,
        "opt_diesel_aud": o_d,
        "delta_diesel_aud": g_d - o_d,
        "greedy_unmet_kl_total": float(greedy["unmet_kl_total"]),
        "opt_unmet_kl_total": float(opt["unmet_kl_total"]),
        "greedy_objective_aud": g_obj,
        "opt_objective_aud": o_obj,
        "delta_objective_aud": g_obj - o_obj,
        "greedy_hours_diesel_on": int(greedy["hours_diesel_on"]),
        "opt_hours_diesel_on": int(opt["hours_diesel_on"]),
        "greedy_pv_curtailed_kwh": float(greedy["pv_curtailed_kwh"]),
        "opt_pv_curtailed_kwh": float(opt["pv_curtailed_kwh"]),
        "opt_beats_or_ties_greedy": o_obj <= g_obj + 1e-2,
    }


def print_compare(cmp: dict[str, Any]) -> None:
    print("Compare greedy vs MILP")
    print(f"  diesel AUD     greedy {cmp['greedy_diesel_aud']:.2f}  opt {cmp['opt_diesel_aud']:.2f}  Δ {cmp['delta_diesel_aud']:.2f}")
    print(f"  diesel L       greedy {cmp['greedy_diesel_litres']:.3f}  opt {cmp['opt_diesel_litres']:.3f}")
    print(f"  unmet kL       greedy {cmp['greedy_unmet_kl_total']:.4f}  opt {cmp['opt_unmet_kl_total']:.4f}")
    print(f"  objective AUD  greedy {cmp['greedy_objective_aud']:.2f}  opt {cmp['opt_objective_aud']:.2f}  Δ {cmp['delta_objective_aud']:.2f}")
    print(f"  diesel hours   greedy {cmp['greedy_hours_diesel_on']}  opt {cmp['opt_hours_diesel_on']}")
