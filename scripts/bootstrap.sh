#!/usr/bin/env bash
set -euo pipefail
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
ruff check src tests scripts
pytest -q
python -m src.run --station data/wirra-bore.json --scenario wirra-summer-clear
python scripts/check_run.py output
