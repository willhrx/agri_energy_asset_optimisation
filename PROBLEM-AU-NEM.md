# PROBLEM-AU-NEM.md — grid-connected watering cell v1

Second archetype for the same product: an NEM-connected pumping cell. The **water
side is identical** to `PROBLEM.md` (herd maths, phi table, dam reserve are the
same contract and are NOT restated here — see §9/§6 there). Only the power side
and the objective change. Where this file is silent, `PROBLEM.md` governs.

## 1. Archetype

Station id: `trangie-grid`. Trangie NSW (-32.03, 147.98, 250 m). Homestead + yards
**grid-connected**; two hybrid bores fill one turkey-nest dam; four paddock
headers. **No genset** — the grid is the dispatchable source of last resort.

| Asset | Value |
|---|---|
| PV | 40 kWp, north, tilt 32 |
| Battery | 60 kWh usable envelope, 15 kW, eta 0.95 both ways |
| Grid meter | import ≤ 30 kW, export ≤ 20 kW |
| Bore A | 11 kW, 4 L/s → dam |
| Bore B | 15 kW, 6 L/s → dam |
| Dam / headers / outlet | identical to `PROBLEM.md` §1 |

## 2. Site graph

Power: `pv`, `battery`, `grid`, `bus_homestead`, `bore_a`, `bore_b`.
Water: identical to `PROBLEM.md` §2. Edges: pv/battery/grid ↔ bus; bus →
homestead and both bores; bores → dam; dam → four headers.

## 3. Time

Horizon 48 h, step 1 h. Default start `2026-02-13T00:00:00` Australia/Sydney
(a Friday). Scenario name `trangie-summer-clear`.

## 4. Decisions (each hour t)

| Symbol | Meaning |
|---|---|
| uA_t, uB_t | Bore A/B on ∈ {0,1} |
| c_t, d_t | Battery charge / discharge kW |
| i_t | Grid import kW ∈ [0, 30] |
| e_t | Grid export kW ∈ [0, 20] |

No simultaneous charge and discharge. i_t and e_t are both modelled; because
every tariff exceeds the feed-in rate, an optimal solution never imports and
exports in the same hour (solvers may exploit this; policies must not rely on it).

## 5. State

Identical to `PROBLEM.md` §5 (S_t battery kWh, V_t dam kL, W_p,t header kL).

## 6. Dynamics

Power:

```
pv_used_t + d_t + i_t = L_t + c_t + 11*uA_t + 15*uB_t + e_t
0 <= pv_used_t <= pv_t          (surplus beyond export cap is curtailed)
```

Battery, dam, headers: **identical to `PROBLEM.md` §6**.

## 7. Rules

- No pumping hours local 11,12,13,14,15 unless dam < 1500 kL (as `PROBLEM.md` §7).
- Tariffs (AUD/kWh, local hour h): off-peak 0.18 for h in [22,07);
  shoulder 0.38 for h in [07,17); peak 0.62 for h in [17,22).
- Feed-in: 0.08 AUD/kWh flat, any hour.
- Unmet water penalty: 50,000 AUD/kL (as `PROBLEM.md` §7).

## 8. Objective

Minimise sum_t [ tariff(h_t)*i_t - 0.08*e_t ]*dt + 50000 * sum_p s_p,t.

The energy term replaces diesel cost. Baselines (later increments): dumb grid
(import everything, no battery cycling), greedy ToU heuristic, MILP.

## 9. Station file

`data/trangie-grid.json`. New fields relative to `wirra-bore.json` (documented
here and only here):

```
power.grid_import_kw_max : 30        (kW, > 0)
power.grid_export_kw_max : 20        (kW, > 0)
market.type              : "au_nem_tou"
market.import_tariff_c_per_kwh : {"offpeak":18, "shoulder":38, "peak":62}
market.tou_hours         : {"offpeak":[22,7], "shoulder":[7,17], "peak":[17,22]}
market.feed_in_c_per_kwh : 8
objective                : {"unmet_water_aud_per_kl": 50000}   (no diesel price)
```

Grid stations MUST NOT define diesel power fields; off-grid stations MUST NOT
define grid fields. Tariff windows must tile the 24 h day exactly once each.

## 10. Sanity / tests

- All `PROBLEM.md` §11 water/herd invariants hold unchanged (phi sums to 1,
  back paddock zero demand, hour-16 peak, initial SoC 36 / dam 5500 / headers 15).
- Power balance holds every hour incl. i_t, e_t.
- 0 <= i_t <= 30; 0 <= e_t <= 20; no hour with both > 1e-6 in a recorded solution.
- Clear-day PV energy in [180, 320] kWh (same array as wirra).

## 11. Outputs

Same artefact names as `PROBLEM.md` §12 with `energy_aud` replacing
`diesel_aud` in KPIs for grid stations (diesel_litres/hours_diesel_on are
absent/zero for grid stations).
