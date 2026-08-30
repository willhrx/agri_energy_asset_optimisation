"""Sprint 3 schematic GUI: layout.x/y + dispatch playback over stdlib http.server.

  python -m src.gui

Serves an HTML site graph (nodes from data/wirra-bore.json layout.nodes,
plus a derived bus). Playback reads output/dispatch_greedy.json and, if
present, output/dispatch_opt.json. No solver is imported or run.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

NODE_IDS = (
    "homestead",
    "pv",
    "battery",
    "diesel",
    "dam",
    "bore_a",
    "bore_b",
    "north",
    "creek",
    "dam_paddock",
    "back",
)

HEADERS = ("north", "creek", "dam_paddock", "back")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_json(path: Path) -> Any | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def bus_node(nodes: dict[str, Any]) -> dict[str, Any]:
    """Bus is not in layout.nodes; sit it under the homestead power cluster."""
    keys = ("pv", "battery", "diesel", "homestead")
    xs = [float(nodes[k]["x"]) for k in keys if k in nodes]
    ys = [float(nodes[k]["y"]) for k in keys if k in nodes]
    return {
        "x": sum(xs) / len(xs),
        "y": sum(ys) / len(ys) + 32,
        "kind": "bus",
    }


def schematic_edges() -> list[dict[str, str]]:
    """PROBLEM.md §2: PV/diesel/battery–bus; bus→homestead+bores; bores→dam; dam→headers."""
    power_to_bus = [
        {"id": "e_pv_bus", "src": "pv", "dst": "bus", "domain": "power"},
        {"id": "e_diesel_bus", "src": "diesel", "dst": "bus", "domain": "power"},
        {"id": "e_battery_bus", "src": "battery", "dst": "bus", "domain": "power"},
    ]
    bus_to_loads = [
        {"id": "e_bus_homestead", "src": "bus", "dst": "homestead", "domain": "power"},
        {"id": "e_bus_bore_a", "src": "bus", "dst": "bore_a", "domain": "power"},
        {"id": "e_bus_bore_b", "src": "bus", "dst": "bore_b", "domain": "power"},
    ]
    bores_to_dam = [
        {"id": "e_bore_a_dam", "src": "bore_a", "dst": "dam", "domain": "water"},
        {"id": "e_bore_b_dam", "src": "bore_b", "dst": "dam", "domain": "water"},
    ]
    dam_to_headers = [
        {"id": f"e_dam_{p}", "src": "dam", "dst": p, "domain": "water"} for p in HEADERS
    ]
    return power_to_bus + bus_to_loads + bores_to_dam + dam_to_headers


def build_payload(station: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    nodes = dict(station.get("layout", {}).get("nodes", {}))
    missing = [n for n in NODE_IDS if n not in nodes]
    if missing:
        raise KeyError(f"layout.nodes missing {missing}")
    water = station["water"]
    power = station["power"]
    return {
        "station_id": station.get("station_id", "wirra-bore"),
        "timezone": station.get("timezone", "Australia/Sydney"),
        "horizon_hours": int(station.get("horizon_hours", 48)),
        "nodes": nodes,
        "bus": bus_node(nodes),
        "edges": schematic_edges(),
        "node_ids": list(NODE_IDS),
        "headers": list(HEADERS),
        "bores": {
            name: {
                "kw": float(spec["kw"]),
                "litres_per_s": float(spec["litres_per_s"]),
                "kl_per_h": float(spec["litres_per_s"]) * 3.6,
            }
            for name, spec in water["bores"].items()
        },
        "header_kl": {p: float(water["paddocks"][p]["header_kl"]) for p in HEADERS},
        "dam_reserve_kl": float(water["dam_reserve_kl"]),
        "dam_spill_kl": float(water["dam_spill_kl"]),
        "battery_kwh": float(power["battery_kwh"]),
        "soc_min_frac": float(power["soc_min_frac"]),
        "soc_max_frac": float(power["soc_max_frac"]),
        "inverter_ac_kw": float(power["inverter_ac_kw"]),
        "series": load_json(output_dir / "series.json"),
        "dispatch_dumb": load_json(output_dir / "dispatch_dumb.json"),
        "dispatch_greedy": load_json(output_dir / "dispatch_greedy.json"),
        "dispatch_opt": load_json(output_dir / "dispatch_opt.json"),
        "kpis": load_json(output_dir / "kpis.json"),
        "kpis_dumb": load_json(output_dir / "kpis_dumb.json"),
        "kpis_opt": load_json(output_dir / "kpis_opt.json"),
        "compare": load_json(output_dir / "compare.json"),
        "suite": load_json(output_dir / "suite.json"),
    }


HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Wirra Bore — western NSW watering cell</title>
  <link rel="preconnect" href="https://fonts.googleapis.com"/>
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>
  <link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,650&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet"/>
  <style>
    :root {
      --bg: #14110d;
      --panel: rgba(22, 19, 15, 0.92);
      --ink: #f3ead6;
      --muted: #b7a88a;
      --line: rgba(243, 234, 214, 0.12);
      --power: #e8c15a;
      --water: #5ec4d4;
      --accent: #e2c27a;
      --diesel: #e07048;
      --ok: #7dba6a;
    }
    * { box-sizing: border-box; }
    html, body { margin: 0; height: 100%; background: var(--bg); color: var(--ink);
      font-family: "IBM Plex Sans", system-ui, sans-serif; }
    body { display: grid; grid-template-rows: auto 1fr auto; min-height: 100%; }
    header, footer { padding: 14px 22px; background: var(--panel);
      backdrop-filter: blur(12px); }
    header { display: flex; align-items: center; gap: 18px; flex-wrap: wrap;
      border-bottom: 1px solid var(--line); }
    header h1 { font-family: Fraunces, Georgia, serif; font-size: 1.35rem; margin: 0;
      font-weight: 650; letter-spacing: 0.01em; }
    header p { margin: 2px 0 0; color: var(--muted); font-size: 0.78rem; }
    .brand { display: flex; flex-direction: column; }
    #policy { margin-left: auto; display: flex; gap: 0; background: #1c1813;
      border: 1px solid var(--line); border-radius: 999px; padding: 3px; }
    #policy button {
      background: transparent; color: var(--muted); border: 0;
      border-radius: 999px; padding: 7px 16px; cursor: pointer; font: inherit;
      font-size: 0.82rem; font-weight: 500; transition: background 0.2s, color 0.2s;
    }
    #policy button.active { background: var(--accent); color: #1a1408; }
    #policy button:disabled { opacity: 0.35; cursor: not-allowed; }
    main { display: grid; grid-template-columns: 1fr minmax(280px, 320px); min-height: 0; }
    #stage { position: relative; min-height: 0; background: #1a1610; overflow: hidden; }
    #schematic { width: 100%; height: 100%; min-height: 560px; display: block;
      cursor: grab; touch-action: none; user-select: none; }
    #schematic.is-panning { cursor: grabbing; }
    .zoom-dock {
      position: absolute; left: 14px; bottom: 14px; display: flex; gap: 6px; align-items: center;
      background: rgba(22, 19, 15, 0.82); border: 1px solid var(--line); border-radius: 999px;
      padding: 4px 6px 4px 8px; backdrop-filter: blur(10px);
    }
    .zoom-dock button {
      width: 32px; height: 32px; border: 0; border-radius: 999px; cursor: pointer;
      background: #2a241c; color: var(--ink); font: 600 16px "IBM Plex Sans", sans-serif;
    }
    .zoom-dock button:hover { background: var(--accent); color: #1a1408; }
    #zoom-label { min-width: 48px; text-align: center; font-size: 0.75rem; color: var(--muted); font-weight: 600; }
    .zoom-hint { position: absolute; right: 14px; bottom: 18px; color: var(--muted);
      font-size: 0.72rem; letter-spacing: 0.04em; pointer-events: none; opacity: 0.75; }
    aside { border-left: 1px solid var(--line); padding: 18px 18px 24px; overflow: auto;
      background: #17130f; font-variant-numeric: tabular-nums; }
    aside h2 { font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.16em;
      color: var(--muted); margin: 18px 0 8px; font-weight: 600; }
    aside h2:first-child { margin-top: 0; }
    aside dl { margin: 0 0 4px; display: grid; grid-template-columns: 1fr auto; gap: 7px 12px; }
    aside dt { color: var(--muted); font-size: 0.78rem; }
    aside dd { margin: 0; font-size: 0.82rem; text-align: right; font-weight: 500; }
    aside .warn { color: var(--diesel); }
    .meter { height: 6px; background: #2a241c; border-radius: 99px; overflow: hidden; margin: 6px 0 14px; }
    .meter > i { display: block; height: 100%; border-radius: 99px; background: var(--water);
      width: 0; transition: width 0.45s ease; }
    .meter.soc > i { background: var(--ok); }
    footer { display: flex; align-items: center; gap: 16px; border-top: 1px solid var(--line); }
    #btn-play {
      min-width: 88px; padding: 9px 16px; border-radius: 999px; border: 0;
      background: var(--accent); color: #1a1408; font: inherit; font-weight: 600; cursor: pointer;
    }
    #hour { flex: 1; accent-color: var(--accent); height: 6px; }
    #hour-label { min-width: 240px; color: var(--muted); font-size: 0.82rem; }
    .chip { display: inline-block; padding: 2px 8px; border-radius: 99px; background: #2a241c;
      font-size: 0.72rem; color: var(--accent); letter-spacing: 0.04em; }
    .node-label { fill: #3a2c1c; font-size: 11px; font-family: "IBM Plex Sans", sans-serif; font-weight: 600; }
    .node-sub { fill: #5c4a32; font-size: 10px; font-family: "IBM Plex Sans", sans-serif; }
    .lbl-halo { fill: rgba(255,248,230,0.86); }
    .edge-power { stroke: var(--power); fill: none; stroke-linecap: round; opacity: 0.9; }
    .edge-water { stroke: var(--water); fill: none; stroke-linecap: round; opacity: 0.9; }
    .edge-idle { opacity: 0.18; }
    .flow-on { stroke-dasharray: 8 10; animation: dash 0.85s linear infinite; }
    .flow-on.edge-water { animation-duration: 1.15s; }
    @keyframes dash { to { stroke-dashoffset: -36; } }
    @keyframes pump { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-3px); } }
    @keyframes shimmer { 0%,100% { opacity: 0.75; } 50% { opacity: 1; } }
    @keyframes stack { 0%,100% { opacity: 0.35; transform: translateY(0); } 50% { opacity: 0.9; transform: translateY(-6px); } }
    @keyframes ripple { 0%,100% { transform: scale(1); opacity: 0.35; } 50% { transform: scale(1.06); opacity: 0.6; } }
    .on-pump .pump-head { animation: pump 0.55s ease-in-out infinite; }
    .on-pv .panel { animation: shimmer 2.2s ease-in-out infinite; }
    .on-diesel .smoke { animation: stack 1.4s ease-in-out infinite; }
    .on-dam .water-shine { animation: shimmer 3s ease-in-out infinite; }
    .win-on { fill: #f6e39a !important; filter: url(#glow); }
    .banner { fill: #c45c4c; font-size: 14px; font-family: "IBM Plex Sans", sans-serif; }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <h1>Wirra Bore</h1>
      <p>western NSW watering cell · homestead · yards · turkey-nest dam</p>
    </div>
    <span class="chip" id="tod-chip">day</span>
    <div id="policy">
      <button type="button" id="btn-dumb" data-policy="dumb" disabled title="No output/dispatch_dumb.json">Dumb</button>
      <button type="button" id="btn-greedy" class="active" data-policy="greedy">Greedy</button>
      <button type="button" id="btn-opt" data-policy="opt" disabled title="No output/dispatch_opt.json">Opt</button>
    </div>
  </header>
  <main>
    <div id="stage">
      <svg id="schematic" viewBox="0 0 1080 700" role="img" aria-label="Wirra Bore station schematic">
        <title>Wirra Bore site graph</title>
      </svg>
      <div class="zoom-dock">
        <button type="button" id="btn-zoom-out" title="Zoom out">−</button>
        <span id="zoom-label">100%</span>
        <button type="button" id="btn-zoom-in" title="Zoom in">+</button>
        <button type="button" id="btn-zoom-fit" title="Fit station">Fit</button>
      </div>
      <div class="zoom-hint">scroll to zoom · drag to pan · double-click a building</div>
    </div>
    <aside id="readout"></aside>
  </main>
  <footer>
    <button type="button" id="btn-play">Play</button>
    <input type="range" id="hour" min="0" max="47" value="0" step="1"/>
    <span id="hour-label">hour 0 / 47</span>
  </footer>
  <script>
  const NODE_IDS = ["homestead","pv","battery","diesel","dam","bore_a","bore_b","north","creek","dam_paddock","back"];
  const SCALE = 1.85, PAD_X = 70, PAD_Y = 55;
  const NS = "http://www.w3.org/2000/svg";
  let payload = null, policy = "greedy", hour = 0, playing = false, timer = null;

  function E(tag, a, kids) {
    const n = document.createElementNS(NS, tag);
    if (a) Object.keys(a).forEach(function (k) { if (a[k] != null && a[k] !== "") n.setAttribute(k, a[k]); });
    (kids || []).forEach(function (c) {
      if (c == null) return;
      if (typeof c === "string") n.appendChild(document.createTextNode(c));
      else n.appendChild(c);
    });
    return n;
  }

  function pos(id) {
    const n = id === "bus" ? payload.bus : payload.nodes[id];
    return { x: n.x * SCALE + PAD_X, y: n.y * SCALE + PAD_Y };
  }

  function dispatch() {
    if (policy === "opt" && payload.dispatch_opt) return payload.dispatch_opt;
    if (policy === "dumb" && payload.dispatch_dumb) return payload.dispatch_dumb;
    return payload.dispatch_greedy;
  }

  function series() { return payload.series; }

  function at(obj, key, t, fallback) {
    if (!obj || obj[key] == null) return fallback;
    const v = obj[key][t];
    return v == null ? fallback : v;
  }

  function atMap(obj, name, t, fallback) {
    if (!obj || obj[name] == null || obj[name][t] == null) return fallback;
    return obj[name][t];
  }

  function fmt(n, digits) {
    if (n == null || Number.isNaN(n)) return "—";
    return Number(n).toFixed(digits);
  }

  function flows(t) {
    const d = dispatch() || {};
    const s = series() || {};
    const bores = payload.bores || {};
    const uA = Number(at(d, "uA", t, 0));
    const uB = Number(at(d, "uB", t, 0));
    const pvUsed = Number(at(d, "pv_used_kw", t, at(s, "pv_kw", t, 0)));
    const g = Number(at(d, "g_kw", t, 0));
    const c = Number(at(d, "c_kw", t, 0));
    const dis = Number(at(d, "d_kw", t, 0));
    const f = {};
    for (const p of payload.headers) f[p] = Number(atMap(d.f_kl || {}, p, t, 0));
    return {
      e_pv_bus: Math.max(0, pvUsed),
      e_diesel_bus: Math.max(0, g),
      e_battery_bus: Math.max(c, dis),
      battery_dir: dis >= c ? 1 : -1,
      e_bus_homestead: Number(at(s, "homestead_kw", t, 0)),
      e_bus_bore_a: uA * (bores.bore_a ? bores.bore_a.kw : 11),
      e_bus_bore_b: uB * (bores.bore_b ? bores.bore_b.kw : 15),
      e_bore_a_dam: uA * (bores.bore_a ? bores.bore_a.kl_per_h : 14.4),
      e_bore_b_dam: uB * (bores.bore_b ? bores.bore_b.kl_per_h : 21.6),
      e_dam_north: f.north || 0,
      e_dam_creek: f.creek || 0,
      e_dam_dam_paddock: f.dam_paddock || 0,
      e_dam_back: f.back || 0,
      uA, uB, g, c, dis,
      pv: Number(at(s, "pv_kw", t, 0)),
      load: Number(at(s, "homestead_kw", t, 0)),
      S: Number(at(d, "S_kwh", t, 0)),
      V: Number(at(d, "V_kl", t, 0)),
      temp: Number(at(s, "temp_c", t, 0)),
    };
  }

  function nodeKind(id) {
    if (id === "bus") return "bus";
    return (payload.nodes[id] && payload.nodes[id].kind) || "load";
  }

  function subtitle(id, fl, t) {
    const d = dispatch() || {};
    if (id === "pv") return fmt(fl.pv, 1) + " kW";
    if (id === "battery") return fmt(fl.S, 1) + " kWh";
    if (id === "diesel") return fl.g > 0.05 ? fmt(fl.g, 1) + " kW" : "off";
    if (id === "homestead") return fmt(fl.load, 1) + " kW";
    if (id === "dam") return fmt(fl.V, 0) + " kL";
    if (id === "bore_a") return fl.uA ? "ON 4 L/s" : "off";
    if (id === "bore_b") return fl.uB ? "ON 6 L/s" : "off";
    if (id === "bus") return "switchboard";
    if (payload.headers.indexOf(id) >= 0) {
      const w = atMap((d.W_kl || {}), id, t, 0);
      const dem = atMap(((series() || {}).demand_kl_per_h || {}), id, t, 0);
      return fmt(w, 1) + " kL · " + fmt(dem, 2) + " kL/h";
    }
    return "";
  }

  function prettyName(id) {
    return {
      homestead: "Homestead",
      pv: "PV array",
      battery: "Battery",
      diesel: "Diesel shed",
      dam: "Turkey-nest dam",
      bore_a: "Bore A",
      bore_b: "Bore B",
      north: "North paddock",
      creek: "Creek paddock",
      dam_paddock: "Dam paddock",
      back: "Back paddock",
      bus: "AC bus",
    }[id] || id;
  }

  function hourPhase(h) {
    const hr = h % 24;
    if (hr < 5 || hr >= 21) return "night";
    if (hr < 7) return "dawn";
    if (hr < 17) return "day";
    if (hr < 19) return "dusk";
    return "night";
  }

  function addDefs(svg) {
    const defs = E("defs");
    defs.appendChild(E("linearGradient", { id: "skyGrad", x1: "0", y1: "0", x2: "0", y2: "1" }, [
      E("stop", { id: "skyTop", offset: "0%", "stop-color": "#8ec4d8" }),
      E("stop", { id: "skyBot", offset: "100%", "stop-color": "#f2ddb0" }),
    ]));
    defs.appendChild(E("linearGradient", { id: "earthGrad", x1: "0", y1: "0", x2: "0", y2: "1" }, [
      E("stop", { offset: "0%", "stop-color": "#d7b07a" }),
      E("stop", { offset: "100%", "stop-color": "#9a6d3c" }),
    ]));
    defs.appendChild(E("radialGradient", { id: "waterGrad", cx: "40%", cy: "35%", r: "70%" }, [
      E("stop", { offset: "0%", "stop-color": "#8fd4de" }),
      E("stop", { offset: "100%", "stop-color": "#2f7f8f" }),
    ]));
    defs.appendChild(E("filter", { id: "glow", x: "-40%", y: "-40%", width: "180%", height: "180%" }, [
      E("feGaussianBlur", { stdDeviation: "2.2", result: "b" }),
      E("feMerge", {}, [E("feMergeNode", { in: "b" }), E("feMergeNode", { in: "SourceGraphic" })]),
    ]));
    defs.appendChild(E("filter", { id: "soft", x: "-20%", y: "-20%", width: "140%", height: "140%" }, [
      E("feDropShadow", { dx: "0", dy: "1.5", stdDeviation: "1.6", "flood-color": "#3a2a18", "flood-opacity": "0.35" }),
    ]));
    defs.appendChild(E("clipPath", { id: "damClip" }, [
      E("ellipse", { cx: "0", cy: "4", rx: "46", ry: "22" }),
    ]));
    svg.appendChild(defs);
  }

  function labelPair(g, x, y, title, dy) {
    const bg = E("rect", { class: "lbl-halo", x: x - 52, y: y + (dy || 28) - 11, width: 104, height: 28, rx: "6" });
    g.appendChild(bg);
    g.appendChild(E("text", { class: "node-label", x: x, y: y + (dy || 28), "text-anchor": "middle" }, [title]));
    g.appendChild(E("text", { class: "node-sub", id: "sub-" + g.dataset.id, x: x, y: y + (dy || 28) + 12, "text-anchor": "middle" }));
  }

  function drawHouse(g, x, y) {
    g.appendChild(E("ellipse", { cx: x + 4, cy: y + 28, rx: "48", ry: "10", fill: "#7d5a32", opacity: "0.25" }));
    g.appendChild(E("rect", { x: x - 34, y: y - 2, width: "68", height: "26", fill: "#efe1c4", stroke: "#6a5438", "stroke-width": "1.2" }));
    g.appendChild(E("polygon", { points: (x-40)+","+(y-2)+" "+x+","+(y-26)+" "+(x+40)+","+(y-2), fill: "#8c3b28", stroke: "#5a2418", "stroke-width": "1" }));
    g.appendChild(E("rect", { x: x - 38, y: y + 16, width: "76", height: "4", fill: "#d9c39a" }));
    g.appendChild(E("line", { x1: x - 28, y1: y + 16, x2: x - 28, y2: y + 26, stroke: "#6a5438", "stroke-width": "2" }));
    g.appendChild(E("line", { x1: x + 28, y1: y + 16, x2: x + 28, y2: y + 26, stroke: "#6a5438", "stroke-width": "2" }));
    g.appendChild(E("rect", { class: "win", x: x - 22, y: y + 4, width: "10", height: "10", fill: "#8fb4c4", stroke: "#5a4632" }));
    g.appendChild(E("rect", { class: "win", x: x + 12, y: y + 4, width: "10", height: "10", fill: "#8fb4c4", stroke: "#5a4632" }));
    g.appendChild(E("rect", { x: x - 4, y: y + 6, width: "8", height: "18", fill: "#6b4a32" }));
    g.appendChild(E("rect", { x: x + 22, y: y - 22, width: "6", height: "12", fill: "#6a3224" }));
    g.appendChild(E("ellipse", { cx: x - 48, cy: y + 18, rx: "9", ry: "12", fill: "#c9c2b3", stroke: "#6a5438" }));
    g.appendChild(E("ellipse", { cx: x - 48, cy: y + 10, rx: "9", ry: "5", fill: "#9aa3a8" }));
  }

  function drawYards(g, x, y) {
    const ox = x + 56, oy = y + 8;
    g.appendChild(E("rect", { x: ox, y: oy, width: "52", height: "34", fill: "none", stroke: "#5c4630", "stroke-width": "2.2" }));
    g.appendChild(E("line", { x1: ox + 26, y1: oy, x2: ox + 26, y2: oy + 34, stroke: "#5c4630", "stroke-width": "1.6" }));
    g.appendChild(E("line", { x1: ox, y1: oy + 17, x2: ox + 52, y2: oy + 17, stroke: "#5c4630", "stroke-width": "1.6" }));
    g.appendChild(E("text", { x: ox + 26, y: oy + 46, "text-anchor": "middle", fill: "#5c4630", "font-size": "9", "font-family": "IBM Plex Sans, sans-serif" }, ["cattle yards"]));
  }

  function drawPv(g, x, y) {
    for (let i = 0; i < 3; i++) {
      const px = x - 28 + i * 18;
      g.appendChild(E("polygon", { class: "panel", points: px+","+(y+10)+" "+(px+22)+","+(y+4)+" "+(px+22)+","+(y-10)+" "+px+","+(y-4), fill: "#2a4e72", stroke: "#d8c078", "stroke-width": "1" }));
    }
    g.appendChild(E("line", { x1: x - 30, y1: y + 12, x2: x + 30, y2: y + 12, stroke: "#6a5438", "stroke-width": "3" }));
  }

  function drawBattery(g, x, y) {
    g.appendChild(E("rect", { x: x - 22, y: y - 14, width: "44", height: "28", rx: "4", fill: "#3d4a3a", stroke: "#1e281c" }));
    g.appendChild(E("rect", { id: "batt-fill", x: x - 18, y: y - 10, width: "36", height: "20", rx: "2", fill: "#5cb87a" }));
    g.appendChild(E("rect", { x: x - 6, y: y - 18, width: "12", height: "5", rx: "1", fill: "#c9c2b3" }));
  }

  function drawDiesel(g, x, y) {
    g.appendChild(E("rect", { x: x - 22, y: y - 8, width: "44", height: "22", fill: "#6b6e72", stroke: "#3a3c40" }));
    g.appendChild(E("polygon", { points: (x-26)+","+(y-8)+" "+x+","+(y-20)+" "+(x+26)+","+(y-8), fill: "#5a5e62" }));
    g.appendChild(E("rect", { class: "stack", x: x + 10, y: y - 28, width: "5", height: "14", fill: "#3a3c40" }));
    g.appendChild(E("ellipse", { class: "smoke", cx: x + 12, cy: y - 32, rx: "5", ry: "3", fill: "#c9c2b3", opacity: "0.3" }));
  }

  function drawDam(g, x, y) {
    g.appendChild(E("ellipse", { cx: x, cy: y + 6, rx: "58", ry: "28", fill: "#8a6236" }));
    g.appendChild(E("ellipse", { cx: x, cy: y + 4, rx: "46", ry: "22", fill: "#6d4c2c" }));
    const waterG = E("g", { "clip-path": "url(#damClip)", transform: "translate("+x+","+y+")" });
    waterG.appendChild(E("ellipse", { id: "dam-water", class: "water-shine", cx: "0", cy: "4", rx: "44", ry: "20", fill: "url(#waterGrad)" }));
    g.appendChild(waterG);
    g.appendChild(E("ellipse", { cx: x, cy: y + 4, rx: "46", ry: "22", fill: "none", stroke: "#5a3c22", "stroke-width": "2" }));
  }

  function drawBore(g, x, y) {
    const head = E("g", { class: "pump-head" });
    head.appendChild(E("rect", { x: x - 10, y: y - 6, width: "20", height: "16", rx: "2", fill: "#8a9094", stroke: "#3a3c40" }));
    head.appendChild(E("rect", { x: x - 3, y: y - 22, width: "6", height: "16", fill: "#6a6e72" }));
    head.appendChild(E("circle", { cx: x, cy: y - 24, r: "7", fill: "#c9c2b3", stroke: "#5a5438" }));
    g.appendChild(head);
    g.appendChild(E("rect", { x: x + 8, y: y + 2, width: "14", height: "10", rx: "2", fill: "#9aa3a8", stroke: "#5a5438" }));
  }

  function drawPaddock(g, x, y, empty) {
    const fill = empty ? "#8a9a6a" : "#6f8a44";
    g.appendChild(E("rect", { x: x - 40, y: y - 22, width: "80", height: "44", rx: "8", fill: fill, stroke: "#4a5c30", "stroke-width": "1.6", "stroke-dasharray": "6 4", opacity: "0.92" }));
    g.appendChild(E("rect", { x: x - 10, y: y + 6, width: "20", height: "8", rx: "2", fill: "#6aa0b0", stroke: "#3a5a62" }));
    if (!empty) {
      g.appendChild(E("ellipse", { cx: x - 18, cy: y - 4, rx: "6", ry: "4", fill: "#cfc6b0", opacity: "0.7" }));
      g.appendChild(E("ellipse", { cx: x + 8, cy: y - 8, rx: "7", ry: "4", fill: "#d5ccb6", opacity: "0.7" }));
    }
  }

  function drawBus(g, x, y) {
    g.appendChild(E("rect", { x: x - 6, y: y - 28, width: "12", height: "40", fill: "#6a6e66" }));
    g.appendChild(E("rect", { x: x - 16, y: y - 8, width: "32", height: "18", rx: "2", fill: "#2a2c28", stroke: "#d8c078" }));
    g.appendChild(E("circle", { cx: x - 8, cy: y + 1, r: "3", fill: "#7dba6a" }));
    g.appendChild(E("circle", { cx: x + 8, cy: y + 1, r: "3", fill: "#e8c15a" }));
  }

  function glyph(id, p) {
    const g = E("g", { id: "node-" + id, "data-id": id, filter: "url(#soft)" });
    g.dataset.id = id;
    const kind = nodeKind(id);
    if (id === "homestead") { drawHouse(g, p.x, p.y); drawYards(g, p.x, p.y); }
    else if (kind === "pv") drawPv(g, p.x, p.y);
    else if (kind === "battery") drawBattery(g, p.x, p.y);
    else if (kind === "diesel") drawDiesel(g, p.x, p.y);
    else if (kind === "dam") drawDam(g, p.x, p.y);
    else if (kind === "bore") drawBore(g, p.x, p.y);
    else if (kind === "paddock") drawPaddock(g, p.x, p.y, id === "back");
    else if (kind === "bus") drawBus(g, p.x, p.y);
    labelPair(g, p.x, p.y, prettyName(id), kind === "dam" ? 40 : 32);
    return g;
  }

  function buildSvg() {
    const svg = document.getElementById("schematic");
    svg.innerHTML = "";
    addDefs(svg);
    const world = E("g", { id: "world" });
    world.appendChild(E("rect", { id: "sky", width: "1080", height: "700", fill: "url(#skyGrad)" }));
    world.appendChild(E("path", { d: "M0 210 C 180 170 320 230 480 190 C 680 140 820 210 1080 160 L 1080 700 L 0 700 Z", fill: "url(#earthGrad)" }));
    world.appendChild(E("path", { d: "M0 250 C 200 220 400 280 600 240 C 800 200 960 260 1080 230 L 1080 700 L 0 700 Z", fill: "#c4a06a", opacity: "0.55" }));
    world.appendChild(E("path", { d: "M0 430 C 140 410 280 450 420 420 C 620 380 860 440 1080 400 L 1080 700 L 0 700 Z", fill: "#b48a52", opacity: "0.35" }));

    if (!payload) return;
    if (!payload.series || !payload.dispatch_greedy) {
      world.appendChild(E("text", { x: "80", y: "80", class: "banner" }, ["Run python -m src.run first (missing output/series.json or dispatch_greedy.json)"]));
    }

    const gEdges = E("g", { id: "edges" });
    world.appendChild(gEdges);
    for (const e of payload.edges) {
      const a = pos(e.src), b = pos(e.dst);
      const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2 - (e.domain === "water" ? 18 : 10);
      const d = "M " + a.x + " " + a.y + " Q " + mx + " " + my + " " + b.x + " " + b.y;
      gEdges.appendChild(E("path", {
        id: e.id, d: d,
        class: e.domain === "power" ? "edge-power" : "edge-water",
        "stroke-width": e.domain === "water" ? "4" : "2.6",
      }));
    }

    const gNodes = E("g", { id: "nodes" });
    world.appendChild(gNodes);
    NODE_IDS.concat(["bus"]).forEach(function (id) {
      gNodes.appendChild(glyph(id, pos(id)));
    });
    svg.appendChild(world);
    applyCam(true);
  }

  function paint() {
    if (!payload) return;
    const t = hour;
    const fl = flows(t);
    const phase = hourPhase(t);
    const tod = { night: ["#0d1c2c", "#1a2430"], dawn: ["#e89b6a", "#f2ddb0"], day: ["#8ec4d8", "#f2ddb0"], dusk: ["#c46a48", "#e8b07a"] }[phase];
    const st = document.getElementById("skyTop");
    const sb = document.getElementById("skyBot");
    if (st) st.setAttribute("stop-color", tod[0]);
    if (sb) sb.setAttribute("stop-color", tod[1]);
    const chip = document.getElementById("tod-chip");
    if (chip) chip.textContent = phase;

    for (const e of payload.edges) {
      const el = document.getElementById(e.id);
      if (!el) continue;
      const mag = Math.abs(fl[e.id] || 0);
      const on = mag > 1e-3;
      el.classList.toggle("edge-idle", !on);
      el.classList.toggle("flow-on", on);
      el.setAttribute("stroke-width", String(on ? Math.min(8, 2.4 + mag / 7) : (e.domain === "water" ? 4 : 2.6)));
    }
    for (const id of NODE_IDS.concat(["bus"])) {
      const g = document.getElementById("node-" + id);
      if (!g) continue;
      g.classList.toggle("on-pv", id === "pv" && fl.pv > 0.4);
      g.classList.toggle("on-diesel", id === "diesel" && fl.g > 0.05);
      g.classList.toggle("on-pump", (id === "bore_a" && fl.uA) || (id === "bore_b" && fl.uB));
      g.classList.toggle("on-dam", id === "dam");
      g.querySelectorAll(".win").forEach(function (w) {
        if (phase === "night" || phase === "dusk") w.classList.add("win-on");
        else w.classList.remove("win-on");
      });
      const sub = document.getElementById("sub-" + id);
      if (sub) sub.textContent = subtitle(id, fl, t);
    }
    const bf = document.getElementById("batt-fill");
    if (bf && payload.battery_kwh) {
      const frac = Math.max(0.08, Math.min(1, fl.S / payload.battery_kwh));
      bf.setAttribute("width", String(36 * frac));
    }
    const dw = document.getElementById("dam-water");
    if (dw) {
      const frac = Math.max(0.25, Math.min(1, fl.V / (payload.dam_spill_kl || 10000)));
      dw.setAttribute("ry", String(20 * frac));
    }

    const s = series() || {};
    const d = dispatch() || {};
    const ts = (s.timestamps && s.timestamps[t]) || "";
    document.getElementById("hour-label").textContent =
      "hour " + t + " / 47  ·  " + ts.replace("T", " ").slice(0, 19);
    const unmet = payload.headers.reduce(function (acc, p) { return acc + Number(atMap((d.unmet_kl || {}), p, t, 0)); }, 0);
    let kpis = payload.kpis || {};
    if (policy === "opt" && payload.kpis_opt) kpis = payload.kpis_opt;
    if (policy === "dumb" && payload.kpis_dumb) kpis = payload.kpis_dumb;
    const socPct = payload.battery_kwh ? Math.max(0, Math.min(100, fl.S / payload.battery_kwh * 100)) : 0;
    const damPct = payload.dam_spill_kl ? Math.max(0, Math.min(100, fl.V / payload.dam_spill_kl * 100)) : 0;
    document.getElementById("readout").innerHTML =
      "<h2>This hour</h2><dl>" +
      "<dt>local time</dt><dd>" + (ts || "—") + "</dd>" +
      "<dt>policy</dt><dd>" + (d.policy || policy) + "</dd>" +
      "<dt>air</dt><dd>" + fmt(fl.temp, 1) + " °C</dd>" +
      "<dt>PV</dt><dd>" + fmt(fl.pv, 1) + " kW</dd>" +
      "<dt>homestead</dt><dd>" + fmt(fl.load, 1) + " kW</dd>" +
      "<dt>diesel</dt><dd>" + (fl.g > 0.05 ? fmt(fl.g, 1) + " kW" : "off") + "</dd>" +
      "<dt>bores</dt><dd>" + (fl.uA ? "A on" : "A off") + " · " + (fl.uB ? "B on" : "B off") + "</dd>" +
      "</dl>" +
      "<h2>Battery</h2><div class='meter soc'><i style='width:" + socPct.toFixed(0) + "%'></i></div>" +
      "<dl><dt>SoC</dt><dd>" + fmt(fl.S, 1) + " kWh</dd><dt>charge / dis</dt><dd>" + fmt(fl.c, 1) + " / " + fmt(fl.dis, 1) + "</dd></dl>" +
      "<h2>Dam</h2><div class='meter'><i style='width:" + damPct.toFixed(0) + "%'></i></div>" +
      "<dl><dt>volume</dt><dd>" + fmt(fl.V, 0) + " kL</dd>" +
      "<dt>unmet</dt><dd class='" + (unmet > 1e-9 ? "warn" : "") + "'>" + fmt(unmet, 3) + " kL</dd></dl>" +
      "<h2>Paddock troughs</h2><dl>" +
      payload.headers.map(function (p) {
        const dem = atMap((s.demand_kl_per_h || {}), p, t, 0);
        const w = atMap((d.W_kl || {}), p, t, 0);
        return "<dt>" + p + "</dt><dd>" + fmt(w, 1) + " kL · " + fmt(dem, 2) + " kL/h</dd>";
      }).join("") +
      "</dl><h2>Run</h2><dl>" +
      "<dt>diesel</dt><dd>" + fmt(kpis.diesel_litres, 1) + " L · $" + fmt(kpis.diesel_aud, 0) + "</dd>" +
      "<dt>PV</dt><dd>" + fmt(kpis.pv_kwh, 0) + " kWh</dd>" +
      "<dt>curtail</dt><dd>" + fmt(kpis.pv_curtailed_kwh, 0) + " kWh</dd>" +
      "</dl>" + compareTable();
  }

  function compareTable() {
    const c = payload.compare || {};
    const d = c.dumb, g = c.greedy, o = c.opt;
    if (!g || !o) return "";
    function line(name, r) {
      if (!r) return "";
      return "<dt>" + name + "</dt><dd>$" + fmt(r.objective_aud, 0) + " · " + fmt(r.diesel_litres, 1) + " L</dd>";
    }
    let html = "<h2>Baselines</h2><dl>" + line("dumb", d) + line("greedy", g) + line("MILP", o) + "</dl>";
    const suite = payload.suite && payload.suite.suite;
    if (suite && suite.length) {
      html += "<h2>Suite AUD</h2><dl>";
      suite.forEach(function (row) {
        html += "<dt>" + row.name.replace("wirra-", "") + "</dt><dd>D $" + fmt(row.dumb_objective_aud, 0) +
          " · G $" + fmt(row.greedy_objective_aud, 0) +
          " · M $" + fmt(row.opt_objective_aud, 0) + "</dd>";
      });
      html += "</dl>";
    }
    return html;
  }

  function setHour(h) {
    const n = payload && payload.horizon_hours ? payload.horizon_hours : 48;
    hour = Math.max(0, Math.min(n - 1, h | 0));
    document.getElementById("hour").value = String(hour);
    paint();
  }

  function setPlaying(on) {
    playing = on;
    document.getElementById("btn-play").textContent = playing ? "Pause" : "Play";
    if (timer) { clearInterval(timer); timer = null; }
    if (playing) {
      timer = setInterval(function () {
        const n = payload && payload.horizon_hours ? payload.horizon_hours : 48;
        setHour((hour + 1) % n);
      }, 380);
    }
  }

  const K_MIN = 0.55, K_MAX = 4.2, VB_W = 1080, VB_H = 700;
  let cam = { x: 0, y: 0, k: 1 }, camT = { x: 0, y: 0, k: 1 };
  let camRaf = 0, panning = false, panLast = null, panMoved = false;

  function applyCam(snap) {
    if (snap) { cam.x = camT.x; cam.y = camT.y; cam.k = camT.k; }
    const g = document.getElementById("world");
    if (g) g.setAttribute("transform", "translate(" + cam.x.toFixed(2) + " " + cam.y.toFixed(2) + ") scale(" + cam.k.toFixed(4) + ")");
    const lab = document.getElementById("zoom-label");
    if (lab) lab.textContent = Math.round(cam.k * 100) + "%";
  }

  function tickCam() {
    camRaf = 0;
    cam.x += (camT.x - cam.x) * 0.22;
    cam.y += (camT.y - cam.y) * 0.22;
    cam.k += (camT.k - cam.k) * 0.22;
    applyCam(false);
    if (Math.abs(cam.x - camT.x) + Math.abs(cam.y - camT.y) + Math.abs(cam.k - camT.k) * 80 > 0.04) {
      camRaf = requestAnimationFrame(tickCam);
    } else {
      applyCam(true);
    }
  }

  function requestCam() {
    if (!camRaf) camRaf = requestAnimationFrame(tickCam);
  }

  function clampCam() {
    camT.k = Math.min(K_MAX, Math.max(K_MIN, camT.k));
    const maxX = VB_W * 0.35, maxY = VB_H * 0.35;
    camT.x = Math.min(maxX, Math.max(-VB_W * camT.k + VB_W * 0.65, camT.x));
    camT.y = Math.min(maxY, Math.max(-VB_H * camT.k + VB_H * 0.65, camT.y));
  }

  function svgPoint(evt) {
    const svg = document.getElementById("schematic");
    const pt = svg.createSVGPoint();
    pt.x = evt.clientX; pt.y = evt.clientY;
    const m = svg.getScreenCTM();
    if (!m) return { x: VB_W / 2, y: VB_H / 2 };
    return pt.matrixTransform(m.inverse());
  }

  function zoomAt(pt, factor) {
    const nk = Math.min(K_MAX, Math.max(K_MIN, camT.k * factor));
    const wx = (pt.x - camT.x) / camT.k;
    const wy = (pt.y - camT.y) / camT.k;
    camT.k = nk;
    camT.x = pt.x - wx * nk;
    camT.y = pt.y - wy * nk;
    clampCam();
    requestCam();
  }

  function fitView() {
    camT.x = 0; camT.y = 0; camT.k = 1;
    requestCam();
  }

  function bindCamera() {
    const svg = document.getElementById("schematic");
    svg.addEventListener("wheel", function (e) {
      e.preventDefault();
      const factor = Math.exp(-e.deltaY * 0.0016);
      zoomAt(svgPoint(e), factor);
    }, { passive: false });
    svg.addEventListener("pointerdown", function (e) {
      if (e.button !== 0) return;
      panning = true; panMoved = false;
      panLast = { x: e.clientX, y: e.clientY };
      svg.classList.add("is-panning");
      svg.setPointerCapture(e.pointerId);
    });
    svg.addEventListener("pointermove", function (e) {
      if (!panning || !panLast) return;
      const dx = e.clientX - panLast.x, dy = e.clientY - panLast.y;
      if (Math.abs(dx) + Math.abs(dy) > 3) panMoved = true;
      const ctm = svg.getScreenCTM();
      const sx = ctm ? ctm.a : 1, sy = ctm ? ctm.d : 1;
      camT.x += dx / sx;
      camT.y += dy / sy;
      clampCam();
      cam.x = camT.x; cam.y = camT.y; cam.k = camT.k;
      panLast = { x: e.clientX, y: e.clientY };
      applyCam(true);
    });
    function endPan(e) {
      if (!panning) return;
      panning = false; panLast = null;
      svg.classList.remove("is-panning");
      try { svg.releasePointerCapture(e.pointerId); } catch (err) {}
    }
    svg.addEventListener("pointerup", endPan);
    svg.addEventListener("pointercancel", endPan);
    svg.addEventListener("dblclick", function (e) {
      e.preventDefault();
      zoomAt(svgPoint(e), 1.55);
    });
    document.getElementById("btn-zoom-in").addEventListener("click", function () {
      zoomAt({ x: VB_W / 2, y: VB_H / 2 }, 1.22);
    });
    document.getElementById("btn-zoom-out").addEventListener("click", function () {
      zoomAt({ x: VB_W / 2, y: VB_H / 2 }, 1 / 1.22);
    });
    document.getElementById("btn-zoom-fit").addEventListener("click", fitView);
    window.addEventListener("keydown", function (e) {
      if (e.target && (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA")) return;
      if (e.key === "+" || e.key === "=") zoomAt({ x: VB_W / 2, y: VB_H / 2 }, 1.18);
      if (e.key === "-" || e.key === "_") zoomAt({ x: VB_W / 2, y: VB_H / 2 }, 1 / 1.18);
      if (e.key === "0") fitView();
    });
  }

  function setPolicy(next) {
    if (next === "opt" && !payload.dispatch_opt) return;
    if (next === "dumb" && !payload.dispatch_dumb) return;
    policy = next;
    document.getElementById("btn-greedy").classList.toggle("active", policy === "greedy");
    document.getElementById("btn-opt").classList.toggle("active", policy === "opt");
    const db = document.getElementById("btn-dumb");
    if (db) db.classList.toggle("active", policy === "dumb");
    paint();
  }

  async function boot() {
    const res = await fetch("/api/payload");
    payload = await res.json();
    const n = payload.horizon_hours || 48;
    const slider = document.getElementById("hour");
    slider.min = "0";
    slider.max = String(n - 1);
    if (payload.dispatch_opt) {
      const btn = document.getElementById("btn-opt");
      btn.disabled = false;
      btn.title = "Optimiser dispatch (sprint 2 artefact)";
    }
    if (payload.dispatch_dumb) {
      const btn = document.getElementById("btn-dumb");
      btn.disabled = false;
      btn.title = "Dumb diesel baseline";
    }
    const sky = (payload.series && payload.series.sky) ? payload.series.sky : "";
    const meta = document.querySelector("header p");
    if (meta && sky) meta.textContent += " · sky " + sky;
    buildSvg();
    bindCamera();
    setHour(0);
  }

  document.getElementById("hour").addEventListener("input", function (ev) {
    setHour(Number(ev.target.value));
  });
  document.getElementById("btn-play").addEventListener("click", function () {
    setPlaying(!playing);
  });
  document.getElementById("btn-greedy").addEventListener("click", function () { setPolicy("greedy"); });
  document.getElementById("btn-opt").addEventListener("click", function () { setPolicy("opt"); });
  document.getElementById("btn-dumb").addEventListener("click", function () { setPolicy("dumb"); });
  boot();
  </script>
</body>
</html>
"""


