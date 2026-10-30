# AGENTS.md — wirra-bore sprint 1

> Status: sprints 1–3 are built (greedy, dumb baseline, MILP, GUI). The sprint-1 scope below is
> kept as the original contract. Verify any change with: `ruff check src tests scripts`,
> `pytest -q`, `python -m src.run --station data/wirra-bore.json --scenario wirra-summer-clear`,
> `python scripts/check_run.py output`. See `.clinerules` and `agents/MODEL_GUIDE.md`.

You are implementing a **single-station agri-energy dispatch prototype**, not a platform.

## Goal

Off-grid western NSW watering cell. Cattle water is a hard constraint. Diesel cost is the objective. Geography is a **site graph** in JSON, not GIS.

## Build now (sprint 1)

1. Repo layout below.
2. Canonical station file `data/wirra-bore.json` (already written — do not invent extra fields).
3. `src/generate_series.py` — fill 48 hourly series from the spec in `PROBLEM.md`.
4. `src/dispatch_greedy.py` — greedy baseline.
5. `src/plot_run.py` — one figure: PV, load, SoC, dam, diesel, bore on/off, paddock demand.
6. `src/kpis.py` — print litres diesel, $, min dam, min SoC, unmet kL, PV kWh, PV curtailment.
7. Tests in `tests/` for the checklist in `PROBLEM.md` §11.

Entry point:

```bash
python -m src.run --station data/wirra-bore.json --scenario wirra-summer-clear
```

Writes `output/series.json`, `output/dispatch_greedy.json`, `output/kpis.json`, `output/run.png`.

## Do not build in sprint 1

- GUI / map / cows walking
- PuLP / Pyomo / MILP (sprint 2)
- Grid, FCAS, NEM bids
- Multi-station, NL adapter, plugins
- Live meters, GIS, pvlib SAM module database
- Changing herd maths or \(\phi\) without editing `PROBLEM.md`

## Conventions

- Python 3.11+, `pvlib`, `pandas`, `numpy`, `matplotlib`. Pin in `requirements.txt`.
- Timezone `Australia/Sydney`. Timestamps = **start** of each hour.
- Units: kW, kWh, kL, L/s, AUD. Dam reserve is sacred.
- If a field is not in the JSON, it does not exist.
- Prefer small pure functions. No hidden globals.
- Greedy may use diesel; it must not run a trough negative. Use slack only if documented in KPIs as unmet.

## Done when

- `pytest` passes.
- Clear-day PV energy 180–320 kWh for 40 kWp.
- \(\sum \phi = 1\).
- Empty paddock (`back`) demand is 0.
- Greedy run on default scenario finishes and writes artefacts.
- Unmet water is 0 on `wirra-summer-clear` **or** KPI file explains why and which hour.

## Next sprints (do not start)

- Sprint 2: optimiser vs greedy on the same series.
- Sprint 3: schematic GUI reading `layout` + dispatch.
