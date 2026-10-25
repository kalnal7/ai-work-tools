@echo off
cd /d "%~dp0"
python setup_models.py || exit /b 1
python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8876
