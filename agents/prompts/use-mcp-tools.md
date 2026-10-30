# Prompt: use the engine MCP tools

When the wirra-bore MCP server is connected, prefer its tools over reading raw JSON:

1. `validate_station` before proposing changes to any station file.
2. `run_scenario` (policy `greedy`) for quick what-ifs; use `dam_kl`, `sky`,
   `temp_max_c` arguments instead of editing JSON.
3. `compare_policies` before claiming a change improves dispatch — check
   `opt_beats_or_ties_greedy` and `unmet_kl_total` stays 0.
4. `list_scenarios` to pick a stress case that matches the question.

Never claim a dispatch improvement without a `compare_policies` result in the reply.
