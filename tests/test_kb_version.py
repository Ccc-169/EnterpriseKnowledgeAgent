"""
tests/test_kb_version.py — KB 全局指纹单元测试

覆盖:
  - 同一文档列表 → 同一 fingerprint（幂等）
  - 改 1 个 doc 的 update_time → fingerprint 变化
  - 加 1 个 doc → fingerprint 变化
  - 删 1 个 doc → fingerprint 变化
  - 5 分钟 TTL 内重复调用 → 不打 RAGFlow（用 mock 计数验证）
  - TTL 过期后重新调用 → 重新打 RAGFlow
  - RAGFlow 请求失败 → 返回 FALLBACK_FINGERPRINT
  - ENABLE_KB_FINGERPRINT=false → 立即返回 FALLBACK，不打 RAGFlow
  - invalidate_kb_fingerprint_cache() → 强制下次重新计算
"""

import time

from core.config import KB_FINGERPRINT_TTL_SECONDS, ENABLE_KB_FINGERPRINT
from data.kb_version import (
    compute_kb_fingerprint,
    invalidate_kb_fingerprint_cache,
    FALLBACK_FINGERPRINT,
)


def _docs(d1=1, d2=2, d3=3):
    """构造测试用的文档列表。"""
    return [
        {"id": "d1", "name": "部署.docx",   "update_time": d1, "chunk_count": 10},
        {"id": "d2", "name": "需求.docx",   "update_time": d2, "chunk_count": 20},
        {"id": "d3", "name": "运维手册.pdf", "update_time": d3, "chunk_count": 30},
    ]


def test_同一文档列表产生相同指纹(fake_ragflow_docs):
    """幂等性: 同一输入 → 同一 fingerprint。"""
    fake_ragflow_docs(_docs())
    fp1 = compute_kb_fingerprint()
    invalidate_kb_fingerprint_cache()  # 强制重算
    fake_ragflow_docs(_docs())
    fp2 = compute_kb_fingerprint()
    assert fp1 == fp2


def test_改_update_time指纹变化(fake_ragflow_docs):
    """改 1 个 doc 的 update_time → fingerprint 变化。"""
    fake_ragflow_docs(_docs(d1=1))
    fp1 = compute_kb_fingerprint()
    invalidate_kb_fingerprint_cache()
    fake_ragflow_docs(_docs(d1=2))
    fp2 = compute_kb_fingerprint()
    assert fp1 != fp2


def test_增加文档指纹变化(fake_ragflow_docs):
    """+1 doc → fingerprint 变化。"""
    fake_ragflow_docs(_docs())
    fp1 = compute_kb_fingerprint()
    invalidate_kb_fingerprint_cache()
    fake_ragflow_docs(_docs() + [{"id": "d4", "name": "新.docx", "update_time": 4, "chunk_count": 5}])
    fp2 = compute_kb_fingerprint()
    assert fp1 != fp2


def test_删除文档指纹变化(fake_ragflow_docs):
    """-1 doc → fingerprint 变化。"""
    fake_ragflow_docs(_docs())
    fp1 = compute_kb_fingerprint()
    invalidate_kb_fingerprint_cache()
    fake_ragflow_docs([_docs()[0], _docs()[1]])  # 删掉 d3
    fp2 = compute_kb_fingerprint()
    assert fp1 != fp2


def test_ttl内重复调用不重新打RAGFlow(fake_ragflow_docs, monkeypatch):
    """5 分钟内重复调用 → 命中进程内缓存。"""
    fake_ragflow_docs(_docs())
    call_count = {"n": 0}
    real_get_orig = None

    import data.kb_version as kv_module
    real_compute = kv_module.compute_kb_fingerprint

    def counting_compute():
        call_count["n"] += 1
        return real_compute()

    monkeypatch.setattr(kv_module, "compute_kb_fingerprint", counting_compute)
    # 但 conftest 已经 patch 了 requests.get（按需触发），所以计数要重新统计
    # 改用 monkeypatch.setattr requests.get 计数
    import requests
    original_get = requests.get
    get_count = {"n": 0}

    def counting_get(*args, **kwargs):
        get_count["n"] += 1
        return original_get(*args, **kwargs)

    monkeypatch.setattr(requests, "get", counting_get)

    # 第 1 次 → 必打 RAGFlow
    fp1 = compute_kb_fingerprint()
    # 第 2~5 次 → 命中 lru
    for _ in range(4):
        fp2 = compute_kb_fingerprint()
        assert fp1 == fp2

    assert get_count["n"] == 1, f"TTL 内应只打 1 次 RAGFlow，实际 {get_count['n']} 次"


