@echo off
chcp 65001 >nul 2>&1

echo === Starting HNGD Knowledge Agent System ===

if not exist "venv\" (
    echo Creating virtual environment...
    python -m venv venv
)

echo Activating venv...
call venv\Scripts\activate.bat

echo Killing stale processes on ports 28000 28001 28080...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":28000 " ^| findstr "LISTENING"') do taskkill /PID %%p /F >nul 2>&1
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":28001 " ^| findstr "LISTENING"') do taskkill /PID %%p /F >nul 2>&1
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":28080 " ^| findstr "LISTENING"') do taskkill /PID %%p /F >nul 2>&1

echo Initializing database...
python scripts/init_db.py

echo Starting code sandbox (port 28001)...
start /b venv\Scripts\python -m uvicorn code_executor:app --port 28001

echo Starting business API (port 28000)...
start /b venv\Scripts\python -m uvicorn api:app --port 28000

echo Starting static file server (port 28080)...
start /b venv\Scripts\python -m http.server 28080

echo Waiting for services to be ready...
timeout /t 5 /nobreak > nul

echo Opening browser...
start http://localhost:28080/html_files/login-page.html

echo.
echo =========================================
echo  System started. Press any key to exit.
echo =========================================
pause > nul
