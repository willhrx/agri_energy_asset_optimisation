# ADR 0001 — Agent harness is model-agnostic

Status: accepted

## Context
The repo was built with one vendor's agent (a `.grok` workflow referencing a WSL path). We want
to develop with Cline via OpenRouter, and not be locked to any model or tool.

## Decision
- `AGENTS.md` + `PROBLEM.md` are the canonical spec.
- Vendor files such as `.clinerules` are thin pointers to them and to the verification commands.
- No vendor-specific workflow scripts in the repo. `.grok/` is removed (kept in git history).
- The pytest suite plus `scripts/check_run.py` is the verifier for every agent change; CI runs
  the same commands.
- Model choice is documented by capability tier in `agents/MODEL_GUIDE.md`, not by model name.

## Consequences
Any model can contribute; correctness comes from tests, not from trusting the model.
Switching tools means adding one pointer file.
