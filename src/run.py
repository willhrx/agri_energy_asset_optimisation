"""Entry point: series, greedy, MILP, KPIs, figures."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.compare import compare_kpis, print_compare
from src.dispatch_greedy import dispatch_greedy
from src.dispatch_opt import dispatch_opt
from src.generate_series import generate_series
from src.kpis import compute_kpis, print_kpis
from src.plot_run import plot_compare, plot_run


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Wirra-bore greedy + MILP run")
    parser.add_argument("--station", default="data/wirra-bore.json")
    parser.add_argument("--scenario", default="wirra-summer-clear")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--greedy-only", action="store_true")
    args = parser.parse_args(argv)

    station = load_station(args.station)
    series = generate_series(station, scenario=args.scenario)
    greedy = dispatch_greedy(station, series)
    kpis_g = compute_kpis(station, series, greedy)

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "series.json", series)
    write_json(out / "dispatch_greedy.json", greedy)
    write_json(out / "kpis.json", kpis_g)
    plot_run(series, greedy, station, out / "run.png")
    print("=== greedy ===")
    print_kpis(kpis_g)

    wrote = ["series.json", "dispatch_greedy.json", "kpis.json", "run.png"]
    if not args.greedy_only:
        opt = dispatch_opt(station, series)
        kpis_o = compute_kpis(station, series, opt)
        cmp = compare_kpis(kpis_g, kpis_o)
        write_json(out / "dispatch_opt.json", opt)
        write_json(out / "kpis_opt.json", kpis_o)
        write_json(out / "compare.json", cmp)
        plot_run(series, opt, station, out / "run_opt.png")
        plot_compare(series, greedy, opt, station, out / "compare.png")
        print("=== MILP ===")
        print_kpis(kpis_o)
        print_compare(cmp)
        wrote += ["dispatch_opt.json", "kpis_opt.json", "compare.json", "run_opt.png", "compare.png"]

    print(f"Wrote {out}/" + ", ".join(wrote))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
