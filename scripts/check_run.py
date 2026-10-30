"""Golden contract for a full run. Reads output/*.json and exits non-zero on violation.

  python -m src.run --station data/wirra-bore.json --scenario wirra-summer-clear
  python scripts/check_run.py [output_dir]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    out = Path(argv[1]) if len(argv) > 1 else Path("output")
    station = json.loads(Path("data/wirra-bore.json").read_text(encoding="utf-8"))
    reserve = float(station["water"]["dam_reserve_kl"])
    k = {n: json.loads((out / f).read_text(encoding="utf-8")) for n, f in
         (("dumb", "kpis_dumb.json"), ("greedy", "kpis.json"), ("opt", "kpis_opt.json"))}
    errors: list[str] = []
    for name, kp in k.items():
        if kp["unmet_kl_total"] > 1e-6:
            errors.append(f"{name}: unmet {kp['unmet_kl_total']} kL on default scenario")
        if kp["min_dam_kl"] < reserve - 1e-3:
            errors.append(f"{name}: dam {kp['min_dam_kl']} below reserve {reserve}")
    if not k["opt"]["objective_aud"] <= k["greedy"]["objective_aud"] + 1e-2:
        errors.append("MILP objective worse than greedy")
    if not k["greedy"]["objective_aud"] <= k["dumb"]["objective_aud"] + 1e-2:
        errors.append("greedy objective worse than dumb")
    if not 180.0 <= k["greedy"]["pv_kwh"] / 2 <= 320.0:
        errors.append(f"PV per day {k['greedy']['pv_kwh'] / 2:.1f} kWh outside 180-320")
    for e in errors:
        print("FAIL:", e)
    if not errors:
        print("golden run ok:", {n: round(v["objective_aud"], 2) for n, v in k.items()})
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
