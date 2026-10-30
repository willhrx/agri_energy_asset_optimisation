# Wirra Bore — sprint 1 handoff

Agri-energy asset optimisation, one off-grid NSW watering cell.

Read `AGENTS.md` then `PROBLEM.md`. Station data is `data/wirra-bore.json`.

## Target layout after sprint 1

```text
AGENTS.md
PROBLEM.md
README.md
requirements.txt
data/wirra-bore.json
src/__init__.py
src/generate_series.py
src/dispatch_greedy.py
src/kpis.py
src/plot_run.py
src/run.py
tests/test_series.py
tests/test_balances.py
output/          # gitignored
```

## Install (when you start)

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pytest
python -m src.run --station data/wirra-bore.json --scenario wirra-summer-clear
```

## Status

Sprints 1–3 are built: dumb / greedy / MILP dispatch, KPIs, stress suite, schematic GUI
(`python -m src.gui`). CI runs lint, tests (Linux + Windows, Python 3.11/3.12) and a golden run.

## One-shot local check

```bash
scripts/bootstrap.sh        # Windows: scripts\bootstrap.ps1
```

## Develop with Cline + OpenRouter

1. In Cline choose provider **OpenRouter** and a model (see `agents/MODEL_GUIDE.md`).
2. Cline reads `.clinerules`, which points to `AGENTS.md` and `PROBLEM.md`.
3. Reusable task prompts live in `agents/prompts/`. Design decisions are in `docs/adr/`.
4. Any model may be used; the test suite and `scripts/check_run.py` are the verifier.
