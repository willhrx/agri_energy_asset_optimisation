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


HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Wirra Bore — schematic</title>
  <style>
    :root {
      --bg: #10140f;
      --panel: #1a2218;
      --ink: #e8eadf;
      --muted: #9aa38c;
      --line: #2c3628;
      --power: #e0b44a;
      --water: #4eb3c8;
      --pv: #f0c14a;
      --batt: #5cb87a;
      --diesel: #d45b4c;
      --load: #c9a66b;
      --dam: #2f7f96;
      --bore: #7f9aa6;
      --paddock: #6a8a45;
      --bus: #b5bba8;
      --accent: #d8c078;
    }
    * { box-sizing: border-box; }
    html, body { margin: 0; height: 100%; background: var(--bg); color: var(--ink);
      font-family: "Segoe UI", system-ui, sans-serif; }
    body { display: grid; grid-template-rows: auto 1fr auto; min-height: 100%; }
    header, footer { padding: 12px 20px; background: var(--panel); border-color: var(--line); }
    header { display: flex; align-items: baseline; gap: 16px; flex-wrap: wrap;
      border-bottom: 1px solid var(--line); }
    header h1 { font-size: 1.15rem; margin: 0; letter-spacing: 0.04em; font-weight: 600; }
    header p { margin: 0; color: var(--muted); font-size: 0.85rem; }
    #policy { margin-left: auto; display: flex; gap: 6px; }
    #policy button {
      background: transparent; color: var(--muted); border: 1px solid var(--line);
      border-radius: 999px; padding: 6px 14px; cursor: pointer; font: inherit;
    }
    #policy button.active { background: var(--accent); color: #1a1608; border-color: var(--accent); }
    #policy button:disabled { opacity: 0.4; cursor: not-allowed; }
    main { display: grid; grid-template-columns: 1fr 280px; min-height: 0; }
    #schematic { width: 100%; height: 100%; min-height: 520px; }
    aside { border-left: 1px solid var(--line); padding: 14px 16px; overflow: auto;
      background: #141a13; font-variant-numeric: tabular-nums; }
    aside h2 { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.12em;
      color: var(--muted); margin: 0 0 8px; }
    aside dl { margin: 0 0 16px; display: grid; grid-template-columns: 1fr auto; gap: 4px 10px; }
    aside dt { color: var(--muted); font-size: 0.8rem; }
    aside dd { margin: 0; font-size: 0.85rem; text-align: right; }
    aside .warn { color: var(--diesel); }
    footer { display: flex; align-items: center; gap: 14px; border-top: 1px solid var(--line); }
    #btn-play {
      min-width: 76px; padding: 8px 12px; border-radius: 8px; border: 0;
      background: var(--accent); color: #1a1608; font: inherit; font-weight: 600; cursor: pointer;
    }
    #hour { flex: 1; accent-color: var(--accent); }
    #hour-label { min-width: 220px; color: var(--muted); font-size: 0.85rem; }
    .node-label { fill: var(--ink); font-size: 11px; font-family: inherit; }
    .node-sub { fill: var(--muted); font-size: 10px; font-family: inherit; }
    .edge-power { stroke: var(--power); fill: none; stroke-linecap: round; }
    .edge-water { stroke: var(--water); fill: none; stroke-linecap: round; }
    .edge-idle { opacity: 0.22; }
    .flow-on { stroke-dasharray: 7 8; animation: dash 0.9s linear infinite; }
    @keyframes dash { to { stroke-dashoffset: -15; } }
    .banner { fill: #c45c4c; font-size: 14px; }
  </style>
</head>
<body>
  <header>
    <h1>Wirra Bore schematic</h1>
    <p>layout.nodes · homestead pv battery diesel dam bore_a bore_b north creek dam_paddock back</p>
    <div id="policy">
      <button type="button" id="btn-dumb" data-policy="dumb" disabled title="No output/dispatch_dumb.json">Dumb</button>
      <button type="button" id="btn-greedy" class="active" data-policy="greedy">Greedy</button>
      <button type="button" id="btn-opt" data-policy="opt" disabled title="No output/dispatch_opt.json">Opt</button>
    </div>
  </header>
  <main>
    <svg id="schematic" viewBox="0 0 1040 640" role="img" aria-label="Site schematic">
      <title>Wirra Bore site graph</title>
    </svg>
    <aside id="readout"></aside>
  </main>
  <footer>
    <button type="button" id="btn-play">Play</button>
    <input type="range" id="hour" min="0" max="47" value="0" step="1"/>
    <span id="hour-label">hour 0 / 47</span>
  </footer>
  <script>
  const NODE_IDS = ["homestead","pv","battery","diesel","dam","bore_a","bore_b","north","creek","dam_paddock","back"];
  const SCALE = 1.85, PAD_X = 70, PAD_Y = 40;
  let payload = null, policy = "greedy", hour = 0, playing = false, timer = null;

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

  function fillFor(id, fl) {
    const kind = nodeKind(id);
    if (kind === "pv") return fl.pv > 0.2 ? "#f0c14a" : "#5a5330";
    if (kind === "battery") {
      const frac = payload.battery_kwh ? fl.S / payload.battery_kwh : 0;
      return frac > 0.4 ? "#5cb87a" : "#3d6a4a";
    }
    if (kind === "diesel") return fl.g > 0.05 ? "#d45b4c" : "#5a3532";
    if (kind === "load") return fl.load > 8 ? "#c9a66b" : "#6d5b3c";
    if (kind === "dam") {
      const spill = payload.dam_spill_kl || 10000;
      return fl.V / spill > 0.4 ? "#2f7f96" : "#3a4e55";
    }
    if (kind === "bore") {
      const on = id === "bore_a" ? fl.uA : fl.uB;
      return on ? "#7fbfc8" : "#3d4a4e";
    }
    if (kind === "paddock") return id === "back" ? "#3a4630" : "#6a8a45";
    if (kind === "bus") return "#b5bba8";
    return "#445";
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
    if (id === "bus") return "AC bus";
    if (payload.headers.indexOf(id) >= 0) {
      const w = atMap((d.W_kl || {}), id, t, 0);
      const dem = atMap(((series() || {}).demand_kl_per_h || {}), id, t, 0);
      return fmt(w, 1) + " kL · " + fmt(dem, 2) + " kL/h";
    }
    return "";
  }

  function buildSvg() {
    const svg = document.getElementById("schematic");
    svg.innerHTML = "";
    const ns = "http://www.w3.org/2000/svg";
    const bg = document.createElementNS(ns, "rect");
    bg.setAttribute("width", "1040"); bg.setAttribute("height", "640");
    bg.setAttribute("fill", "#10140f");
    svg.appendChild(bg);

    if (!payload) return;
    if (!payload.series || !payload.dispatch_greedy) {
      const t = document.createElementNS(ns, "text");
      t.setAttribute("x", "80"); t.setAttribute("y", "80"); t.setAttribute("class", "banner");
      t.textContent = "Run python -m src.run first (missing output/series.json or dispatch_greedy.json)";
      svg.appendChild(t);
    }

    const gEdges = document.createElementNS(ns, "g");
    gEdges.setAttribute("id", "edges");
    svg.appendChild(gEdges);
    for (const e of payload.edges) {
      const a = pos(e.src), b = pos(e.dst);
      const path = document.createElementNS(ns, "path");
      const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
      const d = "M " + a.x + " " + a.y + " Q " + mx + " " + (my - 8) + " " + b.x + " " + b.y;
      path.setAttribute("id", e.id);
      path.setAttribute("d", d);
      path.setAttribute("class", e.domain === "power" ? "edge-power" : "edge-water");
      path.setAttribute("stroke-width", "2.5");
      gEdges.appendChild(path);
    }

    const gNodes = document.createElementNS(ns, "g");
    gNodes.setAttribute("id", "nodes");
    svg.appendChild(gNodes);
    const ids = NODE_IDS.concat(["bus"]);
    for (const id of ids) {
      const p = pos(id);
      const g = document.createElementNS(ns, "g");
      g.setAttribute("id", "node-" + id);
      const kind = nodeKind(id);
      const w = kind === "bus" ? 36 : (kind === "dam" ? 72 : 64);
      const h = kind === "bus" ? 18 : 34;
      const shape = document.createElementNS(ns, "rect");
      shape.setAttribute("class", "glyph");
      shape.setAttribute("x", p.x - w / 2);
      shape.setAttribute("y", p.y - h / 2);
      shape.setAttribute("width", w);
      shape.setAttribute("height", h);
      shape.setAttribute("rx", kind === "bus" ? 3 : 7);
      shape.setAttribute("stroke", "#0b0e0a");
      shape.setAttribute("stroke-width", "1.2");
      g.appendChild(shape);
      const label = document.createElementNS(ns, "text");
      label.setAttribute("class", "node-label");
      label.setAttribute("x", p.x);
      label.setAttribute("y", p.y - h / 2 - 6);
      label.setAttribute("text-anchor", "middle");
      label.textContent = id;
      g.appendChild(label);
      const sub = document.createElementNS(ns, "text");
      sub.setAttribute("class", "node-sub");
      sub.setAttribute("id", "sub-" + id);
      sub.setAttribute("x", p.x);
      sub.setAttribute("y", p.y + 4);
      sub.setAttribute("text-anchor", "middle");
      g.appendChild(sub);
      gNodes.appendChild(g);
    }
  }

  function paint() {
    if (!payload) return;
    const t = hour;
    const fl = flows(t);
    for (const e of payload.edges) {
      const el = document.getElementById(e.id);
      if (!el) continue;
      const mag = Math.abs(fl[e.id] || 0);
      const on = mag > 1e-3;
      el.classList.toggle("edge-idle", !on);
      el.classList.toggle("flow-on", on);
      el.setAttribute("stroke-width", String(on ? Math.min(7, 2 + mag / 6) : 2));
    }
    for (const id of NODE_IDS.concat(["bus"])) {
      const g = document.getElementById("node-" + id);
      if (!g) continue;
      const glyph = g.querySelector(".glyph");
      if (glyph) glyph.setAttribute("fill", fillFor(id, fl));
      const sub = document.getElementById("sub-" + id);
      if (sub) sub.textContent = subtitle(id, fl, t);
    }
    const s = series() || {};
    const d = dispatch() || {};
    const ts = (s.timestamps && s.timestamps[t]) || "";
    document.getElementById("hour-label").textContent =
      "hour " + t + " / 47  ·  " + ts.replace("T", " ").slice(0, 19);
    const unmet = payload.headers.reduce((acc, p) => acc + Number(atMap((d.unmet_kl || {}), p, t, 0)), 0);
    let kpis = payload.kpis || {};
    if (policy === "opt" && payload.kpis_opt) kpis = payload.kpis_opt;
    if (policy === "dumb" && payload.kpis_dumb) kpis = payload.kpis_dumb;
    document.getElementById("readout").innerHTML =
      "<h2>Hour " + t + "</h2><dl>" +
      "<dt>timestamp</dt><dd>" + (ts || "—") + "</dd>" +
      "<dt>policy</dt><dd>" + (d.policy || policy) + "</dd>" +
      "<dt>PV</dt><dd>" + fmt(fl.pv, 2) + " kW</dd>" +
      "<dt>homestead</dt><dd>" + fmt(fl.load, 2) + " kW</dd>" +
      "<dt>diesel g</dt><dd>" + fmt(fl.g, 2) + " kW</dd>" +
      "<dt>charge / discharge</dt><dd>" + fmt(fl.c, 2) + " / " + fmt(fl.dis, 2) + " kW</dd>" +
      "<dt>SoC</dt><dd>" + fmt(fl.S, 2) + " kWh</dd>" +
      "<dt>dam V</dt><dd>" + fmt(fl.V, 1) + " kL</dd>" +
      "<dt>bore A / B</dt><dd>" + (fl.uA ? "on" : "off") + " / " + (fl.uB ? "on" : "off") + "</dd>" +
      "<dt>air temp</dt><dd>" + fmt(fl.temp, 1) + " °C</dd>" +
      "<dt>unmet this hour</dt><dd class='" + (unmet > 1e-9 ? "warn" : "") + "'>" + fmt(unmet, 3) + " kL</dd>" +
      "</dl><h2>Paddock demand</h2><dl>" +
      payload.headers.map(function (p) {
        const dem = atMap((s.demand_kl_per_h || {}), p, t, 0);
        const w = atMap((d.W_kl || {}), p, t, 0);
        return "<dt>" + p + "</dt><dd>" + fmt(w, 2) + " kL · D " + fmt(dem, 3) + " kL/h</dd>";
      }).join("") +
      "</dl><h2>Run KPIs</h2><dl>" +
      "<dt>diesel</dt><dd>" + fmt(kpis.diesel_litres, 2) + " L · $" + fmt(kpis.diesel_aud, 2) + "</dd>" +
      "<dt>PV energy</dt><dd>" + fmt(kpis.pv_kwh, 1) + " kWh</dd>" +
      "<dt>curtailment</dt><dd>" + fmt(kpis.pv_curtailed_kwh, 1) + " kWh</dd>" +
      "<dt>min dam / SoC</dt><dd>" + fmt(kpis.min_dam_kl, 0) + " kL / " + fmt(kpis.min_soc_kwh, 1) + " kWh</dd>" +
      "<dt>unmet total</dt><dd>" + fmt(kpis.unmet_kl_total, 3) + " kL</dd>" +
      "<dt>PV used</dt><dd>" + fmt(kpis.pv_utilisation, 3) + " · pumped " + fmt(kpis.water_pumped_kl, 1) + " kL</dd>" +
      "</dl>" + compareTable();
  }

  function compareTable() {
    const c = payload.compare || {};
    const d = c.dumb, g = c.greedy, o = c.opt;
    if (!g || !o) return "";
    function line(name, r) {
      if (!r) return "";
      return "<dt>" + name + "</dt><dd>$" + fmt(r.objective_aud, 2) + " · " + fmt(r.diesel_litres, 1) + " L</dd>";
    }
    let html = "<h2>Baselines</h2><dl>" + line("dumb", d) + line("greedy", g) + line("MILP", o) + "</dl>";
    const suite = payload.suite && payload.suite.suite;
    if (suite && suite.length) {
      html += "<h2>Suite AUD</h2><dl>";
      suite.forEach(function (row) {
        html += "<dt>" + row.name + "</dt><dd>D $" + fmt(row.dumb_objective_aud, 0) +
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
