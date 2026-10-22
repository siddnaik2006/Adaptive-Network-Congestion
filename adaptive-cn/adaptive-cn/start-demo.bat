@echo off
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (set "PYTHON=python") else (set "PYTHON=py -3")
if not exist .venv\Scripts\python.exe %PYTHON% -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 exit /b 1
if not exist data\model.json .venv\Scripts\python.exe scripts\train.py
start "" http://127.0.0.1:8080
.venv\Scripts\python.exe -m cn.server
pause