class GuiHandler(BaseHTTPRequestHandler):
    server_version = "WirraBoreGUI/1"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, code: int, content_type: str, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._send(200, "text/html; charset=utf-8", HTML_PAGE.encode("utf-8"))
            return
        if path == "/api/payload":
            body = json.dumps(self.server.payload(), indent=2).encode("utf-8")  # type: ignore[attr-defined]
            self._send(200, "application/json; charset=utf-8", body)
            return
        if path == "/favicon.ico":
            self._send(204, "image/x-icon", b"")
            return
        self._send(404, "text/plain; charset=utf-8", b"not found\n")


class GuiServer(ThreadingHTTPServer):
    allow_reuse_address = True

    def __init__(
        self,
        addr: tuple[str, int],
        station: dict[str, Any],
        output_dir: Path,
    ) -> None:
        super().__init__(addr, GuiHandler)
        self._station = station
        self._output_dir = output_dir

    def payload(self) -> dict[str, Any]:
        return build_payload(self._station, self._output_dir)


def curl_page(url: str, timeout: float = 5.0) -> tuple[int, str]:
    """GET url (stdlib). Same check as `curl -sS -D -` without extra deps."""
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return int(resp.status), body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return int(exc.code), body


def serve_in_thread(station: dict[str, Any], output_dir: Path, host: str = "127.0.0.1") -> GuiServer:
    httpd = GuiServer((host, 0), station, output_dir)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


