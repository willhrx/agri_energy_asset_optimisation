"""Fill the 48-hour exogenous series for a station file.

PV uses pvlib Location + Ineichen clearsky + Perez POA + PVWatts-style DC/AC.
Herd demand uses PROBLEM.md heat factor H(T) and the station phi table as-is.
"""

from __future__ import annotations

import hashlib
from typing import Any

import numpy as np
import pandas as pd
import pvlib
from pvlib.location import Location


def heat_factor(temp_c: np.ndarray | float) -> np.ndarray | float:
    """H(T): 1.0 at T<=25; linear to 1.8 at 38; cap 1.8."""
    scalar = np.ndim(temp_c) == 0
    t = np.atleast_1d(np.asarray(temp_c, dtype=float))
    h = np.ones_like(t, dtype=float)
    ramp = (t > 25.0) & (t < 38.0)
    h[ramp] = 1.0 + 0.8 * (t[ramp] - 25.0) / (38.0 - 25.0)
    h[t >= 38.0] = 1.8
    if scalar:
        return float(h[0])
    return h


def scenario_rng(scenario: str) -> np.random.Generator:
    digest = hashlib.sha256(scenario.encode("utf-8")).digest()
    seed = int.from_bytes(digest[:8], "little") % (2**32)
    return np.random.default_rng(seed)


def _run_cfg(station: dict[str, Any], scenario: str | None) -> dict[str, Any]:
    cfg = dict(station["run"])
    if scenario:
        cfg["name"] = scenario
    return cfg


def _hourly_index(station: dict[str, Any], run: dict[str, Any]) -> pd.DatetimeIndex:
    tz = station["timezone"]
    start = pd.Timestamp(run["start"])
    if start.tzinfo is None:
        start = start.tz_localize(tz)
    else:
        start = start.tz_convert(tz)
    horizon = int(run.get("horizon_hours", station["horizon_hours"]))
    freq = f"{int(station['timestep_hours'])}h"
    return pd.date_range(start=start, periods=horizon, freq=freq, tz=tz)


def air_temperature_c(index: pd.DatetimeIndex, tmin: float, tmax: float) -> np.ndarray:
    """T_t = Tmin + (Tmax-Tmin) * (cos(2π(h-15)/24) + 1) / 2. Peak at 15:00."""
    hour = index.hour.to_numpy(dtype=float)
    return tmin + (tmax - tmin) * (np.cos(2.0 * np.pi * (hour - 15.0) / 24.0) + 1.0) / 2.0


