"""Sprint 3 schematic GUI smoke tests."""

from __future__ import annotations

import json
from pathlib import Path

from src.gui import HTML_PAGE, NODE_IDS, build_payload, schematic_edges

ROOT = Path(__file__).resolve().parents[1]


def test_html_contains_layout_nodes() -> None:
    station = json.loads((ROOT / "data" / "wirra-bore.json").read_text(encoding="utf-8"))
    for node_id in station["layout"]["nodes"]:
        assert node_id in HTML_PAGE
        assert node_id in NODE_IDS


def test_html_has_playback_controls() -> None:
    for token in ("hour", "Play", "btn-play", "/api/payload", "bore_a", "dam", "btn-opt"):
        assert token in HTML_PAGE


def test_payload_includes_layout_and_dispatch() -> None:
    station = json.loads((ROOT / "data" / "wirra-bore.json").read_text(encoding="utf-8"))
    out = ROOT / "output"
    payload = build_payload(station, out)
    assert payload["station_id"] == "wirra-bore"
    assert set(payload["nodes"]) == set(station["layout"]["nodes"])
    assert payload["bus"]["kind"] == "bus"
    assert len(payload["edges"]) >= 12
    if out.joinpath("dispatch_greedy.json").exists():
        assert payload["dispatch_greedy"] is not None
        assert len(payload["dispatch_greedy"]["uA"]) == 48


def test_site_graph_edges() -> None:
    ids = {e["id"] for e in schematic_edges()}
    assert "e_pv_bus" in ids
    assert "e_dam_north" in ids
    assert "e_bore_a_dam" in ids
    domains = {e["domain"] for e in schematic_edges()}
    assert domains == {"power", "water"}
