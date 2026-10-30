"""Minimal MCP (Model Context Protocol) stdio server for the wirra-bore engine.

Exposes the dispatch engine as agent-callable tools over newline-delimited
JSON-RPC 2.0 on stdin/stdout (see docs/adr/0002-mcp-stdio.md for why this is
hand-rolled rather than using the official SDK).

Run:  python -m src.mcp_server   (cwd = repo root)
"""

from __future__ import annotations

import json
import sys
from typing import Any, Callable

from src.run_service import (
    load_station,
    prepare_run,
    run_comparison,
    run_policies,
    scenario_list,
    station_summary,
    validate_station,
)

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "wirra-bore-engine", "version": "0.1.0"}


def tool_list_scenarios(args: dict[str, Any]) -> dict[str, Any]:
    return {"scenarios": scenario_list()}


def tool_get_station(args: dict[str, Any]) -> dict[str, Any]:
    return station_summary(load_station(args))


def tool_validate_station(args: dict[str, Any]) -> dict[str, Any]:
    st = load_station(args)
    errors = validate_station(st)
    return {"ok": not errors, "errors": errors, "station_id": st.get("station_id")}


def tool_run_scenario(args: dict[str, Any]) -> dict[str, Any]:
    station, series, scenario = prepare_run(args)
    policies = [str(p) for p in args.get("policies") or ["greedy"]]
    return {
        "scenario": scenario,
        "horizon_hours": series["horizon_hours"],
        "kpis": run_policies(station, series, policies),
    }


def tool_compare_policies(args: dict[str, Any]) -> dict[str, Any]:
    station, series, scenario = prepare_run(args)
    return run_comparison(station, series, scenario)


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
