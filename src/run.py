"""Entry point: series, dumb / greedy / MILP, KPIs, figures, optional suite."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.compare import compare_kpis, print_compare
from src.generate_series import generate_series
from src.kpis import compute_kpis, print_kpis
from src.policies import get_policy
from src.plot_run import plot_compare, plot_run, plot_suite
from src.scenarios import SUITE, overlay_station


def load_station(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def json_ready(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): json_ready(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_ready(v) for v in obj]
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, int):
        return int(obj)
    if isinstance(obj, float):
        return float(obj)
    return obj


def write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(json_ready(obj), indent=2) + "\n", encoding="utf-8")


def run_one(
    station: dict[str, Any],
    scenario: str,
    out: Path,
    *,
    greedy_only: bool = False,
    sky: str | None = None,
    dam_kl: float | None = None,
    temp_max_c: float | None = None,
    temp_min_c: float | None = None,
) -> dict[str, Any]:
    station = overlay_station(
        station,
        dam_kl=dam_kl,
        temp_min_c=temp_min_c,
        temp_max_c=temp_max_c,
        sky=sky,
        scenario=scenario,
    )
    series = generate_series(
        station,
        scenario=scenario,
        sky=sky,
        temp_min_c=temp_min_c,
        temp_max_c=temp_max_c,
    )
    dumb = get_policy("dumb")(station, series)
    greedy = get_policy("greedy")(station, series)
    kpis_d = compute_kpis(station, series, dumb)
    kpis_g = compute_kpis(station, series, greedy)

    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "series.json", series)
    write_json(out / "dispatch_dumb.json", dumb)
    write_json(out / "dispatch_greedy.json", greedy)
    write_json(out / "kpis_dumb.json", kpis_d)
    write_json(out / "kpis.json", kpis_g)
    plot_run(series, greedy, station, out / "run.png")
    plot_run(series, dumb, station, out / "run_dumb.png")
    print(f"=== {series.get('sky', sky)}  {scenario}  dumb ===")
    print_kpis(kpis_d)
    print("=== greedy ===")
    print_kpis(kpis_g)

    result: dict[str, Any] = {
        "name": scenario,
        "sky": series.get("sky"),
        "kpis": {"dumb": kpis_d, "greedy": kpis_g},
    }
    wrote = ["series.json", "dispatch_dumb.json", "dispatch_greedy.json", "kpis_dumb.json", "kpis.json", "run.png", "run_dumb.png"]
    if not greedy_only:
        opt = get_policy("milp")(station, series)
        kpis_o = compute_kpis(station, series, opt)
        cmp = compare_kpis(kpis_g, kpis_o, dumb=kpis_d)
        write_json(out / "dispatch_opt.json", opt)
        write_json(out / "kpis_opt.json", kpis_o)
        write_json(out / "compare.json", cmp)
        plot_run(series, opt, station, out / "run_opt.png")
        plot_compare(series, greedy, opt, station, out / "compare.png", dumb=dumb)
        print("=== MILP ===")
        print_kpis(kpis_o)
        print_compare(cmp)
        result["kpis"]["opt"] = kpis_o
        result["compare"] = cmp
        wrote += ["dispatch_opt.json", "kpis_opt.json", "compare.json", "run_opt.png", "compare.png"]
    print(f"Wrote {out}/" + ", ".join(wrote))
    print("Schematic: python -m src.gui")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Wirra-bore dumb + greedy + MILP")
    parser.add_argument("--station", default="data/wirra-bore.json")
    parser.add_argument("--scenario", default="wirra-summer-clear")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--greedy-only", action="store_true")
    parser.add_argument("--sky", choices=["clear", "mixed", "overcast"])
    parser.add_argument("--dam-kl", type=float, default=None, help="override initial dam kL")
    parser.add_argument("--temp-max", type=float, default=None, dest="temp_max_c")
    parser.add_argument("--temp-min", type=float, default=None, dest="temp_min_c")
    parser.add_argument("--suite", action="store_true", help="run clear/mixed/overcast/dry/heat")
    args = parser.parse_args(argv)

    station = load_station(args.station)
    if args.suite:
        root = Path(args.output_dir)
        rows = []
        for spec in SUITE:
            sub = root / "suite" / spec["name"]
            print(f"\n######## {spec['name']} ########")
            row = run_one(
                station,
                spec["name"],
                sub,
                greedy_only=args.greedy_only,
                sky=spec.get("sky"),
                dam_kl=spec.get("dam_kl"),
                temp_max_c=spec.get("temp_max_c"),
            )
            rows.append(row)
        summary = {
            "suite": [
                {
                    "name": r["name"],
                    "sky": r.get("sky"),
                    "dumb_objective_aud": r["kpis"]["dumb"]["objective_aud"],
                    "greedy_objective_aud": r["kpis"]["greedy"]["objective_aud"],
                    "opt_objective_aud": r["kpis"].get("opt", {}).get("objective_aud"),
                    "opt_water_pumped_kl": r["kpis"].get("opt", {}).get("water_pumped_kl"),
                    "greedy_water_pumped_kl": r["kpis"]["greedy"]["water_pumped_kl"],
                    "unmet_opt": r["kpis"].get("opt", {}).get("unmet_kl_total"),
                }
                for r in rows
            ]
        }
        write_json(root / "suite.json", summary)
        if not args.greedy_only:
            plot_suite(rows, root / "suite.png")
        print(f"\nSuite summary {root}/suite.json")
        return 0

    run_one(
        station,
        args.scenario,
        Path(args.output_dir),
        greedy_only=args.greedy_only,
        sky=args.sky,
        dam_kl=args.dam_kl,
        temp_max_c=args.temp_max_c,
        temp_min_c=args.temp_min_c,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
