"""Minimal MCP (Model Context Protocol) stdio server for the wirra-bore engine.

Exposes the dispatch engine as agent-callable tools over newline-delimited
JSON-RPC 2.0 on stdin/stdout (see docs/adr/0002-mcp-stdio.md for why this is
hand-rolled rather than using the official SDK).

Run:  python -m src.mcp_server   (cwd = repo root)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

from src.compare import compare_kpis
from src.generate_series import generate_series
from src.kpis import compute_kpis
from src.policies import get_policy
from src.scenarios import SUITE, overlay_station
from src.site_schema import validate_station

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "wirra-bore-engine", "version": "0.1.0"}
REPO_ROOT = Path(__file__).resolve().parents[1]

# Compact KPI keys returned by run/compare tools (full kpis stay in artefacts).
_COMPACT = (
    "policy", "diesel_litres", "diesel_aud", "objective_aud", "unmet_kl_total",
    "min_dam_kl", "min_soc_kwh", "pv_kwh", "pv_curtailed_kwh", "pv_utilisation",
    "water_pumped_kl", "dump_kwh_total", "hours_diesel_on", "peak_diesel_kw",
)


def _compact(kpis: dict[str, Any]) -> dict[str, Any]:
    return {k: kpis[k] for k in _COMPACT if k in kpis}


def _load_station(args: dict[str, Any]) -> dict[str, Any]:
    raw = args.get("station")
    if isinstance(raw, dict):
        return raw
    path = Path(args.get("station_path") or "data/wirra-bore.json")
    if not path.is_absolute():
        path = REPO_ROOT / path
    return json.loads(path.read_text(encoding="utf-8"))


def tool_list_scenarios(args: dict[str, Any]) -> dict[str, Any]:
    return {"scenarios": [
        {"name": s["name"], "overrides": {k: v for k, v in s.items() if k != "name"}}
        for s in SUITE
    ]}


def tool_get_station(args: dict[str, Any]) -> dict[str, Any]:
    st = _load_station(args)
    water = st["water"]
    return {
        "station_id": st["station_id"],
        "timezone": st["timezone"],
        "power": {k: st["power"][k] for k in (
            "pv_kwp", "battery_kwh", "battery_kw", "diesel_kw_min", "diesel_kw_max")},
        "dam_kl": {"usable": water["dam_usable_kl"], "reserve": water["dam_reserve_kl"],
                   "spill": water["dam_spill_kl"],
                   "outlet_kl_per_h": water["dam_outlet_kl_per_h"]},
        "bores": {name: {"kw": b["kw"], "litres_per_s": b["litres_per_s"],
                         "feeds": b.get("feeds")}
                  for name, b in water["bores"].items()},
        "paddocks": list(water["paddocks"].keys()),
        "herd": {name: m["head"] for name, m in st["herd"]["mobs"].items()},
        "initial": st["initial"],
        "schema_errors": validate_station(st),
    }


def tool_validate_station(args: dict[str, Any]) -> dict[str, Any]:
    st = _load_station(args)
    errors = validate_station(st)
    return {"ok": not errors, "errors": errors, "station_id": st.get("station_id")}


def _resolve_station_and_series(args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], str]:
    station = _load_station(args)
    scenario = str(args.get("scenario") or station["run"]["name"])
    station = overlay_station(
        station, dam_kl=args.get("dam_kl"), temp_min_c=args.get("temp_min_c"),
        temp_max_c=args.get("temp_max_c"), sky=args.get("sky"), scenario=scenario,
    )
    series = generate_series(
        station, scenario=scenario, sky=args.get("sky"),
        temp_min_c=args.get("temp_min_c"), temp_max_c=args.get("temp_max_c"),
    )
    return station, series, scenario


def tool_run_scenario(args: dict[str, Any]) -> dict[str, Any]:
    station, series, scenario = _resolve_station_and_series(args)
    policies = [str(p) for p in args.get("policies") or ["greedy"]]
    return {
        "scenario": scenario,
        "horizon_hours": series["horizon_hours"],
        "kpis": {name: _compact(compute_kpis(station, series, get_policy(name)(station, series)))
                 for name in policies},
    }


def tool_compare_policies(args: dict[str, Any]) -> dict[str, Any]:
    station, series, scenario = _resolve_station_and_series(args)
    kpis = {name: compute_kpis(station, series, get_policy(name)(station, series))
            for name in ("dumb", "greedy", "milp")}
    cmp = compare_kpis(kpis["greedy"], kpis["milp"], dumb=kpis["dumb"])
    return {
        "scenario": scenario,
        "kpis": {k: _compact(v) for k, v in kpis.items()},
        "comparison": cmp,
    }


TOOLS: dict[str, dict[str, Any]] = {
    "list_scenarios": {
        "description": "List the built-in stress scenarios (sky/dam/temperature overlays).",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": tool_list_scenarios,
    },
    "get_station": {
        "description": "Summarise a station file: assets, dam, bores, paddocks, herd, initial state.",
        "inputSchema": {"type": "object", "properties": {
            "station_path": {"type": "string", "description": "Path relative to repo root"},
            "station": {"type": "object", "description": "Inline station dict (overrides path)"},
        }},
        "handler": tool_get_station,
    },
    "validate_station": {
        "description": "Validate a station file against the site schema; returns structured errors.",
        "inputSchema": {"type": "object", "properties": {
            "station_path": {"type": "string"},
            "station": {"type": "object"},
        }},
        "handler": tool_validate_station,
    },
    "run_scenario": {
        "description": "Generate the exogenous series and dispatch one or more policies; returns KPIs.",
        "inputSchema": {"type": "object", "properties": {
            "scenario": {"type": "string"},
            "station_path": {"type": "string"},
            "station": {"type": "object"},
            "policies": {"type": "array", "items": {"type": "string",
                         "enum": ["dumb", "greedy", "milp"]}},
            "sky": {"type": "string", "enum": ["clear", "mixed", "overcast"]},
            "dam_kl": {"type": "number"},
            "temp_min_c": {"type": "number"},
            "temp_max_c": {"type": "number"},
        }},
        "handler": tool_run_scenario,
    },
    "compare_policies": {
        "description": "Run dumb + greedy + MILP on one scenario and return the KPI comparison.",
        "inputSchema": {"type": "object", "properties": {
            "scenario": {"type": "string"},
            "station_path": {"type": "string"},
            "station": {"type": "object"},
            "sky": {"type": "string", "enum": ["clear", "mixed", "overcast"]},
            "dam_kl": {"type": "number"},
            "temp_min_c": {"type": "number"},
            "temp_max_c": {"type": "number"},
        }},
        "handler": tool_compare_policies,
    },
}

def list_tools() -> list[dict[str, Any]]:
    return [{"name": name, "description": spec["description"],
             "inputSchema": spec["inputSchema"]}
            for name, spec in TOOLS.items()]


def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Invoke a tool handler; returns the result payload. Raises on bad name/args."""
    spec = TOOLS[name]  # KeyError -> caller maps to MCP error
    return spec["handler"](dict(arguments or {}))


