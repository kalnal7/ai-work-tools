#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
python3 setup_models.py
python3 -m streamlit run app.py --server.address 127.0.0.1 --server.port 8876
