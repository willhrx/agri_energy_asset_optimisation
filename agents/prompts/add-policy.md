# Prompt: add a dispatch policy

A policy is `fn(station: dict, series: dict) -> dict` returning the same schema as
`dispatch_greedy` (keys: policy, timestamps, uA, uB, c_kw, d_kw, g_kw, pv_used_kw,
pv_curtailed_kw, dump_kw, f_kl, S_kwh, V_kl, W_kl, unmet_kl, S_kwh_end, V_kl_end, W_kl_end).

Requirements:
1. Must satisfy the power, battery, dam and header balances asserted in `tests/test_balances.py`.
   Copy those tests for the new policy.
2. Wire it into `src/run.py` and `src/compare.py` without changing existing outputs.
3. It must not run a trough negative; record slack as `unmet_kl`.
4. Run `pytest -q` and `python scripts/check_run.py output`.