def _ok(msg_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _err(msg_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


METHOD_NOT_FOUND = -32601
PARSE_ERROR = -32700
INVALID_PARAMS = -32602


def handle_message(msg: dict[str, Any]) -> dict[str, Any] | None:
    """Handle one JSON-RPC message. Returns a response dict, or None for notifications."""
    method = str(msg.get("method", ""))
    msg_id = msg.get("id")
    params = msg.get("params") or {}

    if method == "initialize":
        client_version = params.get("protocolVersion") or PROTOCOL_VERSION
        return _ok(msg_id, {
            "protocolVersion": client_version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": SERVER_INFO,
        })
    if method.startswith("notifications/"):
        return None
    if method == "ping":
        return _ok(msg_id, {})
    if method == "tools/list":
        return _ok(msg_id, {"tools": list_tools()})
    if method == "tools/call":
        name = params.get("name")
        if not isinstance(name, str) or name not in TOOLS:
            return _err(msg_id, INVALID_PARAMS, f"unknown tool: {name!r}")
        try:
            payload = call_tool(name, params.get("arguments") or {})
        except KeyError as exc:
            return _ok(msg_id, {"content": [{"type": "text", "text": f"unknown tool: {exc}"}],
                                "isError": True})
        except (ValueError, OSError, RuntimeError) as exc:
            return _ok(msg_id, {"content": [{"type": "text", "text": f"{type(exc).__name__}: {exc}"}],
                                "isError": True})
        return _ok(msg_id, {"content": [{"type": "text", "text": json.dumps(payload)}],
                            "isError": False})
    return _err(msg_id, METHOD_NOT_FOUND, f"method not found: {method}")


def serve(read_line: Callable[[], str | None], write_line: Callable[[str], None]) -> None:
    """JSON-RPC loop: one JSON message per line; exits on EOF (None or empty string)."""
    while True:
        line = read_line()
        if line is None or line == "":
            return
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError as exc:
            write_line(json.dumps(_err(None, PARSE_ERROR, f"parse error: {exc}")))
            continue
        if not isinstance(msg, dict):
            write_line(json.dumps(_err(None, PARSE_ERROR, "message must be an object")))
            continue
        response = handle_message(msg)
        if response is not None:
            write_line(json.dumps(response))


def _stdout_write(line: str) -> None:
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def main() -> int:
    serve(sys.stdin.readline, _stdout_write)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
