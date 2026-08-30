"""KPIs for a greedy (or later optimiser) run."""

from __future__ import annotations

from typing import Any


def diesel_litres_for_g(g_kw: float, station: dict[str, Any]) -> float:
    if g_kw <= 1e-12:
        return 0.0
    p = station["power"]
    return float(p["diesel_litres_per_hour_idle"]) + float(p["diesel_litres_per_kwh"]) * float(g_kw)


def compute_kpis(station: dict[str, Any], series: dict[str, Any], dispatch: dict[str, Any]) -> dict[str, Any]:
    dt = float(station["timestep_hours"])
    paddocks = list(station["water"]["paddocks"].keys())

    diesel_litres = 0.0
    hours_diesel_on = 0
    diesel_hours: list[int] = []
    for t, g in enumerate(dispatch["g_kw"]):
        litres = diesel_litres_for_g(g, station) * dt
        diesel_litres += litres
        if g > 1e-9:
            hours_diesel_on += 1
            diesel_hours.append(t)

    diesel_aud = diesel_litres * float(station["objective"]["diesel_aud_per_litre"])
    pv_kwh = float(sum(series["pv_kw"])) * dt
    pv_used_kwh = float(sum(dispatch["pv_used_kw"])) * dt
    pv_curtailed_kwh = float(sum(dispatch["pv_curtailed_kw"])) * dt
    q_a = float(station["water"]["bores"]["bore_a"]["litres_per_s"]) * 3.6
    q_b = float(station["water"]["bores"]["bore_b"]["litres_per_s"]) * 3.6
    water_pumped_kl = 0.0
    bore_hours_a = 0
    bore_hours_b = 0
    for t, ua in enumerate(dispatch["uA"]):
        ub = dispatch["uB"][t]
        water_pumped_kl += (q_a * ua + q_b * ub) * dt
        bore_hours_a += int(ua)
        bore_hours_b += int(ub)
    peak_diesel_kw = float(max(dispatch["g_kw"]) if dispatch["g_kw"] else 0.0)

    dam_trace = list(dispatch["V_kl"]) + [dispatch["V_kl_end"][-1]]
    soc_trace = list(dispatch["S_kwh"]) + [dispatch["S_kwh_end"][-1]]
    min_dam_kl = float(min(dam_trace))
    min_soc_kwh = float(min(soc_trace))

    unmet_by_hour = []
    unmet_total = 0.0
    for t in range(len(dispatch["timestamps"])):
        hour_unmet = sum(float(dispatch["unmet_kl"][p][t]) for p in paddocks)
        unmet_total += hour_unmet * dt
        if hour_unmet > 1e-9:
            unmet_by_hour.append(
                {
                    "hour": t,
                    "timestamp": dispatch["timestamps"][t],
                    "unmet_kl": hour_unmet,
                    "paddocks": {p: float(dispatch["unmet_kl"][p][t]) for p in paddocks if dispatch["unmet_kl"][p][t] > 1e-9},
                }
            )

    penalty = float(station["objective"]["unmet_water_aud_per_kl"])
    kpis: dict[str, Any] = {
        "policy": dispatch.get("policy", "unknown"),
        "diesel_litres": diesel_litres,
        "diesel_aud": diesel_aud,
        "pv_kwh": pv_kwh,
        "pv_used_kwh": pv_used_kwh,
        "pv_curtailed_kwh": pv_curtailed_kwh,
        "pv_utilisation": (pv_used_kwh / pv_kwh) if pv_kwh > 1e-9 else 0.0,
        "min_dam_kl": min_dam_kl,
        "min_soc_kwh": min_soc_kwh,
        "unmet_kl_total": unmet_total,
        "hours_diesel_on": hours_diesel_on,
        "peak_diesel_kw": peak_diesel_kw,
        "water_pumped_kl": water_pumped_kl,
        "bore_hours_a": bore_hours_a,
        "bore_hours_b": bore_hours_b,
        "objective_aud": diesel_aud + penalty * unmet_total,
    }
    if unmet_total > 1e-9:
        kpis["unmet_hours"] = unmet_by_hour
        kpis["unmet_note"] = (
            "Unmet water slack s_p,t (kL/h) when a header would otherwise go negative. "
            f"Total {unmet_total:.4f} kL across {len(unmet_by_hour)} hour(s). "
            "Dam reserve (1000 kL) is not drawn; outlet is capped at 40 kL/h."
        )
    else:
        kpis["unmet_note"] = "Unmet water is 0 kL on this run."
    return kpis


def print_kpis(kpis: dict[str, Any]) -> None:
    print("KPIs")
    print(f"  diesel_litres     {kpis['diesel_litres']:.3f} L")
    print(f"  diesel_aud        {kpis['diesel_aud']:.2f} AUD")
    if "objective_aud" in kpis:
        print(f"  objective_aud     {kpis['objective_aud']:.2f} AUD")
    print(f"  pv_kwh            {kpis['pv_kwh']:.2f} kWh")
    print(f"  pv_used_kwh       {kpis.get('pv_used_kwh', 0.0):.2f} kWh")
    print(f"  pv_curtailed_kwh  {kpis['pv_curtailed_kwh']:.2f} kWh")
    print(f"  pv_utilisation    {kpis.get('pv_utilisation', 0.0):.3f}")
    print(f"  water_pumped_kl   {kpis.get('water_pumped_kl', 0.0):.2f} kL")
    print(f"  bore_hours        A {kpis.get('bore_hours_a', 0)}  B {kpis.get('bore_hours_b', 0)}")
    print(f"  peak_diesel_kw    {kpis.get('peak_diesel_kw', 0.0):.2f}")
    print(f"  min_dam_kl        {kpis['min_dam_kl']:.2f} kL")
    print(f"  min_soc_kwh       {kpis['min_soc_kwh']:.2f} kWh")
    print(f"  unmet_kl_total    {kpis['unmet_kl_total']:.4f} kL")
    print(f"  hours_diesel_on   {kpis['hours_diesel_on']}")
    if kpis.get("unmet_note"):
        print(f"  note              {kpis['unmet_note']}")
    for row in kpis.get("unmet_hours") or []:
        print(f"    hour {row['hour']} {row['timestamp']} unmet={row['unmet_kl']:.4f} kL {row['paddocks']}")
