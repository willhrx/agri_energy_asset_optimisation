"""Structural validation for a station file. Pure checks, no physics.

`validate_station` returns a list of human-readable errors; an empty list means the
dict has every field the engine reads with sane values. Validation never adds,
removes or renames fields: if a field is not in the JSON, it does not exist.
"""

from __future__ import annotations

from typing import Any

_TOP = ("station_id", "timezone", "timestep_hours", "horizon_hours")
_LOCATION = ("lat", "lon", "altitude_m")
_OBJECTIVE = ("diesel_aud_per_litre", "unmet_water_aud_per_kl")
_POWER = (
    "pv_kwp", "pv_tilt_deg", "pv_azimuth_deg", "inverter_ac_kw", "system_loss_frac",
    "battery_kwh", "battery_kw", "soc_min_frac", "soc_max_frac", "eta_charge",
    "eta_discharge", "diesel_kw_min", "diesel_kw_max", "diesel_litres_per_hour_idle",
    "diesel_litres_per_kwh",
)
_WATER = ("dam_usable_kl", "dam_reserve_kl", "dam_spill_kl", "dam_outlet_kl_per_h")
# Strictly positive power fields. pv_tilt_deg / pv_azimuth_deg may legitimately be 0
# (horizontal array, north-facing) and are range-checked instead.
_POWER_POSITIVE = (
    "pv_kwp", "inverter_ac_kw", "system_loss_frac",
    "battery_kwh", "battery_kw", "soc_min_frac", "soc_max_frac", "eta_charge",
    "eta_discharge", "diesel_kw_min", "diesel_kw_max", "diesel_litres_per_hour_idle",
    "diesel_litres_per_kwh",
)
_BORE = ("kw", "litres_per_s", "feeds")
_MOB = ("class", "head", "liveweight_kg", "litres_per_hd_per_day_base")
_RUN = ("name", "start", "horizon_hours", "sky", "temp_min_c", "temp_max_c")
_RULES = ("no_pump_hours_local", "no_pump_override_if_dam_below_kl")
_SKIES = ("clear", "overcast", "mixed")


def _missing(d: dict[str, Any], keys: tuple[str, ...], where: str) -> list[str]:
    return [f"{where}.{k} missing" for k in keys if k not in d]


def _num(x: Any) -> float | None:
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    return float(x)


def _positive(e: list[str], d: dict[str, Any], keys: tuple[str, ...], where: str) -> None:
    for k in keys:
        v = _num(d.get(k))
        if v is None:
            e.append(f"{where}.{k} must be a number")
        elif v <= 0.0:
            e.append(f"{where}.{k} must be > 0 (got {v})")


def _section(e: list[str], station: dict[str, Any], name: str, keys: tuple[str, ...]) -> dict[str, Any] | None:
    if name not in station or not isinstance(station[name], dict):
        e.append(f"{name} missing or not an object")
        return None
    e.extend(_missing(station[name], keys, name))
    return station[name]


