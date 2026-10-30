# ADR 0003 — Service layer + FastAPI HTTP API

Status: accepted

## Context
MCP tools and the coming client-facing frontend both need the same operations:
load/validate a station, run policies, compare baselines. Duplicating that logic
across transports guarantees drift (the same class of bug as ADR-reviewed
dispatch code). A real HTTP API also needs a real framework; hand-rolling HTTP
would repeat the `http.server` pattern in `src/gui.py` with worse ergonomics.

## Decision
1. `src/run_service.py` is the single service layer: station loading (with
   repo-confinement), scenario overlays, policy runs, comparisons, summaries.
   The MCP server now delegates to it; the API does too.
2. `src/api.py` is a thin FastAPI adapter over the service layer — it adds no
   engine logic and maps service errors to HTTP codes (400/404).
3. New dependencies accepted: `fastapi`, `uvicorn`, `httpx` (test client).
   This is the first deliberate dependency expansion; it is product-driven.

## Consequences
- `station_path` is confined to the repository in ALL transports (fixes an
  arbitrary-file-read path that existed in the MCP `get_station`/`validate_station`
  tools since 0002).
- Contract drift between MCP and HTTP is now impossible by construction.
- CORS is open for local development; must be tightened before any deployment.
