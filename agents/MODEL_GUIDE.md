# Model guide — Cline + OpenRouter

Nothing in this repo depends on a specific model. `AGENTS.md` + `PROBLEM.md` are the spec and the
test suite is the verifier, so any capable model can work here.

## Setup in Cline

1. Settings → API Provider → **OpenRouter**.
2. Paste your key (see `.env.example`; Cline stores it itself, the repo never reads it).
3. Pick a model by its OpenRouter id (`<vendor>/<model>`). Browse https://openrouter.ai/models.

## Routing by task

Model ids change often, so this table is by capability tier. Choose current models yourself.

| Task | Tier | Why |
|---|---|---|
| MILP changes, physics, power/water balance, schema design | Strongest reasoning model | A wrong constraint is silent and costly |
| Audits, ADRs, architecture planning | Strongest reasoning model | Long-context judgement |
| New tests, plots, CLI flags, docs, refactors with tests | Mid-tier / fast model | Verifier catches mistakes cheaply |
| Mechanical edits (renames, formatting) | Cheapest model | Low risk |

## Rules for any model

- Run the commands in `.clinerules` before declaring done.
- Tests are the contract. Do not weaken or delete a test to make it pass.
- Keep a change small; one concern per commit.
- Record cost-sensitive findings (which tier failed which task) in this file.
