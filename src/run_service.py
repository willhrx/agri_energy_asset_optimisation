"""Service layer shared by the MCP server and the HTTP API.

Single source of truth for: loading stations, resolving scenario overlays,
running policies, comparing baselines, and summarising stations. Both frontends
wrap these functions; neither re-implements engine calls.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.compare import compare_kpis
from src.generate_series import generate_series
from src.kpis import compute_kpis
from src.policies import REGISTRY
from src.scenarios import SUITE, overlay_station
from src.site_schema import validate_station

REPO_ROOT = Path(__file__).resolve().parents[1]

# Compact KPI keys returned over service boundaries (full kpis stay in artefacts).
COMPACT_KEYS = (
    "policy", "diesel_litres", "diesel_aud", "objective_aud", "unmet_kl_total",
    "min_dam_kl", "min_soc_kwh", "pv_kwh", "pv_curtailed_kwh", "pv_utilisation",
    "water_pumped_kl", "dump_kwh_total", "hours_diesel_on", "peak_diesel_kw",
)

POLICY_NAMES = tuple(sorted(REGISTRY))


def compact(kpis: dict[str, Any]) -> dict[str, Any]:
    return {k: kpis[k] for k in COMPACT_KEYS if k in kpis}


def load_station(args: dict[str, Any]) -> dict[str, Any]:
    """Load a station from inline dict or a repo-confined path (default wirra-bore)."""
    raw = args.get("station")
    if isinstance(raw, dict):
        return raw
    raw_path = str(args.get("station_path") or "data/wirra-bore.json")
    path = Path(raw_path)
    if not path.is_absolute():
        path = REPO_ROOT / path
    resolved = path.resolve()
    if not resolved.is_relative_to(REPO_ROOT.resolve()):
        raise ValueError("station_path must stay inside the repository")
    return json.loads(resolved.read_text(encoding="utf-8"))


def prepare_run(args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], str]:
    """Apply scenario/CLI overlays and generate the exogenous series."""
    station = load_station(args)
    scenario = str(args.get("scenario") or station["run"]["name"])
    station = overlay_station(
        station, dam_kl=args.get("dam_kl"), temp_min_c=args.get("temp_min_c"),
        temp_max_c=args.get("temp_max_c"), sky=args.get("sky"), scenario=scenario,
    )
    series = generate_series(
        station, scenario=scenario, sky=args.get("sky"),
        temp_min_c=args.get("temp_min_c"), temp_max_c=args.get("temp_max_c"),
    )
    return station, series, scenario


def check_policies(policies: list[str]) -> None:
    unknown = [p for p in policies if p not in REGISTRY]
    if unknown:
        raise ValueError(f"unknown policy: {', '.join(unknown)}; known: {', '.join(POLICY_NAMES)}")


def run_policies(station: dict[str, Any], series: dict[str, Any],
                 policies: list[str]) -> dict[str, dict[str, Any]]:
    """Dispatch each policy on the prepared series; returns compact KPIs per policy."""
    check_policies(policies)
    return {name: compact(compute_kpis(station, series, REGISTRY[name](station, series)))
            for name in policies}


def run_comparison(station: dict[str, Any], series: dict[str, Any],
                   scenario: str) -> dict[str, Any]:
    """Run dumb + greedy + MILP and return KPIs plus the comparison dict."""
    kpis = {name: compute_kpis(station, series, REGISTRY[name](station, series))
            for name in ("dumb", "greedy", "milp")}
    cmp = compare_kpis(kpis["greedy"], kpis["milp"], dumb=kpis["dumb"])
    return {"scenario": scenario, "kpis": {k: compact(v) for k, v in kpis.items()},
            "comparison": cmp}


def scenario_list() -> list[dict[str, Any]]:
    return [{"name": s["name"], "overrides": {k: v for k, v in s.items() if k != "name"}}
            for s in SUITE]


def station_summary(station: dict[str, Any]) -> dict[str, Any]:
    """Compact station description (also served by the MCP get_station tool)."""
    water = station["water"]
    return {
        "station_id": station["station_id"],
        "timezone": station["timezone"],
        "power": {k: station["power"][k] for k in (
            "pv_kwp", "battery_kwh", "battery_kw", "diesel_kw_min", "diesel_kw_max")},
        "dam_kl": {"usable": water["dam_usable_kl"], "reserve": water["dam_reserve_kl"],
                   "spill": water["dam_spill_kl"],
                   "outlet_kl_per_h": water["dam_outlet_kl_per_h"]},
        "bores": {name: {"kw": b["kw"], "litres_per_s": b["litres_per_s"],
                         "feeds": b.get("feeds")}
                  for name, b in water["bores"].items()},
        "paddocks": list(water["paddocks"].keys()),
        "herd": {name: m["head"] for name, m in station["herd"]["mobs"].items()},
        "initial": station["initial"],
        "schema_errors": validate_station(station),
    }
