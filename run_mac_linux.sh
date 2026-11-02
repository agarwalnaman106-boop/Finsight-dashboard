#!/usr/bin/env bash
# FinSight launcher for macOS / Linux:  bash run_mac_linux.sh
cd "$(dirname "$0")"
PY=$(command -v python3.14 || command -v python3)
[ -d .venv ] || "$PY" -m venv .venv
source .venv/bin/activate
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt
python -m streamlit run app.py
