# ADR 0002 — MCP server is hand-rolled stdio JSON-RPC

Status: accepted

## Context
The engine should be callable by agents (Cline via OpenRouter first). The official
`mcp` Python SDK would add pydantic/httpx transitive deps to a repo whose convention
is a deliberately small dependency set, and our CI runs the suite on four platforms.

## Decision
Implement the MCP stdio surface by hand in `src/mcp_server.py`: newline-delimited
JSON-RPC 2.0, methods `initialize`, `notifications/*`, `ping`, `tools/list`,
`tools/call`. Handlers are pure functions separated from the transport, so tests
cover them directly AND end-to-end via a subprocess speaking real JSON-RPC.

## Consequences
No new dependencies; ~260 lines to own. If a client compatibility gap appears,
replace the transport layer with the `mcp` SDK — the handler registry
(`TOOLS`) and tool contracts stay unchanged.
