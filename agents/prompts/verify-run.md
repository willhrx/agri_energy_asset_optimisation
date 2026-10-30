# Prompt: verify a run

Read `AGENTS.md` and `PROBLEM.md`. Then run, in order:

1. `ruff check src tests scripts`
2. `pytest -q`
3. `python -m src.run --station data/wirra-bore.json --scenario wirra-summer-clear`
4. `python scripts/check_run.py output`

Report each result. For any failure, name the file and hour/KPI involved and propose a fix.
Do not edit tests to make them pass.
