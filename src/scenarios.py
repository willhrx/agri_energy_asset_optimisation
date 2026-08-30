"""Named stress cases. Canonical JSON fields are not extended; we only override run/initial."""

from __future__ import annotations

import copy
from typing import Any

SUITE: list[dict[str, Any]] = [
    {"name": "wirra-summer-clear", "sky": "clear"},
    {"name": "wirra-summer-mixed", "sky": "mixed"},
    {"name": "wirra-summer-overcast", "sky": "overcast"},
    {"name": "wirra-dry", "sky": "clear", "dam_kl": 1800.0},
    {"name": "wirra-heat", "sky": "clear", "temp_max_c": 42.0},
]


def overlay_station(
    station: dict[str, Any],
    *,
    dam_kl: float | None = None,
    temp_min_c: float | None = None,
    temp_max_c: float | None = None,
    sky: str | None = None,
    scenario: str | None = None,
) -> dict[str, Any]:
    """Copy the station dict and overlay CLI/suite knobs. Does not invent JSON keys."""
    out = copy.deepcopy(station)
    if scenario:
        out.setdefault("run", {})["name"] = scenario
    if sky:
        out.setdefault("run", {})["sky"] = sky
    if temp_min_c is not None:
        out.setdefault("run", {})["temp_min_c"] = float(temp_min_c)
    if temp_max_c is not None:
        out.setdefault("run", {})["temp_max_c"] = float(temp_max_c)
    if dam_kl is not None:
        out.setdefault("initial", {})["dam_kl"] = float(dam_kl)
    return out
