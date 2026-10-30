"""MCP server: handler-level tests plus an end-to-end stdio JSON-RPC session."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.mcp_server import REPO_ROOT, call_tool, handle_message, list_tools

ROOT = Path(__file__).resolve().parents[1]


def _station() -> dict:
    return json.loads((ROOT / "data" / "wirra-bore.json").read_text(encoding="utf-8"))


# --- handlers ---------------------------------------------------------------


def test_list_tools_have_schemas() -> None:
    tools = list_tools()
    names = {t["name"] for t in tools}
    assert {"list_scenarios", "get_station", "validate_station",
            "run_scenario", "compare_policies"} <= names
    for t in tools:
        assert t["description"]
        assert t["inputSchema"]["type"] == "object"


def test_validate_station_tool_clean_and_broken() -> None:
    ok = call_tool("validate_station", {"station": _station()})
    assert ok["ok"] is True and ok["errors"] == []
    broken = copy.deepcopy(_station())
    broken["phi_hourly"][0] = 0.5
    bad = call_tool("validate_station", {"station": broken})
    assert bad["ok"] is False and any("phi_hourly" in e for e in bad["errors"])


def test_get_station_tool() -> None:
    s = call_tool("get_station", {"station": _station()})
    assert s["station_id"] == "wirra-bore"
    assert s["bores"]["bore_a"]["kw"] == 11
    assert s["herd"]["cows_calves"] == 220
    assert s["schema_errors"] == []


def test_list_scenarios_tool() -> None:
    s = call_tool("list_scenarios", {})
    names = [x["name"] for x in s["scenarios"]]
    assert "wirra-summer-clear" in names and "wirra-dry" in names


def test_run_scenario_greedy_clear() -> None:
    out = call_tool("run_scenario", {"scenario": "wirra-summer-clear", "policies": ["greedy"]})
    k = out["kpis"]["greedy"]
    assert out["scenario"] == "wirra-summer-clear"
    assert k["unmet_kl_total"] == pytest.approx(0.0, abs=1e-9)
    assert k["diesel_aud"] >= 0.0
    assert "objective_aud" in k


def test_run_scenario_unknown_policy_is_error() -> None:
    with pytest.raises(KeyError):
        call_tool("run_scenario", {"policies": ["nope"]})


def test_compare_policies_ordering() -> None:
    out = call_tool("compare_policies", {"scenario": "wirra-summer-clear"})
    cmp = out["comparison"]
    assert cmp["greedy_beats_or_ties_dumb"]
    assert cmp["opt_beats_or_ties_greedy"]
    assert out["kpis"]["milp"]["objective_aud"] <= out["kpis"]["dumb"]["objective_aud"] + 1e-2


# --- JSON-RPC plumbing -------------------------------------------------------


def test_rpc_initialize_and_tools_list() -> None:
    resp = handle_message({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                           "params": {"protocolVersion": "2025-06-18"}})
    assert resp["result"]["protocolVersion"] == "2025-06-18"
    assert resp["result"]["serverInfo"]["name"] == "wirra-bore-engine"
    resp = handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert len(resp["result"]["tools"]) >= 5
    # notifications produce no response
    assert handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_rpc_tools_call_roundtrip() -> None:
    resp = handle_message({"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                           "params": {"name": "validate_station",
                                      "arguments": {"station": _station()}}})
    assert resp["result"]["isError"] is False
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert payload["ok"] is True


def test_rpc_unknown_tool_and_method() -> None:
    resp = handle_message({"jsonrpc": "2.0", "id": 8, "method": "tools/call",
                           "params": {"name": "does_not_exist", "arguments": {}}})
    assert resp["error"]["code"] == -32602
    resp = handle_message({"jsonrpc": "2.0", "id": 9, "method": "resources/list"})
    assert resp["error"]["code"] == -32601


def test_rpc_handler_error_is_tool_error() -> None:
    resp = handle_message({"jsonrpc": "2.0", "id": 10, "method": "tools/call",
                           "params": {"name": "validate_station",
                                      "arguments": {"station_path": "no/such/file.json"}}})
    assert resp["result"]["isError"] is True
    assert "FileNotFoundError" in resp["result"]["content"][0]["text"]


# --- end-to-end over stdio ----------------------------------------------------


def test_subprocess_mcp_session() -> None:
    messages = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2024-11-05"}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "run_scenario",
                    "arguments": {"scenario": "wirra-summer-clear", "policies": ["greedy"]}}},
    ]
    stdin = "\n".join(json.dumps(m) for m in messages) + "\n"
    proc = subprocess.run(
        [sys.executable, "-m", "src.mcp_server"],
        input=stdin, capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=120,
    )
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    assert len(lines) == 3, proc.stderr  # notification gets no response
    init, tools, call = (json.loads(ln) for ln in lines)
    assert init["result"]["serverInfo"]["name"] == "wirra-bore-engine"
    assert {"name": t["name"] for t in tools["result"]["tools"]} >= {"run_scenario"}
    kpis = json.loads(call["result"]["content"][0]["text"])["kpis"]["greedy"]
    assert kpis["unmet_kl_total"] == pytest.approx(0.0, abs=1e-9)
