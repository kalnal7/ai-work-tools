@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Python environment missing. Follow README.md first.
  exit /b 1
)
".venv\Scripts\python.exe" -m streamlit run app.py --server.headless true --server.address 127.0.0.1 --browser.gatherUsageStats false