def check_served_page(station: dict[str, Any], output_dir: Path) -> int:
    httpd = serve_in_thread(station, output_dir)
    host, port = httpd.server_address[:2]
    url = f"http://{host}:{port}/"
    try:
        code, html = curl_page(url)
        print(f"GET {url} -> {code} ({len(html)} bytes)")
        missing = [n for n in NODE_IDS if n not in html]
        if code != 200 or missing:
            print("  FAIL missing nodes:", missing)
            return 1
        for token in ("Play", "btn-play", "btn-opt", 'id="hour"', "min=\"0\"", "max=\"47\""):
            if token not in html:
                print(f"  FAIL missing control {token!r}")
                return 1
        print("  nodes:", " ".join(NODE_IDS))
        pcode, pbody = curl_page(f"http://{host}:{port}/api/payload")
        payload = json.loads(pbody) if pcode == 200 else {}
        print(
            f"GET /api/payload -> {pcode} greedy={payload.get('dispatch_greedy') is not None} "
            f"opt={payload.get('dispatch_opt') is not None} edges={len(payload.get('edges') or [])}"
        )
        print("curl check ok")
        return 0
    finally:
        httpd.shutdown()
        httpd.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Wirra-bore sprint 3 schematic GUI")
    parser.add_argument("--station", default="data/wirra-bore.json")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--check",
        action="store_true",
        help="bind ephemeral port, GET / and /api/payload, print, exit",
    )
    args = parser.parse_args(argv)

    station_path = Path(args.station)
    if not station_path.is_file():
        alt = repo_root() / args.station
        if alt.is_file():
            station_path = alt
    output_dir = Path(args.output_dir)
    if not output_dir.is_dir():
        alt = repo_root() / args.output_dir
        if alt.is_dir():
            output_dir = alt

    station = json.loads(station_path.read_text(encoding="utf-8"))
    payload = build_payload(station, output_dir)
    has_greedy = payload["dispatch_greedy"] is not None
    has_opt = payload["dispatch_opt"] is not None
    if args.check:
        return check_served_page(station, output_dir)

    httpd = GuiServer((args.host, args.port), station, output_dir)
    url = f"http://{args.host}:{args.port}/"
    print("Wirra Bore schematic GUI")
    print(f"  {url}")
    print(f"  station: {station_path}")
    print(f"  output:  {output_dir.resolve()}")
    print(f"  greedy:  {'yes' if has_greedy else 'no — run python -m src.run'}")
    print(f"  opt:     {'yes' if has_opt else 'no (toggle disabled until output/dispatch_opt.json)'}")
    print("  Ctrl-C to stop")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
