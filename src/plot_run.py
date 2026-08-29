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
    title: str | None = None,
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

    policy = dispatch.get("policy", "run")
    fig.suptitle(
        title or f"{station['station_id']}  {series.get('scenario', '')}  {policy}",
        fontsize=12,
    )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


def plot_compare(
    series: dict[str, Any],
    greedy: dict[str, Any],
    opt: dict[str, Any],
    station: dict[str, Any],
    path: str | Path,
) -> Path:
    n = len(series["timestamps"])
    x = list(range(n))
    tick_idx = list(range(0, n, 6))
    tick_labels = [ts[8:10] + " " + ts[11:16] for ts in (series["timestamps"][i] for i in tick_idx)]

    fig, axes = plt.subplots(4, 1, figsize=(12, 11), sharex=True, constrained_layout=True)

    ax = axes[0]
    ax.plot(x, greedy["g_kw"], label="Greedy diesel", color="tab:red", alpha=0.85)
    ax.plot(x, opt["g_kw"], label="MILP diesel", color="tab:orange", linestyle="--")
    ax.set_ylabel("kW")
    ax.set_title("Diesel")
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(True, alpha=0.3)

    ax = axes[1]
    ax.plot(x, greedy["S_kwh"], label="Greedy SoC", color="tab:green")
    ax.plot(x, opt["S_kwh"], label="MILP SoC", color="tab:olive", linestyle="--")
    ax.set_ylabel("kWh")
    ax.set_title("Battery SoC")
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(True, alpha=0.3)

    ax = axes[2]
    ax.plot(x, greedy["V_kl"], label="Greedy dam", color="tab:cyan")
    ax.plot(x, opt["V_kl"], label="MILP dam", color="tab:blue", linestyle="--")
    ax.axhline(float(station["water"]["dam_reserve_kl"]), color="tab:red", linestyle=":", label="Reserve")
    ax.set_ylabel("kL")
    ax.set_title("Dam")
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(True, alpha=0.3)

    ax = axes[3]
    ax.step(x, greedy["uA"], where="post", label="Greedy A", color="tab:brown", alpha=0.7)
    ax.step(x, greedy["uB"], where="post", label="Greedy B", color="tab:orange", alpha=0.7)
    ax.step(x, [u + 0.05 for u in opt["uA"]], where="post", label="MILP A", color="saddlebrown", linestyle="--")
    ax.step(x, [u + 0.1 for u in opt["uB"]], where="post", label="MILP B", color="darkorange", linestyle="--")
    ax.set_ylim(-0.1, 1.3)
    ax.set_ylabel("on/off")
    ax.set_title("Bores")
    ax.legend(loc="upper right", ncol=2, fontsize=8)
    ax.grid(True, alpha=0.3)
    ax.set_xlabel("Local time (Australia/Sydney), dd HH:MM")
    ax.set_xticks(tick_idx)
    ax.set_xticklabels(tick_labels, rotation=30, ha="right")
    ax.set_xlim(0, n - 1)

    fig.suptitle(f"{station['station_id']}  {series.get('scenario', '')}  greedy vs MILP", fontsize=12)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path
