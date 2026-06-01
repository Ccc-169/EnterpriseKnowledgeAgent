@echo off
chcp 65001 >nul 2>&1
echo === 启动 HNGD 企业知识库智能体系统 ===

REM 检查 venv 是否存在，不存在则创建
if not exist "venv\" (
    echo 创建虚拟环境...
    python -m venv venv
)

REM 激活虚拟环境并安装依赖
echo 安装/更新依赖...
call venv\Scripts\activate.bat

REM 清理占用端口的残留进程
echo 清理残留进程...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8000 " ^| findstr "LISTENING"') do taskkill /PID %%p /F >nul 2>&1
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8001 " ^| findstr "LISTENING"') do taskkill /PID %%p /F >nul 2>&1

REM 初始化数据库
python scripts/init_db.py

echo 启动代码沙箱服务（端口 8001）...
start /b venv\Scripts\python -m uvicorn code_executor:app --port 8001

timeout /t 1 /nobreak > nul

echo 启动业务 API 服务（端口 8000）...
start /b venv\Scripts\python -m uvicorn api:app --port 8000

timeout /t 1 /nobreak > nul

echo 启动前端静态文件服务（端口 8080）...
timeout /t 1 /nobreak > nul
start http://localhost:8080/html_files/login-page.html
venv\Scripts\python -m http.server 8080
