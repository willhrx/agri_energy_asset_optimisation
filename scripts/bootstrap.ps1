$ErrorActionPreference = "Stop"
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
& .\.venv\Scripts\python.exe -m ruff check src tests scripts
& .\.venv\Scripts\python.exe -m pytest -q
& .\.venv\Scripts\python.exe -m src.run --station data/wirra-bore.json --scenario wirra-summer-clear
& .\.venv\Scripts\python.exe scripts/check_run.py output
