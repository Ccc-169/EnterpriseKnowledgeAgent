#!/bin/bash
echo "=== 启动 HNGD 企业知识库智能体系统 ==="

# 初始化数据库（幂等，已存在不重复创建）
python scripts/init_db.py

# 后台启动代码执行沙箱
echo "启动代码沙箱服务（端口 8001）..."
uvicorn code_executor:app --port 8001 &
EXECUTOR_PID=$!

sleep 1

# 前台启动 Streamlit
echo "启动 Web 服务（端口 8501）..."
streamlit run app.py

# 退出时关闭沙箱服务
kill $EXECUTOR_PID 2>/dev/null
