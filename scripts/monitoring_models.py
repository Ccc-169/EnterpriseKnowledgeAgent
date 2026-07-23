"""
实时监控 Ollama 模型显存占用 + Xinference Rerank 模型状态
用法: python scripts/test_models.py [--base-url http://192.168.1.155:11434] [--interval 5]
      python scripts/test_models.py --xinference-url http://192.168.1.155:9997/v1 --rerank-model bge-reranker-v2-m3
"""

import argparse
import sys
import time
from datetime import datetime

import requests


def fmt_bytes(b: int) -> str:
    """字节数 → 人类可读格式"""
    if b < 1024:
        return f"{b} B"
    if b < 1024 ** 2:
        return f"{b / 1024:.1f} MB"
    if b < 1024 ** 3:
        return f"{b / 1024 ** 2:.1f} MB"
    return f"{b / 1024 ** 3:.2f} GB"


def get_running_models(base_url: str) -> list[dict]:
    """通过 /api/ps 获取当前已加载的模型及其显存占用"""
    try:
        resp = requests.get(f"{base_url}/api/ps", timeout=5)
        resp.raise_for_status()
        return resp.json().get("models", [])
    except requests.RequestException as e:
        return None


def get_all_models(base_url: str) -> list[dict]:
    """通过 /v1/models 获取所有可用模型"""
    try:
        resp = requests.get(f"{base_url}/v1/models", timeout=5)
        resp.raise_for_status()
        return resp.json().get("data", [])
    except requests.RequestException:
        return []


def get_xinference_models(xinference_url: str) -> list[dict]:
    """通过 Xinference /v1/models 获取已启动的模型列表"""
    base = xinference_url.rstrip("/v1").rstrip("/")
    try:
        resp = requests.get(f"{base}/v1/models", timeout=5)
        resp.raise_for_status()
        return resp.json().get("data", [])
    except requests.RequestException:
        return []


def test_rerank(xinference_url: str, model_id: str) -> dict:
    """测试 Xinference rerank 模型是否可用，返回延迟(ms)和状态"""
    base = xinference_url.rstrip("/v1").rstrip("/")
    payload = {
        "model": model_id,
        "query": "公司背景",
        "documents": ["本公司是一家专注于智能制造的企业", "财务报销制度规定"],
        "top_n": 2,
    }
    try:
        start = time.time()
        resp = requests.post(f"{base}/v1/rerank", json=payload, timeout=10)
        elapsed_ms = (time.time() - start) * 1000
        if resp.status_code == 200:
            results = resp.json().get("results", [])
            return {"status": "OK", "latency_ms": elapsed_ms, "results_count": len(results)}
        else:
            return {"status": f"ERR({resp.status_code})", "latency_ms": elapsed_ms, "results_count": 0}
    except requests.Timeout:
        return {"status": "TIMEOUT", "latency_ms": 10000, "results_count": 0}
    except requests.RequestException as e:
        return {"status": f"FAIL({type(e).__name__})", "latency_ms": 0, "results_count": 0}


def render_bar(used: float, total: float, width: int = 30) -> str:
    """渲染进度条，used/total 单位 GB"""
    if total <= 0:
        return "[" + "?" * width + "]"
    ratio = min(used / total, 1.0)
    filled = int(width * ratio)
    return "[" + "█" * filled + "░" * (width - filled) + "]"