def _validate_power_water(e: list[str], station: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Validate power + water; return (power, bores, paddocks)."""
    pwr = _section(e, station, "power", _POWER)
    if pwr:
        _positive(e, pwr, _POWER_POSITIVE, "power")
        tilt, azimuth = _num(pwr.get("pv_tilt_deg")), _num(pwr.get("pv_azimuth_deg"))
        if tilt is not None and not 0 <= tilt <= 90:
            e.append(f"power.pv_tilt_deg {tilt} outside [0, 90]")
        if azimuth is not None and not 0 <= azimuth < 360:
            e.append(f"power.pv_azimuth_deg {azimuth} outside [0, 360)")
        s_min, s_max = _num(pwr.get("soc_min_frac")), _num(pwr.get("soc_max_frac"))
        g_min, g_max = _num(pwr.get("diesel_kw_min")), _num(pwr.get("diesel_kw_max"))
        if None not in (s_min, s_max) and s_min >= s_max:
            e.append("power.soc_min_frac must be < power.soc_max_frac")
        if None not in (g_min, g_max) and g_min >= g_max:
            e.append("power.diesel_kw_min must be < power.diesel_kw_max")

    water = _section(e, station, "water", _WATER)
    bores: dict[str, Any] = {}
    paddocks: dict[str, Any] = {}
    if water:
        _positive(e, water, _WATER, "water")
        reserve, usable, spill = (
            _num(water.get("dam_reserve_kl")),
            _num(water.get("dam_usable_kl")),
            _num(water.get("dam_spill_kl")),
        )
        if None not in (reserve, usable, spill) and not reserve < usable < spill:
            e.append("water must satisfy reserve < usable < spill")
        raw_bores = water.get("bores")
        if not isinstance(raw_bores, dict) or not raw_bores:
            e.append("water.bores missing or empty")
        else:
            bores = raw_bores
            for name, b in raw_bores.items():
                if not isinstance(b, dict):
                    e.append(f"water.bores.{name} must be an object")
                    continue
                e.extend(_missing(b, _BORE, f"water.bores.{name}"))
                _positive(e, b, ("kw", "litres_per_s"), f"water.bores.{name}")
                if not isinstance(b.get("feeds"), str) or not b.get("feeds"):
                    e.append(f"water.bores.{name}.feeds must be a non-empty string")
        raw_paddocks = water.get("paddocks")
        if not isinstance(raw_paddocks, dict) or not raw_paddocks:
            e.append("water.paddocks missing or empty")
        else:
            paddocks = raw_paddocks
            for name, pd_ in raw_paddocks.items():
                v = _num(pd_.get("header_kl")) if isinstance(pd_, dict) else None
                if v is None or v <= 0:
                    e.append(f"water.paddocks.{name}.header_kl must be a number > 0")
    return pwr or {}, bores, paddocks


def _validate_herd_placement(e: list[str], station: dict[str, Any], paddocks: dict[str, Any]) -> dict[str, Any]:
    """Validate herd + placement; return the mobs dict."""
    herd = station.get("herd")
    mobs = herd.get("mobs") if isinstance(herd, dict) else None
    if not isinstance(mobs, dict) or not mobs:
        e.append("herd.mobs missing or empty")
        mobs = {}
    else:
        for name, m in mobs.items():
            if not isinstance(m, dict):
                e.append(f"herd.mobs.{name} must be an object")
                continue
            e.extend(_missing(m, _MOB, f"herd.mobs.{name}"))
            head = _num(m.get("head"))
            if head is not None and head < 0:
                e.append(f"herd.mobs.{name}.head must be >= 0")

    placement = station.get("placement")
    if not isinstance(placement, list) or not placement:
        e.append("placement missing or empty")
        return mobs
    for i, block in enumerate(placement):
        if not isinstance(block, dict):
            e.append(f"placement[{i}] must be an object")
            continue
        e.extend(_missing(block, ("from_hour", "to_hour", "paddock_mobs"), f"placement[{i}]"))
        pm = block.get("paddock_mobs")
        if isinstance(pm, dict):
            for paddock, mob_ids in pm.items():
                if paddock not in paddocks:
                    e.append(f"placement[{i}].paddock_mobs references unknown paddock {paddock}")
                if not isinstance(mob_ids, list):
                    e.append(f"placement[{i}].paddock_mobs.{paddock} must be a list")
                else:
                    for mid in mob_ids:
                        if mid not in mobs:
                            e.append(f"placement[{i}] references unknown mob {mid}")
    return mobs


def _validate_series_tables(e: list[str], station: dict[str, Any]) -> None:
    phi = station.get("phi_hourly")
    if not isinstance(phi, list) or len(phi) != 24 or any(_num(x) is None for x in phi):
        e.append("phi_hourly must be a list of 24 numbers")
    elif abs(sum(float(x) for x in phi) - 1.0) > 1e-9:
        e.append(f"phi_hourly must sum to 1 (got {sum(float(x) for x in phi):.9f})")

    wk = station.get("homestead_weekday_kw")
    if not isinstance(wk, list) or len(wk) != 24 or any(_num(x) is None or x < 0 for x in wk):
        e.append("homestead_weekday_kw must be a list of 24 non-negative numbers")

    ov = station.get("homestead_weekend_hour_overrides_kw", {})
    if not isinstance(ov, dict):
        e.append("homestead_weekend_hour_overrides_kw must be an object")
    else:
        for k, v in ov.items():
            if not str(k).isdigit() or not 0 <= int(k) <= 23 or _num(v) is None:
                e.append(f"homestead_weekend_hour_overrides_kw.{k} must be hour 0-23 -> number")


def _validate_initial(e: list[str], station: dict[str, Any], pwr: dict[str, Any],
                      water: dict[str, Any], paddocks: dict[str, Any]) -> None:
    initial = station.get("initial")
    if not isinstance(initial, dict):
        e.append("initial missing or not an object")
        return
    e.extend(_missing(initial, ("soc_kwh", "dam_kl", "header_kl"), "initial"))
    battery = _num(pwr.get("battery_kwh")) or 0.0
    s_min = (_num(pwr.get("soc_min_frac")) or 0.0) * battery
    s_max = (_num(pwr.get("soc_max_frac")) or 1.0) * battery
    soc = _num(initial.get("soc_kwh"))
    if soc is not None and not s_min <= soc <= s_max:
        e.append(f"initial.soc_kwh {soc} outside SoC envelope [{s_min}, {s_max}]")
    dam = _num(initial.get("dam_kl"))
    if dam is not None and water:
        reserve, spill = _num(water.get("dam_reserve_kl")), _num(water.get("dam_spill_kl"))
        if None not in (reserve, spill) and not reserve <= dam <= spill:
            e.append(f"initial.dam_kl {dam} outside [{reserve}, {spill}]")
    headers = initial.get("header_kl")
    if not isinstance(headers, dict) or set(headers) != set(paddocks):
        e.append("initial.header_kl must have exactly the paddock keys")
        return
    for name, w in headers.items():
        cap = _num(paddocks.get(name, {}).get("header_kl"))
        v = _num(w)
        if v is None or v < 0 or (cap is not None and v > cap):
            e.append(f"initial.header_kl.{name} must be in [0, header_kl]")


def validate_station(station: dict[str, Any]) -> list[str]:
    e: list[str] = []
    e.extend(_missing(station, _TOP, "station"))
    for k in ("timestep_hours", "horizon_hours"):
        v = _num(station.get(k))
        if v is not None and v <= 0:
            e.append(f"station.{k} must be > 0")

    _section(e, station, "location", _LOCATION)
    obj = _section(e, station, "objective", _OBJECTIVE)
    if obj:
        _positive(e, obj, _OBJECTIVE, "objective")

    pwr, _bores, paddocks = _validate_power_water(e, station)
    water = station.get("water") if isinstance(station.get("water"), dict) else {}
    _validate_herd_placement(e, station, paddocks)
    _validate_series_tables(e, station)

    rules = _section(e, station, "rules", _RULES)
    if rules:
        hours = rules.get("no_pump_hours_local")
        if not isinstance(hours, list) or any(
            not isinstance(h, int) or not 0 <= h <= 23 for h in hours
        ):
            e.append("rules.no_pump_hours_local must be a list of hours 0-23")

    run = _section(e, station, "run", _RUN)
    if run:
        tmin, tmax = _num(run.get("temp_min_c")), _num(run.get("temp_max_c"))
        if None not in (tmin, tmax) and tmin > tmax:
            e.append("run.temp_min_c must be <= run.temp_max_c")
        if run.get("sky") not in _SKIES:
            e.append(f"run.sky must be one of {_SKIES}")

    if pwr and water:
        _validate_initial(e, station, pwr, water, paddocks)
    return e


class StationSchemaError(ValueError):
    """Raised by require_valid_station when a station file fails validation."""


def require_valid_station(station: dict[str, Any]) -> None:
    errors = validate_station(station)
    if errors:
        raise StationSchemaError("station schema errors: " + "; ".join(errors))




