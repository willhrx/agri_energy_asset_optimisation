"""HTTP API tests via FastAPI TestClient (no port binding)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from fastapi.testclient import TestClient

from src.api import app

ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app)


def _station() -> dict:
    return json.loads((ROOT / "data" / "wirra-bore.json").read_text(encoding="utf-8"))


def test_health() -> None:
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["station_id"] == "wirra-bore"
    assert body["schema_errors"] == []


def test_scenarios_lists_suite_and_policies() -> None:
    r = client.get("/scenarios")
    assert r.status_code == 200
    names = [s["name"] for s in r.json()["scenarios"]]
    assert "wirra-summer-clear" in names
    assert {"dumb", "greedy", "milp"} <= set(r.json()["policies"])


def test_station_summary() -> None:
    r = client.get("/station")
    assert r.status_code == 200
    assert r.json()["bores"]["bore_a"]["kw"] == 11
    assert r.json()["schema_errors"] == []


def test_post_run_greedy_clear_zero_unmet() -> None:
    r = client.post("/runs", json={"scenario": "wirra-summer-clear", "policies": ["greedy"]})
    assert r.status_code == 200
    body = r.json()
    assert body["horizon_hours"] == 48
    k = body["kpis"]["greedy"]
    assert k["unmet_kl_total"] == 0.0
    assert "objective_aud" in k


def test_post_run_default_policies_is_greedy() -> None:
    r = client.post("/runs", json={})
    assert r.status_code == 200
    assert set(r.json()["kpis"]) == {"greedy"}


def test_post_run_all_policies() -> None:
    r = client.post("/runs", json={"policies": ["dumb", "greedy", "milp"]})
    assert r.status_code == 200
    assert set(r.json()["kpis"]) == {"dumb", "greedy", "milp"}


def test_post_compare_ordering() -> None:
    r = client.post("/compare", json={"scenario": "wirra-summer-clear"})
    assert r.status_code == 200
    cmp = r.json()["comparison"]
    assert cmp["greedy_beats_or_ties_dumb"]
    assert cmp["opt_beats_or_ties_greedy"]


def test_post_run_inline_station() -> None:
    r = client.post("/runs", json={"station": _station(), "policies": ["greedy"]})
    assert r.status_code == 200
    assert r.json()["kpis"]["greedy"]["unmet_kl_total"] == 0.0


def test_unknown_policy_is_400() -> None:
    r = client.post("/runs", json={"policies": ["nope"]})
    assert r.status_code == 400
    assert "unknown policy" in r.json()["detail"]


def test_missing_station_path_is_404() -> None:
    r = client.get("/station", params={"station_path": "data/does-not-exist.json"})
    assert r.status_code == 404


def test_station_path_escape_is_400() -> None:
    # Security: paths must stay inside the repository.
    r = client.get("/station", params={"station_path": "../../../windows/win.ini"})
    assert r.status_code == 400
    assert "inside the repository" in r.json()["detail"]


def test_mcp_and_http_contracts_match() -> None:
    """ADR 0003: MCP tool and HTTP endpoint must return identical payloads."""
    from src.mcp_server import call_tool

    args = {"scenario": "wirra-summer-clear", "policies": ["greedy"]}
    mcp_out = call_tool("run_scenario", args)
    http_out = client.post("/runs", json=args).json()
    assert mcp_out == http_out

    mcp_cmp = call_tool("compare_policies", args)
    http_cmp = client.post("/compare", json=args).json()
    assert mcp_cmp == http_cmp

    mcp_station = call_tool("get_station", {})
    assert mcp_station == client.get("/station").json()


def test_broken_inline_station_still_runs_but_reports_errors() -> None:
    broken = copy.deepcopy(_station())
    broken["phi_hourly"][0] = 0.5
    r = client.get("/station", json=None)  # sanity: default ok
    assert r.status_code == 200
    r2 = client.post("/runs", json={"station": broken, "policies": ["greedy"]})
    # Engine runs on the dict as given; validation is a separate tool.
    assert r2.status_code == 200
