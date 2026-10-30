# Prompt: add a stress scenario

Add one entry to `SUITE` in `src/scenarios.py`. Only override fields that already exist in
`data/wirra-bore.json` (`run.*`, `initial.dam_kl`, temperatures, sky). Do not add JSON fields.

Then:
1. Add a test in `tests/test_scenarios.py` asserting the scenario's intended effect.
2. Run `pytest -q` and `python -m src.run --suite`.
3. Report objective AUD for dumb / greedy / MILP and confirm unmet water is 0 or explained.
