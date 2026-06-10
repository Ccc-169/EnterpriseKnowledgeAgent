@echo off
chcp 65001 >nul 2>&1

echo === Starting HNGD Knowledge Agent System ===

if not exist "venv\" (
    echo Creating virtual environment...
    python -m venv venv
)

echo Activating venv...
call venv\Scripts\activate.bat

echo Killing stale processes on ports 8000 8001 8002 8080...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8000 " ^| findstr "LISTENING"') do taskkill /PID %%p /F >nul 2>&1
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8001 " ^| findstr "LISTENING"') do taskkill /PID %%p /F >nul 2>&1
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8002 " ^| findstr "LISTENING"') do taskkill /PID %%p /F >nul 2>&1
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8080 " ^| findstr "LISTENING"') do taskkill /PID %%p /F >nul 2>&1

echo Initializing database...
python scripts/init_db.py

echo Starting code sandbox (port 8001)...
start /b venv\Scripts\python -m uvicorn code_executor:app --port 8001

echo Starting business API (port 8000)...
start /b venv\Scripts\python -m uvicorn api:app --port 8000

echo Starting alarm API (port 8002)...
start /b venv\Scripts\python -m uvicorn alarm_api:app --port 8002

echo Starting static file server (port 8080)...
start /b venv\Scripts\python -m http.server 8080

echo Waiting for services to be ready...
timeout /t 5 /nobreak > nul

echo Opening browser...
start http://localhost:8080/html_files/login-page.html

echo.
echo =========================================
echo  System started. Press any key to exit.
echo =========================================
pause > nul
