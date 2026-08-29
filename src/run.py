"""Entry point: generate series, greedy dispatch, KPIs, figure."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.dispatch_greedy import dispatch_greedy
from src.generate_series import generate_series
from src.kpis import compute_kpis, print_kpis
from src.plot_run import plot_run


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
    parser = argparse.ArgumentParser(description="Wirra-bore sprint 1 greedy run")
    parser.add_argument("--station", default="data/wirra-bore.json")
    parser.add_argument("--scenario", default="wirra-summer-clear")
    parser.add_argument("--output-dir", default="output")
    args = parser.parse_args(argv)

    station = load_station(args.station)
    series = generate_series(station, scenario=args.scenario)
    dispatch = dispatch_greedy(station, series)
    kpis = compute_kpis(station, series, dispatch)

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "series.json", series)
    write_json(out / "dispatch_greedy.json", dispatch)
    write_json(out / "kpis.json", kpis)
    plot_run(series, dispatch, station, out / "run.png")
    print_kpis(kpis)
    print(f"Wrote {out}/series.json, dispatch_greedy.json, kpis.json, run.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
