#!/bin/bash
# start_ubuntu.sh — Ubuntu 一键启动脚本（等同于 start.bat）
# 服务绑定 0.0.0.0，本机(127.0.0.1)与局域网(192.168.1.155)均可访问
# Ctrl+C 可停止所有服务
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
SERVER_IP="192.168.1.155"
PORTS=(28000 28001 28080)
# ── 捕获 Ctrl+C，退出时杀掉所有子进程 ───────────────────
cleanup() {
    echo ""
    echo "=== 正在停止所有服务... ==="
    kill $(jobs -p) 2>/dev/null
    wait 2>/dev/null
    echo "=== 所有服务已停止 ==="
    exit 0
}
trap cleanup INT TERM
echo "=== Starting HNGD Knowledge Agent System (Ubuntu) ==="
echo ""
# ── 1. 虚拟环境 ──────────────────────────────────────────
if [ ! -d "venv" ]; then
    echo "[1/4] 创建虚拟环境..."
    python3 -m venv venv
else
    echo "[1/4] 虚拟环境已存在，跳过创建。"
fi
source venv/bin/activate
echo "      已激活 venv: $(which python)"
# ── 2. 释放端口 ──────────────────────────────────────────
echo ""
echo "[2/4] 释放端口 ${PORTS[*]}..."
for port in "${PORTS[@]}"; do
    pids=$(lsof -ti tcp:"$port" 2>/dev/null || true)
    if [ -n "$pids" ]; then
        echo "      端口 $port 被占用 (PID $pids)，正在终止..."
        kill -9 $pids 2>/dev/null || true
        sleep 0.5
    fi
done
# ── 3. 初始化数据库 ───────────────────────────────────────
echo ""
echo "[3/4] 初始化数据库..."
python scripts/init_db.py
# ── 4. 启动三个服务（前台输出，实时打印到终端） ──────────
echo ""
echo "[4/4] 启动服务..."
mkdir -p logs
# 每个服务加前缀标签，方便区分来源
python -m uvicorn code_executor:app \
    --host 0.0.0.0 --port 28001 \
    2>&1 | sed 's/^/[沙箱  ] /' | tee logs/code_executor.log &
echo "      代码沙箱       → http://127.0.0.1:28001  (PID $!)"
python -m uvicorn api:app \
    --host 0.0.0.0 --port 28000 \
    2>&1 | sed 's/^/[API   ] /' | tee logs/api.log &
echo "      业务 API       → http://127.0.0.1:28000  (PID $!)"
python -m http.server 28080 \
    --directory . \
    --bind 0.0.0.0 \
    2>&1 | sed 's/^/[静态  ] /' | tee logs/http_server.log &
echo "      静态文件服务器 → http://127.0.0.1:28080  (PID $!)"
# ── 5. 等待并打印访问地址 ────────────────────────────────
echo ""
echo "[5/5] 等待服务就绪（5 秒）..."
sleep 5
echo ""
echo "============================================="
echo "  系统已启动"
echo ""
echo "  本机访问："
echo "    http://127.0.0.1:28080/html_files/login-page.html"
echo ""
echo "  局域网访问（服务器 IP: $SERVER_IP）："
echo "    http://$SERVER_IP:28080/html_files/login-page.html"
echo ""
echo "  日志目录: $SCRIPT_DIR/logs/"
echo "    api.log / code_executor.log / http_server.log"
echo ""
echo "  按 Ctrl+C 停止所有服务"
echo "============================================="
echo ""
# 阻塞主进程，等待 Ctrl+C
wait