def monitor(base_url: str, interval: int, gpu_total_gb: float,
            xinference_url: str = "", rerank_model: str = ""):
    """主监控循环"""
    has_xin = bool(xinference_url and rerank_model)
    xin_title = f" + Xinference Rerank ({rerank_model})" if has_xin else ""

    print(f"╔══════════════════════════════════════════════════════════╗")
    print(f"║  Ollama 模型显存监控{xin_title:<28s}║")
    print(f"║  Ollama: {base_url:<46s}║")
    if has_xin:
        xin_base = xinference_url.rstrip("/v1").rstrip("/")
        print(f"║  Xinference: {xin_base:<44s}║")
    print(f"║  刷新间隔: {interval}s  GPU 总显存: {gpu_total_gb:.0f} GB{' ' * (28 - len(str(int(gpu_total_gb))))}║")
    print(f"╚══════════════════════════════════════════════════════════╝")
    print(f"  按 Ctrl+C 退出\n")

    prev_models = None

    while True:
        now = datetime.now().strftime("%H:%M:%S")

        # 获取已加载模型
        running = get_running_models(base_url)

        if running is None:
            print(f"\r[{now}] 连接失败，{interval}s 后重试...", end="", flush=True)
            time.sleep(interval)
            continue

        # 获取全部模型列表
        all_models = get_all_models(base_url)
        loaded_names = {m["name"] for m in running}
        idle_models = [m for m in all_models if m.get("id") not in loaded_names]

        # 计算显存
        total_vram = sum(m.get("size_vram", 0) for m in running)
        total_ram = sum(m.get("size", 0) - m.get("size_vram", 0) for m in running)
        total_size = sum(m.get("size", 0) for m in running)

        # 清屏并输出
        print(f"\033[2J\033[H", end="")  # ANSI 清屏+光标回左上角

        print(f"┌─────────────────────────────────────────────────────────┐")
        print(f"│  ⏱ {now}  刷新间隔 {interval}s                             │")
        print(f"├─────────────────────────────────────────────────────────┤")

        if not running:
            print(f"│                                                         │")
            print(f"│  当前无已加载模型                                       │")
            print(f"│                                                         │")
        else:
            # 逐个显示模型
            for m in running:
                name = m.get("name", "?")
                vram = m.get("size_vram", 0)
                ram = m.get("size", 0) - vram
                details = m.get("details", {})
                family = details.get("family", "?")
                params = details.get("parameter_size", "?")
                quant = details.get("quantization_level", "?")
                ctx = m.get("context_length", "?")
                expires = m.get("expires_at", "")

                # 过期时间
                expire_str = ""
                if expires:
                    try:
                        dt = datetime.fromisoformat(expires)
                        now_aware = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
                        remaining = (dt - now_aware).total_seconds()
                        if remaining > 0:
                            expire_str = f"  {remaining:.0f}s 后卸载"
                        else:
                            expire_str = "  即将卸载"
                    except ValueError:
                        pass

                print(f"│  📦 {name}")
                print(f"│     家族: {family}  参数: {params}  量化: {quant}  上下文: {ctx}")
                print(f"│     显存(VRAM): {fmt_bytes(vram):>10s}   内存(RAM): {fmt_bytes(ram):>10s}{expire_str}")

            # 显存汇总
            print(f"├─────────────────────────────────────────────────────────┤")
            vram_gb = total_vram / 1024 ** 3
            bar = render_bar(vram_gb, gpu_total_gb)
            pct = (vram_gb / gpu_total_gb * 100) if gpu_total_gb > 0 else 0
            print(f"│  显存占用 {bar} {pct:5.1f}%")
            print(f"│  VRAM: {fmt_bytes(total_vram):>10s}  RAM: {fmt_bytes(total_ram):>10s}  总计: {fmt_bytes(total_size):>10s}")

        # 未加载的模型
        if idle_models:
            print(f"├─────────────────────────────────────────────────────────┤")
            print(f"│  💤 未加载模型 ({len(idle_models)} 个):")
            idle_names = [m.get("id", "?") for m in idle_models]
            # 每行最多 3 个
            for i in range(0, len(idle_names), 3):
                chunk = idle_names[i:i+3]
                line = "  ".join(f"{n}" for n in chunk)
                print(f"│     {line}")

        # Xinference Rerank 模型监控
        if has_xin:
            print(f"├─────────────────────────────────────────────────────────┤")
            print(f"│  🔀 Xinference Rerank 模型")

            xin_models = get_xinference_models(xinference_url)
            rerank_found = any(m.get("id", "") == rerank_model for m in xin_models)

            if not xin_models:
                print(f"│     ❌ Xinference 连接失败或无已启动模型")
            elif not rerank_found:
                print(f"│     ⚠️  模型 '{rerank_model}' 未启动")
                # 显示 Xinference 上已启动的其他模型
                if xin_models:
                    started = [m.get("id", "?") for m in xin_models]
                    print(f"│     已启动模型: {', '.join(started)}")
            else:
                print(f"│     ✅ 模型 '{rerank_model}' 已启动")
                # 显示 Xinference 上的所有模型
                started = [m.get("id", "?") for m in xin_models]
                others = [n for n in started if n != rerank_model]
                if others:
                    print(f"│     其他已启动: {', '.join(others)}")

                # 测试 rerank 可用性和延迟
                test = test_rerank(xinference_url, rerank_model)
                status_icon = "✅" if test["status"] == "OK" else "❌"
                print(f"│     {status_icon} Rerank 测试: {test['status']}  延迟: {test['latency_ms']:.0f}ms  返回结果数: {test['results_count']}")

        print(f"└─────────────────────────────────────────────────────────┘")
        print(f"  按 Ctrl+C 退出")

        prev_models = running
        time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description="实时监控 Ollama 模型显存 + Xinference Rerank 模型状态")
    parser.add_argument(
        "--base-url",
        default="http://192.168.1.155:11434",
        help="Ollama 基础 URL (默认 http://192.168.1.155:11434)",
    )
    parser.add_argument(
        "--xinference-url",
        default="http://192.168.1.155:9997/v1",
        help="Xinference API URL (默认 http://192.168.1.155:9997/v1)",
    )
    parser.add_argument(
        "--rerank-model",
        default="bge-reranker-v2-m3",
        help="Xinference 中 Rerank 模型的 ID (默认 bge-reranker-v2-m3)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=5,
        help="刷新间隔秒数 (默认 5)",
    )
    parser.add_argument(
        "--gpu-memory",
        type=float,
        default=96,
        help="GPU 总显存 GB 数，用于计算占用率 (默认 96，即 4×4090)",
    )
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    xinference_url = args.xinference_url.rstrip("/")
    rerank_model = args.rerank_model

    # 先测试 Ollama 连通性
    running = get_running_models(base_url)
    if running is None:
        print(f"[ERROR] 无法连接到 Ollama {base_url}，请确认服务是否运行")
        sys.exit(1)

    # 测试 Xinference 连通性（可选）
    if xinference_url and rerank_model:
        xin_models = get_xinference_models(xinference_url)
        if not xin_models:
            print(f"[WARN] 无法连接到 Xinference {xinference_url} 或无已启动模型，Rerank 监控将不可用")

    try:
        monitor(base_url, args.interval, args.gpu_memory,
                xinference_url=xinference_url, rerank_model=rerank_model)
    except KeyboardInterrupt:
        print("\n\n监控已停止。")


if __name__ == "__main__":
    main()
