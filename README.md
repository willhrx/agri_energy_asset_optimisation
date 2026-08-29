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

## Grok Build prompt (paste after copying this folder)

```text
Read AGENTS.md and PROBLEM.md. Implement sprint 1 only.
Do not build a GUI or a MILP solver.
Create the src/ and tests/ layout, requirements.txt, and a runnable
python -m src.run that writes output/ artefacts.
Keep herd maths and phi tables exactly as specified.
```
