"""
data/kb_version.py — KB 全局指纹（用于缓存一致性校验）

设计目标:
  - 同一时刻同一 KB 状态 → 同一 fingerprint
  - KB 任意 doc 增删改 → fingerprint 必变
  - 5 分钟内重复调用 → 直接返回 lru 缓存，不打 RAGFlow
  - RAGFlow 调用失败 → 返回 FALLBACK_FINGERPRINT（让所有缓存视为失效）

使用方式:
  from data.kb_version import compute_kb_fingerprint
  kb_ver = compute_kb_fingerprint()    # 16 位 hex 字符串
"""

import hashlib
import json
import time
import threading

import requests

from core.config import (
    RAGFLOW_API_BASE,
    RAGFLOW_API_KEY,
    RAGFLOW_DATASET_ID,
    KB_FINGERPRINT_TTL_SECONDS,
    ENABLE_KB_FINGERPRINT,
)


# 进程内缓存: (fingerprint, fetched_at)
_kb_version_cache: dict = {"fingerprint": None, "fetched_at": 0.0}
_kb_version_lock = threading.Lock()

# 兜底值: RAGFlow 拉取失败时使用，让所有 qa_cache 缓存失效（视为 kb_version 不匹配）
FALLBACK_FINGERPRINT = "KB_UNAVAILABLE"

# 清理去重：记录上一次触发清理的指纹，避免同一指纹反复清理
_last_cleaned_fingerprint: str | None = None


def _purge_stale_kb_cache(new_fingerprint: str) -> int:
    """
    KB 指纹变化时，清理 qa_cache 中所有旧 kb_version 的记录。
    不做删除操作（只标记也够了），这里直接 DELETE。
    Returns: 删除条数。
    """
    deleted = 0
    try:
        from core.database import get_db
        conn = get_db()
        conn.execute(
            "DELETE FROM qa_cache WHERE kb_version != ?",
            (new_fingerprint,),
        )
        deleted = conn.total_changes
        conn.commit()
        conn.close()
        if deleted > 0:
            print(f"[KBVersion] KB 指纹变化，已清理 {deleted} 条旧缓存")
    except Exception as e:
        print(f"[KBVersion] 清理旧缓存失败（不影响主流程）: {e}")
    return deleted


def compute_kb_fingerprint() -> str:
    """
    拉取 RAGFlow 数据集下所有文档元数据，排序后 SHA-256，取前 16 位。
    5 分钟内复用上次结果。RAGFlow 调用失败时返回 FALLBACK_FINGERPRINT。
    KB 指纹变化时自动清理 qa_cache 中旧版本的记录。
    """
    if not ENABLE_KB_FINGERPRINT:
        return FALLBACK_FINGERPRINT

    global _last_cleaned_fingerprint
    now = time.time()
    with _kb_version_lock:
        cached_fp = _kb_version_cache["fingerprint"]
        cached_at = _kb_version_cache["fetched_at"]
        if cached_fp and (now - cached_at) < KB_FINGERPRINT_TTL_SECONDS:
            return cached_fp

        try:
            resp = requests.get(
                f"{RAGFLOW_API_BASE}/datasets/{RAGFLOW_DATASET_ID}/documents",
                headers={"Authorization": f"Bearer {RAGFLOW_API_KEY}"},
                params={"page": 1, "page_size": 500},
                timeout=10,
            )
            resp.raise_for_status()
            docs = resp.json().get("data", {}).get("docs", [])
            # 关键字段指纹（不包含 content，避免大字段影响计算）
            payload = json.dumps(
                sorted(
                    (
                        d.get("id", ""),
                        d.get("name", ""),
                        d.get("update_time", 0),
                        d.get("chunk_count", 0),
                    )
                    for d in docs
                ),
                ensure_ascii=False,
                sort_keys=True,
            )
            fp = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
            # 指纹变化时清理旧缓存（同指纹不重复清理）
            if cached_fp and fp != cached_fp and fp != _last_cleaned_fingerprint:
                _purge_stale_kb_cache(fp)
            _last_cleaned_fingerprint = fp
            _kb_version_cache["fingerprint"] = fp
            _kb_version_cache["fetched_at"] = now
            print(f"[KBVersion] fingerprint={fp} (docs={len(docs)})")
            return fp
        except Exception as e:
            print(f"[KBVersion] RAGFlow 拉取失败，使用 fallback: {e}")
            # 失败时不更新 _fetched_at，让下次尽快重试
            return FALLBACK_FINGERPRINT


def invalidate_kb_fingerprint_cache() -> None:
    """
    强制清空进程内指纹缓存。供以下场景调用:
      - RAGFlow 文档上传/删除/更新 API 的钩子（未来扩展）
      - 单元测试 / 集成测试
      - 运维手动触发
    """
    with _kb_version_lock:
        _kb_version_cache["fingerprint"] = None
        _kb_version_cache["fetched_at"] = 0.0
