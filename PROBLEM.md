# PROBLEM.md — wirra-bore v0

Operational dispatch for one off-grid pastoral watering cell.

## 1. Archetype

Station id: `wirra-bore`. Western NSW. Homestead + yards off-grid. Two hybrid bores fill one turkey-nest dam. Dam feeds four paddock header tanks / trough lines.

| Asset | Value |
|---|---|
| PV | 40 kWp, north, tilt 32° |
| Battery | 60 kWh usable envelope, 15 kW |
| Diesel | 30 kVA class; model 8–24 kW band |
| Bore A | 11 kW, 4 L/s → dam |
| Bore B | 15 kW, 6 L/s → dam |
| Dam | 8 ML usable, 1 ML reserve, 10 ML spill |
| Headers | 20 kL each paddock |
| Outlet cap | 40 kL/h shared |

No grid. No export revenue.

## 2. Site graph

Power: `pv`, `battery`, `diesel`, `bus_homestead`, `bore_a`, `bore_b`  
Water: `bore_a`, `bore_b`, `dam`, headers `north`, `creek`, `dam_paddock`, `back`

Edges: PV/diesel/battery ↔ bus; bus → homestead and both bores; both bores → dam; dam → four headers.

`layout.x/y` is GUI-only until sprint 3.

## 3. Time

- Horizon 48 h, step 1 h.
- Default start: `2026-01-16T00:00:00` Australia/Sydney (Fri–Sat).
- Scenario name: `wirra-summer-clear`.

## 4. Decisions (each hour t)

| Symbol | Meaning |
|---|---|
| \(u^A_t, u^B_t\) | Bore A/B on ∈ {0,1} |
| \(c_t, d_t\) | Battery charge / discharge kW |
| \(g_t\) | Diesel electrical kW; 0 or [8, 24] |

No simultaneous charge and discharge.

## 5. State

- \(S_t\) battery kWh
- \(V_t\) dam kL
- \(W_{p,t}\) header kL for paddock p

Exogenous: PV available, homestead load, air temp, demand \(D_{p,t}\).

## 6. Dynamics

Power:

```
pv_t + d_t + g_t = L_t + c_t + 11*uA_t + 15*uB_t
```

Battery:

```
S_{t+1} = S_t + 0.95*c_t*dt - d_t*dt/0.95
0.15*60 <= S <= 0.95*60
```

Dam (L/s × 3.6 = kL/h):

```
V_{t+1} = V_t + 3.6*(4*uA + 6*uB) - sum_p f_p,t
1000 <= V <= 10000
```

Headers:

```
W_p,{t+1} = W_p,t + f_p,t - D_p,t
W_p >= 0
sum f_p <= 40 kL/h
f_p >= 0
```

If demand cannot be met, record unmet slack \(s_{p,t}\) (kL) and keep W at 0.

## 7. Rules

- No pumping hours local 11,12,13,14,15 unless dam < 1500 kL.
- Diesel fuel L/h = 0 if g=0 else `1.2 + 0.28*g`.
- Diesel AUD/L = 2.00.
- Unmet penalty (optimiser, sprint 2) = 50000 AUD/kL.

## 8. Objective (sprint 2; greedy approximates)

Minimise sum_t [ diesel_cost_t + 50000 * sum_p s_p,t ].

Sprint 1 greedy policy (implement this, not a solver):

1. Meet homestead from PV, then battery above SoC min, then diesel.
2. Release from dam to headers to meet D and keep headers ≥ 30% if dam allows.
3. If dam < 2500 kL or any header would fail next 3 hours: run the cheapest bore(s) that fit remaining PV+battery+diesel, respecting no-pump hours unless dam < 1500 kL.
4. Charge battery with leftover PV. Never charge from diesel in sprint 1.
5. Do not start a bore if it would require diesel **and** dam > 4000 kL **and** all headers > 8 kL.

Document the policy in a docstring. It does not need to be optimal.

## 9. Cattle

Mobs are exogenous. Solver does not move stock.

| Mob | Head | Base L/hd/day |
|---|---|---|
| weaners | 180 | 50 |
| cows_calves | 220 | 70 |
| bulls | 8 | 60 |

Default placement all 48 h:

- north → cows_calves
- creek → weaners
- dam_paddock → bulls
- back → empty

Heat factor H(T): 1.0 at T≤25; linear to 1.8 at 38; cap 1.8.

Hourly fraction φ (sums to 1.000):

```
h:  0     1     2     3     4     5     6     7     8     9    10    11
φ: 0.012 0.010 0.008 0.008 0.012 0.020 0.042 0.055 0.058 0.054 0.048 0.044

h: 12    13    14    15    16    17    18    19    20    21    22    23
φ: 0.040 0.036 0.055 0.080 0.100 0.095 0.070 0.050 0.040 0.030 0.020 0.013
```

```
D_p,t [kL/h] = sum_{m on p} N_m * ell_m * H(T_t) * φ[h(t)] / 1000
```

## 10. Series generator

### PV — pvlib

```
lat, lon = -32.00, 147.20
tz = Australia/Sydney
alt = 250 m
kwp = 40, tilt = 32, azimuth = 0 (north)
inverter_ac_kw = 36
system_loss_frac = 0.14
sky = clear | overcast | mixed
```

Use Location + Ineichen clearsky + Perez POA + PVWatts-style DC/AC as in the chat spec.  
`overcast`: GHI×0.35, DNI×0.05, DHI×0.70.  
`mixed`: day 0 clear; day 1 hours 12–17 GHI×0.45.

Cell temp v0: `T_cell = T_air + 25 * POA/1000`.

Expect **180–320 kWh** AC on a clear January day for 40 kWp.

### Temperature

```
T_t = Tmin + (Tmax-Tmin) * (cos(2π(h-15)/24) + 1) / 2
```

Default Tmin=22, Tmax=37. Peak at 15:00.

### Homestead weekday kW (bores not included)

```
0:3.0  1:2.5  2:2.5  3:2.5  4:3.0  5:4.0
6:10   7:20   8:16   9:12  10:7   11:7
12:6  13:6   14:7   15:8   16:18  17:16
18:12 19:10  20:8   21:6   22:5   23:4
```

Sum 198 kWh. Clip [0, 20].  
Weekend: hour 7→12, hour 8→10.  
16 Jan 2026 is Friday (use weekday). 17 Jan Saturday (weekend table).  
`yards_busy` extra already baked into 7–8 and 16–17 on Friday.  
Noise: Uniform(0.90, 1.10) with seed from scenario name.

## 11. Tests / sanity

- sum(φ) == 1 within 1e-9
- back demand all zeros
- cows_calves daily kL ≈ 220 * 70 * mean(H) / 1000 (±15%)
- hour 16 demand ≥ demand of every other hour for each stocked paddock
- clear-day PV energy in [180, 320] kWh
- homestead daily energy in [170, 230] kWh and max ≤ 20 kW
- dam never below 1000 kL in the recorded state unless unmet > 0
- initial SoC 36 kWh, dam 5500 kL, headers 15 kL

## 12. Outputs

`output/series.json` — hourly arrays aligned to horizon.  
`output/dispatch_greedy.json` — uA, uB, c, d, g, f_p, S, V, W_p, unmet_p per hour.  
`output/kpis.json` — diesel_litres, diesel_aud, pv_kwh, pv_curtailed_kwh, min_dam_kl, min_soc_kwh, unmet_kl_total, hours_diesel_on.

## 13. Baselines (sprint 2 compares; sprint 1 implements greedy only)

1. Dumb diesel (optional stub).  
2. Greedy (this sprint).  
3. Optimiser (sprint 2).
