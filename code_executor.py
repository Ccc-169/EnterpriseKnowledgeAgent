# code_executor.py — 进程池预热版
# 改造点：subprocess 冷启动 → multiprocessing.Pool 预热，消除 pandas 重复加载开销
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Union
from contextlib import asynccontextmanager
import multiprocessing
import os
import io
import sys
import traceback


# ── Worker 进程初始化：预加载 pandas 等重模块 ──────────
def _worker_init():
    """每个 Worker 启动时调用一次，预加载 pandas 消除冷启动开销。"""
    global _pd, _json, _os, _warnings
    import pandas as _pd
    import json as _json
    import os as _os
    import warnings as _warnings
    _warnings.filterwarnings('ignore')


# ── Worker 执行函数：在预热进程中 exec 代码 ────────────
def _worker_execute(code: str, data_path) -> dict:
    """在预热 Worker 中执行代码，namespace 隔离 + stdout 捕获。"""
    namespace = {
        '__builtins__': __builtins__,
        'pd': _pd,
        'json': _json,
        'os': _os,
        'DATA_PATH': data_path,
    }

    old_stdout = sys.stdout
    sys.stdout = captured = io.StringIO()
    try:
        exec(code, namespace)
        output = captured.getvalue().strip()
        return {"status": "success", "output": output, "error": ""}
    except Exception:
        partial_output = captured.getvalue().strip()
        error_msg = traceback.format_exc()
        return {"status": "error", "output": partial_output, "error": error_msg}
    finally:
        sys.stdout = old_stdout


# ── Pool 生命周期管理 ──────────────────────────────────
_pool = None  # multiprocessing.Pool 实例


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时创建预热进程池，关闭时销毁。"""
    global _pool
    pool_size = int(os.environ.get("EXECUTOR_POOL_SIZE", "0")) or min(4, os.cpu_count() or 2)
    _pool = multiprocessing.Pool(processes=pool_size, initializer=_worker_init)
    print(f"[code_executor] 进程池已预热：{pool_size} workers，pandas 已加载")
    yield
    if _pool:
        _pool.terminate()
        _pool.join()


app = FastAPI(lifespan=lifespan)


# ── 请求模型 ──────────────────────────────────────────
class CodeRequest(BaseModel):
    code: str
    data_path: Union[str, list[str]]   # 支持单文件(str)或多文件(list)


class CodeBatchRequest(BaseModel):
    codes: list[str]                    # 多个代码块，在一个进程中执行
    data_path: Union[str, list[str]]    # 公用数据路径


# ── API 端点 ──────────────────────────────────────────
@app.post("/execute")
def execute_code(req: CodeRequest):
    return _run_code(req.code, req.data_path)


@app.post("/execute_batch")
def execute_code_batch(req: CodeBatchRequest):
    """批量执行：多个代码块共享预热进程，按分隔符拆分输出。"""
    merged_code = "\nprint('__BATCH_SEP__')\n".join(req.codes)
    raw_output = _run_code(merged_code, req.data_path)
    parts = raw_output["output"].split("__BATCH_SEP__")
    raw_output["outputs"] = [p.strip() for p in parts]
    return raw_output


def _run_code(code: str, data_path: Union[str, list[str]]) -> dict:
    """核心执行：在预热进程池中执行代码，30s 超时。"""
    if _pool is None:
        return {"status": "error", "output": "", "error": "进程池未初始化"}
    try:
        result = _pool.apply_async(_worker_execute, (code, data_path)).get(timeout=30)
        return result
    except multiprocessing.TimeoutError:
        return {"status": "error", "output": "", "error": "执行超时（30s）"}
    except Exception as e:
        return {"status": "error", "output": "", "error": f"执行异常：{e}"}


# 启动：uvicorn code_executor:app --port 8001