def test_ttl过期后重新打RAGFlow(fake_ragflow_docs, monkeypatch):
    """TTL 过期后 → 重新打 RAGFlow。"""
    import requests
    get_count = {"n": 0}
    original_get = requests.get

    def counting_get(*args, **kwargs):
        get_count["n"] += 1
        return original_get(*args, **kwargs)

    monkeypatch.setattr(requests, "get", counting_get)
    fake_ragflow_docs(_docs())

    # 强行把 TTL 改成 0
    monkeypatch.setattr("data.kb_version.KB_FINGERPRINT_TTL_SECONDS", 0)
    # 也要 patch 函数内 from core.config import 进来的版本
    monkeypatch.setattr("core.config.KB_FINGERPRINT_TTL_SECONDS", 0)
    # 函数内 import 后拿到了旧值，需要 reload
    import importlib
    import data.kb_version
    importlib.reload(data.kb_version)
    monkeypatch.setattr("requests.get", counting_get)

    fp1 = data.kb_version.compute_kb_fingerprint()
    time.sleep(0.01)  # 确保时间差
    fp2 = data.kb_version.compute_kb_fingerprint()

    assert get_count["n"] >= 2, f"TTL=0 时应每次都打，实际 {get_count['n']} 次"


def test_RAGFlow失败返回fallback(fake_ragflow_docs, monkeypatch):
    """RAGFlow 抛异常 → 返回 FALLBACK_FINGERPRINT，不抛异常。"""
    import requests
    def boom(*args, **kwargs):
        raise ConnectionError("RAGFlow down")

    monkeypatch.setattr(requests, "get", boom)
    invalidate_kb_fingerprint_cache()
    fp = compute_kb_fingerprint()
    assert fp == FALLBACK_FINGERPRINT


def test_disable_kb_fingerprint直接返回fallback(fake_ragflow_docs, monkeypatch):
    """ENABLE_KB_FINGERPRINT=false → 立即返回 fallback，不打 RAGFlow。"""
    import requests
    get_count = {"n": 0}
    def counting_get(*args, **kwargs):
        get_count["n"] += 1
        raise RuntimeError("应该不会调用")

    monkeypatch.setattr(requests, "get", counting_get)
    monkeypatch.setattr("data.kb_version.ENABLE_KB_FINGERPRINT", False)

    fp = compute_kb_fingerprint()
    assert fp == FALLBACK_FINGERPRINT
    assert get_count["n"] == 0

    # 恢复
    monkeypatch.setattr("data.kb_version.ENABLE_KB_FINGERPRINT", True)


def test_invalidate强制清空缓存(fake_ragflow_docs, monkeypatch):
    """invalidate 后 → 下次必重新打 RAGFlow。"""
    import requests
    get_count = {"n": 0}
    original_get = requests.get

    def counting_get(*args, **kwargs):
        get_count["n"] += 1
        return original_get(*args, **kwargs)

    monkeypatch.setattr(requests, "get", counting_get)
    fake_ragflow_docs(_docs())

    fp1 = compute_kb_fingerprint()
    fp2 = compute_kb_fingerprint()
    assert get_count["n"] == 1

    invalidate_kb_fingerprint_cache()
    fp3 = compute_kb_fingerprint()
    assert get_count["n"] == 2
    assert fp1 == fp3  # 同样的 docs，同一个 fingerprint


def test_fingerprint是16位hex(fake_ragflow_docs):
    """fingerprint 必须是 16 位 hex 字符串。"""
    fake_ragflow_docs(_docs())
    fp = compute_kb_fingerprint()
    assert len(fp) == 16
    int(fp, 16)  # 能被解析为 16 进制整数，否则抛 ValueError


def test_空文档列表仍然返回有效指纹(fake_ragflow_docs):
    """KB 为空时仍返回稳定的 fingerprint。"""
    fake_ragflow_docs([])
    fp1 = compute_kb_fingerprint()
    invalidate_kb_fingerprint_cache()
    fake_ragflow_docs([])
    fp2 = compute_kb_fingerprint()
    assert fp1 == fp2
    assert len(fp1) == 16
