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

REM 初始化数据库
python scripts/init_db.py

echo 启动代码沙箱服务（端口 8001）...
start /b venv\Scripts\python -m uvicorn code_executor:app --port 8001

timeout /t 1 /nobreak > nul

echo 启动 Web 服务（端口 8501）...
venv\Scripts\streamlit run app.py