def _apply_sky(
    ghi: pd.Series,
    dni: pd.Series,
    dhi: pd.Series,
    sky: str,
    start: pd.Timestamp,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    sky = (sky or "clear").lower()
    ghi = ghi.astype(float).copy()
    dni = dni.astype(float).copy()
    dhi = dhi.astype(float).copy()
    if sky == "overcast":
        ghi *= 0.35
        dni *= 0.05
        dhi *= 0.70
    elif sky == "mixed":
        hours_from_start = (ghi.index - start) / pd.Timedelta(hours=1)
        day1 = hours_from_start >= 24.0
        local_hour = ghi.index.hour
        mask = day1 & (local_hour >= 12) & (local_hour <= 17)
        ghi.loc[mask] = ghi.loc[mask] * 0.45
    return ghi, dni, dhi


def pv_ac_kw(station: dict[str, Any], index: pd.DatetimeIndex, temp_c: np.ndarray, sky: str) -> np.ndarray:
    """Hourly AC PV (kW) as the mean of 5-minute clearsky/PVWatts samples, labeled at hour start."""
    loc = station["location"]
    power = station["power"]
    tz = station["timezone"]
    start = index[0]
    end = index[-1] + pd.Timedelta(hours=int(station["timestep_hours"]))
    times = pd.date_range(start=start, end=end, freq="5min", tz=tz, inclusive="left")

    site = Location(
        latitude=float(loc["lat"]),
        longitude=float(loc["lon"]),
        tz=tz,
        altitude=float(loc["altitude_m"]),
        name=station.get("station_id", "station"),
    )
    clearsky = site.get_clearsky(times, model="ineichen")
    ghi, dni, dhi = _apply_sky(clearsky["ghi"], clearsky["dni"], clearsky["dhi"], sky, start)

    solpos = site.get_solarposition(times)
    dni_extra = pvlib.irradiance.get_extra_radiation(times)
    airmass = pvlib.atmosphere.get_relative_airmass(solpos["apparent_zenith"])
    poa = pvlib.irradiance.get_total_irradiance(
        surface_tilt=float(power["pv_tilt_deg"]),
        surface_azimuth=float(power["pv_azimuth_deg"]),
        solar_zenith=solpos["apparent_zenith"],
        solar_azimuth=solpos["azimuth"],
        dni=dni,
        ghi=ghi,
        dhi=dhi,
        dni_extra=dni_extra,
        airmass=airmass,
        model="perez",
    )
    poa_global = poa["poa_global"].to_numpy(dtype=float)
    poa_global = np.nan_to_num(poa_global, nan=0.0, posinf=0.0, neginf=0.0)
    poa_global = np.clip(poa_global, 0.0, None)

    # Air temp is hourly; hold each hour's value across the 5-minute samples.
    temp_hourly = pd.Series(temp_c, index=index)
    temp_5min = temp_hourly.reindex(times, method="ffill").to_numpy(dtype=float)
    t_cell = temp_5min + 25.0 * poa_global / 1000.0

    pdc0_w = float(power["pv_kwp"]) * 1000.0
    try:
        pdc = pvlib.pvsystem.pvwatts_dc(
            effective_irradiance=poa_global,
            temp_cell=t_cell,
            pdc0=pdc0_w,
            gamma_pdc=-0.004,
        )
    except TypeError:
        pdc = pvlib.pvsystem.pvwatts_dc(
            g_poa_effective=poa_global,
            temp_cell=t_cell,
            pdc0=pdc0_w,
            gamma_pdc=-0.004,
        )
    pdc = np.nan_to_num(pdc, nan=0.0) * (1.0 - float(power["system_loss_frac"]))

    eta_inv = 0.96
    pac0_w = float(power["inverter_ac_kw"]) * 1000.0
    pdc0_inv = pac0_w / eta_inv
    pvwatts_ac = getattr(pvlib.inverter, "pvwatts", None) or pvlib.inverter.pvwatts_ac
    pac = pvwatts_ac(pdc, pdc0=pdc0_inv, eta_inv_nom=eta_inv)
    pac = np.nan_to_num(pac, nan=0.0, posinf=0.0, neginf=0.0)
    pac_kw = np.clip(pac / 1000.0, 0.0, float(power["inverter_ac_kw"]))

    ac = pd.Series(pac_kw, index=times)
    hourly = ac.resample("1h").mean()
    hourly = hourly.reindex(index).fillna(0.0)
    return np.clip(hourly.to_numpy(dtype=float), 0.0, None)


def homestead_kw(station: dict[str, Any], index: pd.DatetimeIndex, scenario: str) -> np.ndarray:
    weekday = np.asarray(station["homestead_weekday_kw"], dtype=float)
    overrides = {int(k): float(v) for k, v in station.get("homestead_weekend_hour_overrides_kw", {}).items()}
    base = np.empty(len(index), dtype=float)
    for i, ts in enumerate(index):
        hour = int(ts.hour)
        load = weekday[hour]
        if ts.dayofweek >= 5 and hour in overrides:
            load = overrides[hour]
        base[i] = load
    rng = scenario_rng(scenario)
    noisy = base * rng.uniform(0.90, 1.10, size=len(index))
    return np.clip(noisy, 0.0, 20.0)


def _mobs_on_paddock(station: dict[str, Any], paddock: str, hour_index: int) -> list[str]:
    for block in station["placement"]:
        if int(block["from_hour"]) <= hour_index < int(block["to_hour"]):
            return list(block["paddock_mobs"].get(paddock, []))
    return []


def paddock_demand_kl(
    station: dict[str, Any],
    temp_c: np.ndarray,
) -> dict[str, np.ndarray]:
    """D_p,t [kL/h] = sum_{m on p} N_m * ell_m * H(T_t) * φ[h(t)] / 1000."""
    phi = np.asarray(station["phi_hourly"], dtype=float)
    h_t = heat_factor(temp_c)
    paddocks = list(station["water"]["paddocks"].keys())
    n = len(temp_c)
    out = {p: np.zeros(n, dtype=float) for p in paddocks}
    mobs = station["herd"]["mobs"]
    for t in range(n):
        hour_of_day = t % 24
        phi_h = float(phi[hour_of_day])
        ht = float(h_t[t])
        for paddock in paddocks:
            total_l = 0.0
            for mob_id in _mobs_on_paddock(station, paddock, t):
                mob = mobs[mob_id]
                total_l += float(mob["head"]) * float(mob["litres_per_hd_per_day_base"]) * ht * phi_h
            out[paddock][t] = total_l / 1000.0
    return out


def generate_series(
    station: dict[str, Any],
    scenario: str | None = None,
    sky: str | None = None,
    temp_min_c: float | None = None,
    temp_max_c: float | None = None,
) -> dict[str, Any]:
    run = _run_cfg(station, scenario)
    if sky:
        run["sky"] = sky
    if temp_min_c is not None:
        run["temp_min_c"] = temp_min_c
    if temp_max_c is not None:
        run["temp_max_c"] = temp_max_c
    scenario_name = str(run["name"])
    index = _hourly_index(station, run)
    tmin = float(run["temp_min_c"])
    tmax = float(run["temp_max_c"])
    temp = air_temperature_c(index, tmin, tmax)
    h_t = np.asarray(heat_factor(temp), dtype=float)
    pv = pv_ac_kw(station, index, temp, sky=str(run.get("sky", "clear")))
    load = homestead_kw(station, index, scenario_name)
    demand = paddock_demand_kl(station, temp)

    return {
        "station_id": station["station_id"],
        "scenario": scenario_name,
        "timezone": station["timezone"],
        "horizon_hours": int(len(index)),
        "timestep_hours": float(station["timestep_hours"]),
        "sky": str(run.get("sky", "clear")),
        "timestamps": [ts.isoformat() for ts in index],
        "pv_kw": pv.tolist(),
        "homestead_kw": load.tolist(),
        "temp_c": temp.tolist(),
        "heat_factor": h_t.tolist(),
        "demand_kl_per_h": {p: v.tolist() for p, v in demand.items()},
    }
