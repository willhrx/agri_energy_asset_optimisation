"""HTTP API for the wirra-bore engine (FastAPI).

Same contract as the MCP tools, over HTTP. Run:
    uvicorn src.api:app --reload
Docs: GET /docs (OpenAPI, auto-generated).

The API is a thin adapter over src.run_service; it adds no engine logic.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src import run_service

app = FastAPI(
    title="Wirra Bore Engine API",
    description="Off-grid agri-energy dispatch: scenarios, policies, KPIs.",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # dev; tighten before any public deployment
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class RunRequest(BaseModel):
    scenario: str | None = None
    station_path: str | None = None
    station: dict[str, Any] | None = None
    policies: list[str] | None = Field(default=None,
                                       description="Defaults to ['greedy']")
    sky: str | None = None
    dam_kl: float | None = None
    temp_min_c: float | None = None
    temp_max_c: float | None = None


def _service_call(fn, args: dict[str, Any]) -> dict[str, Any]:
    """Map service-layer errors to HTTP status codes (ValueError->400, missing->404)."""
    try:
        return fn(args)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=f"unknown key: {exc}") from exc


@app.get("/health")
def health() -> dict[str, Any]:
    station = run_service.load_station({})
    return {"status": "ok", "station_id": station["station_id"],
            "schema_errors": run_service.validate_station(station)}


@app.get("/scenarios")
def scenarios() -> dict[str, Any]:
    return {"scenarios": run_service.scenario_list(),
            "policies": list(run_service.POLICY_NAMES)}


@app.get("/station")
def station(station_path: str | None = None) -> dict[str, Any]:
    return _service_call(lambda a: run_service.station_summary(run_service.load_station(a)),
                         {"station_path": station_path})


@app.post("/runs")
def runs(req: RunRequest) -> dict[str, Any]:
    station, series, scenario = _service_call(run_service.prepare_run, req.model_dump())
    policies = req.policies or ["greedy"]
    try:
        kpis = run_service.run_policies(station, series, policies)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"scenario": scenario, "horizon_hours": series["horizon_hours"], "kpis": kpis}


@app.post("/compare")
def compare(req: RunRequest) -> dict[str, Any]:
    station, series, scenario = _service_call(run_service.prepare_run, req.model_dump())
    return run_service.run_comparison(station, series, scenario)
