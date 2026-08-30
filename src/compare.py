"""Baseline KPI comparison: dumb diesel, greedy, MILP."""

from __future__ import annotations

from typing import Any


def _row(kpis: dict[str, Any]) -> dict[str, float]:
    return {
        "diesel_litres": float(kpis["diesel_litres"]),
        "diesel_aud": float(kpis["diesel_aud"]),
        "objective_aud": float(kpis.get("objective_aud", kpis["diesel_aud"])),
        "unmet_kl_total": float(kpis["unmet_kl_total"]),
        "hours_diesel_on": int(kpis["hours_diesel_on"]),
        "pv_curtailed_kwh": float(kpis["pv_curtailed_kwh"]),
        "pv_used_kwh": float(kpis.get("pv_used_kwh", 0.0)),
        "pv_utilisation": float(kpis.get("pv_utilisation", 0.0)),
        "water_pumped_kl": float(kpis.get("water_pumped_kl", 0.0)),
        "bore_hours_a": int(kpis.get("bore_hours_a", 0)),
        "bore_hours_b": int(kpis.get("bore_hours_b", 0)),
        "peak_diesel_kw": float(kpis.get("peak_diesel_kw", 0.0)),
        "min_dam_kl": float(kpis["min_dam_kl"]),
        "min_soc_kwh": float(kpis["min_soc_kwh"]),
    }


def compare_kpis(greedy: dict[str, Any], opt: dict[str, Any], dumb: dict[str, Any] | None = None) -> dict[str, Any]:
    g = _row(greedy)
    o = _row(opt)
    out: dict[str, Any] = {
        "greedy": g,
        "opt": o,
        "greedy_diesel_litres": g["diesel_litres"],
        "opt_diesel_litres": o["diesel_litres"],
        "greedy_diesel_aud": g["diesel_aud"],
        "opt_diesel_aud": o["diesel_aud"],
        "delta_diesel_aud": g["diesel_aud"] - o["diesel_aud"],
        "greedy_unmet_kl_total": g["unmet_kl_total"],
        "opt_unmet_kl_total": o["unmet_kl_total"],
        "greedy_objective_aud": g["objective_aud"],
        "opt_objective_aud": o["objective_aud"],
        "delta_objective_aud": g["objective_aud"] - o["objective_aud"],
        "greedy_hours_diesel_on": g["hours_diesel_on"],
        "opt_hours_diesel_on": o["hours_diesel_on"],
        "greedy_pv_curtailed_kwh": g["pv_curtailed_kwh"],
        "opt_pv_curtailed_kwh": o["pv_curtailed_kwh"],
        "opt_beats_or_ties_greedy": o["objective_aud"] <= g["objective_aud"] + 1e-2,
    }
    if dumb is not None:
        d = _row(dumb)
        out["dumb"] = d
        out["dumb_diesel_aud"] = d["diesel_aud"]
        out["dumb_objective_aud"] = d["objective_aud"]
        out["greedy_beats_or_ties_dumb"] = g["objective_aud"] <= d["objective_aud"] + 1e-2
        out["opt_beats_or_ties_dumb"] = o["objective_aud"] <= d["objective_aud"] + 1e-2
    return out


def print_compare(cmp: dict[str, Any]) -> None:
    print("Compare baselines")
    rows = []
    if "dumb" in cmp:
        rows.append(("dumb  ", cmp["dumb"]))
    rows.append(("greedy", cmp["greedy"] if "greedy" in cmp else {
        "diesel_aud": cmp["greedy_diesel_aud"],
        "diesel_litres": cmp["greedy_diesel_litres"],
        "objective_aud": cmp["greedy_objective_aud"],
        "unmet_kl_total": cmp["greedy_unmet_kl_total"],
        "hours_diesel_on": cmp["greedy_hours_diesel_on"],
    }))
    rows.append(("MILP  ", cmp["opt"] if "opt" in cmp else {
        "diesel_aud": cmp["opt_diesel_aud"],
        "diesel_litres": cmp["opt_diesel_litres"],
        "objective_aud": cmp["opt_objective_aud"],
        "unmet_kl_total": cmp["opt_unmet_kl_total"],
        "hours_diesel_on": cmp["opt_hours_diesel_on"],
    }))
    print(f"  {'policy':<8} {'AUD':>8} {'L':>8} {'unmet kL':>10} {'hrs':>5} {'PV use':>7} {'pump kL':>8}")
    for name, r in rows:
        print(
            f"  {name:<8} {r['objective_aud']:8.2f} {r['diesel_litres']:8.3f} "
            f"{r['unmet_kl_total']:10.4f} {r['hours_diesel_on']:5d} "
            f"{r.get('pv_utilisation', 0):7.3f} {r.get('water_pumped_kl', 0):8.1f}"
        )
    print(f"  Δ greedy−MILP diesel AUD {cmp['delta_diesel_aud']:.2f}")
