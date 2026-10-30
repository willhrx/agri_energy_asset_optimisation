"""TEMPORARY CI diagnostic: dump greedy water arrays to locate the dynamics bug.

Remove this file after root-causing the test_balances failures.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.dispatch_greedy import dispatch_greedy
from src.generate_series import generate_series

ROOT = Path(__file__).resolve().parents[1]


def test_debug_dump() -> None:
    station = json.loads((ROOT / "data" / "wirra-bore.json").read_text(encoding="utf-8"))
    series = generate_series(station, scenario="wirra-summer-clear")
    d = dispatch_greedy(station, series)
    paddocks = list(station["water"]["paddocks"])
    dt = float(station["timestep_hours"])

    rows = []
    for t in range(12):
        row: dict = {
            "t": t,
            "V": round(float(d["V_kl"][t]), 4),
            "Vend": round(float(d["V_kl_end"][t]), 4),
            "uA": d["uA"][t],
            "uB": d["uB"][t],
        }
        for p in paddocks:
            row[p] = [
                round(float(d["W_kl"][p][t]), 4),
                round(float(d["f_kl"][p][t]), 4),
                round(float(series["demand_kl_per_h"][p][t]), 4),
                round(float(d["unmet_kl"][p][t]), 4),
                round(float(d["W_kl_end"][p][t]), 4),
            ]
        rows.append(row)

    first_bad = None
    for t in range(len(d["uA"])):
        for p in paddocks:
            predicted = (
                d["W_kl"][p][t] + d["f_kl"][p][t] * dt
                - series["demand_kl_per_h"][p][t] * dt
                + d["unmet_kl"][p][t] * dt
            )
            predicted = min(float(station["water"]["paddocks"][p]["header_kl"]), max(0.0, predicted))
            if abs(predicted - d["W_kl_end"][p][t]) > 1e-6:
                first_bad = {
                    "t": t,
                    "p": p,
                    "W": d["W_kl"][p][t],
                    "f": d["f_kl"][p][t],
                    "D": series["demand_kl_per_h"][p][t],
                    "unmet": d["unmet_kl"][p][t],
                    "predicted": predicted,
                    "W_end": d["W_kl_end"][p][t],
                }
                break
        if first_bad is not None:
            break

    lengths = {k: len(v) for k, v in d.items() if isinstance(v, list)}
    lengths["demand_north"] = len(series["demand_kl_per_h"]["north"])
    pytest.fail("DEBUG DUMP:\n" + json.dumps({"rows": rows, "first_bad": first_bad, "lens": lengths}))
