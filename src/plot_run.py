"""One figure: PV, load, SoC, dam, diesel, bore on/off, paddock demand."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def plot_run(
    series: dict[str, Any],
    dispatch: dict[str, Any],
    station: dict[str, Any],
    path: str | Path,
) -> Path:
    n = len(series["timestamps"])
    x = list(range(n))
    tick_idx = list(range(0, n, 6))
    tick_labels = [ts[8:10] + " " + ts[11:16] for ts in (series["timestamps"][i] for i in tick_idx)]
    paddocks = list(station["water"]["paddocks"].keys())
    reserve = float(station["water"]["dam_reserve_kl"])

    fig, axes = plt.subplots(5, 1, figsize=(12, 14), sharex=True, constrained_layout=True)

    ax = axes[0]
    ax.plot(x, series["pv_kw"], label="PV available", color="gold")
    ax.plot(x, series["homestead_kw"], label="Homestead load", color="tab:blue")
    ax.plot(x, dispatch["g_kw"], label="Diesel", color="tab:red")
    ax.plot(x, dispatch["c_kw"], label="Charge", color="tab:green", linestyle="--")
    ax.plot(x, dispatch["d_kw"], label="Discharge", color="tab:purple", linestyle="--")
    ax.set_ylabel("kW")
    ax.set_title("PV, homestead load, diesel, battery")
    ax.legend(loc="upper right", ncol=3, fontsize=8)
    ax.grid(True, alpha=0.3)

    ax = axes[1]
    ax.plot(x, dispatch["S_kwh"], label="SoC", color="tab:green")
    s_min = float(station["power"]["soc_min_frac"]) * float(station["power"]["battery_kwh"])
    s_max = float(station["power"]["soc_max_frac"]) * float(station["power"]["battery_kwh"])
    ax.axhline(s_min, color="tab:green", linestyle=":", alpha=0.6, label="SoC min/max")
    ax.axhline(s_max, color="tab:green", linestyle=":", alpha=0.6)
    ax.set_ylabel("kWh")
    ax.set_title("Battery SoC")
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(True, alpha=0.3)

    ax = axes[2]
    ax.plot(x, dispatch["V_kl"], label="Dam", color="tab:cyan")
    ax.axhline(reserve, color="tab:red", linestyle="--", label=f"Reserve {reserve:.0f} kL")
    ax.set_ylabel("kL")
    ax.set_title("Dam volume")
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(True, alpha=0.3)

    ax = axes[3]
    ax.step(x, dispatch["uA"], where="post", label="Bore A", color="tab:brown")
    ax.step(x, dispatch["uB"], where="post", label="Bore B", color="tab:orange")
    ax.set_ylabel("on/off")
    ax.set_ylim(-0.1, 1.2)
    ax.set_yticks([0, 1])
    ax.set_title("Bore on/off")
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(True, alpha=0.3)

    ax = axes[4]
    for p in paddocks:
        ax.plot(x, series["demand_kl_per_h"][p], label=p)
    ax.set_ylabel("kL/h")
    ax.set_title("Paddock demand")
    ax.legend(loc="upper right", ncol=4, fontsize=8)
    ax.grid(True, alpha=0.3)
    ax.set_xlabel("Local time (Australia/Sydney), dd HH:MM")
    ax.set_xticks(tick_idx)
    ax.set_xticklabels(tick_labels, rotation=30, ha="right")
    ax.set_xlim(0, n - 1)

    fig.suptitle(
        f"{station['station_id']}  {series.get('scenario', '')}  greedy",
        fontsize=12,
    )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path
