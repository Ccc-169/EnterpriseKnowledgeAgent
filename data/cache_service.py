"""
data/cache_service.py — 经验记忆缓存（长期记忆：Q&A 向量相似度匹配）

提供：
- embed_text: 调用 Qwen embedding API 将文本转为向量
- cosine_similarity: 余弦相似度计算
- search_cache: 在 messages 表中检索与当前问题相似的历史 Q&A（兼容旧路径）
- save_embedding: 将问题向量存入对应的 user 消息（兼容旧路径）
- search_qa_cache: 在 qa_cache 表中检索，支持 KB 指纹校验 + 双阈值分层（高/中/低/未命中）
- save_qa_cache_entry: 将 Q&A 写入 qa_cache 表（带 kb_version 字段）
- should_cache: 判断问题是否值得缓存（过滤噪音）
"""

import json
import math
import os

import requests
from langsmith import traceable

from core.database import get_db

# ── 常量 ────────────────────────────────────────────────
EMBEDDING_MODEL = "text-embedding-v3"
SIMILARITY_THRESHOLD = 0.80        # 余弦相似度命中阈值
MIN_QUESTION_LENGTH = 6            # 最短问题字符数
QWEN_API_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"


# ── 噪音过滤 ────────────────────────────────────────────

_NOISE_PATTERNS = {
    "谢谢", "好的", "ok", "OK", "继续", "还有呢", "还有吗",
    "为什么", "什么意思", "怎么用", "详细说", "具体一点",
    "那这个呢", "上一个呢", "能再说一遍吗", "不",
    "可是我还是不太明白", "你能再解释一下吗", "不是这个意思",
    "嗯", "好", "是", "？", "?", "收到", "明白", "了解",
    "请继续", "接着说", "然后呢", "然后呢？","请问", "那", "那么",
}


def _should_cache(question: str) -> bool:
    """判断问题是否值得缓存（排除纯闲聊和指代追问）。"""
    stripped = question.strip()
    if len(stripped) < MIN_QUESTION_LENGTH:
        return False
    if stripped in _NOISE_PATTERNS:
        return False
    return True


# ── 向量化 ──────────────────────────────────────────────

def embed_text(text: str) -> list[float] | None:
    """
    调用 Qwen embedding API 将文本转为向量。

    Returns:
        1024 维浮点数列表，失败返回 None。
    """
    try:
        resp = requests.post(
            f"{QWEN_API_BASE}/embeddings",
            headers={
                "Authorization": f"Bearer {os.environ.get('QWEN_API_KEY', '')}",
                "Content-Type": "application/json",
            },
            json={
                "model": EMBEDDING_MODEL,
                "input": text,
            },
            timeout=15,
        )
        if resp.status_code != 200:
            print(f"[Embedding] 请求失败: {resp.status_code} {resp.text[:100]}")
            return None
        data = resp.json()
        return data["data"][0]["embedding"]
    except Exception as e:
        print(f"[Embedding] 异常: {e}")
        return None


# ── 相似度计算 ──────────────────────────────────────────

def cosine_similarity(a: list[float], b: list[float]) -> float:
    """计算两个向量的余弦相似度（0~1）。"""
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ── 缓存检索 ────────────────────────────────────────────

@traceable(name="CACHE: 检索历史相似Q&A", run_type="retriever")
def search_cache(
    question_vec: list[float],
    threshold: float = SIMILARITY_THRESHOLD,
    limit: int = 3,
) -> list[dict]:
    """
    在 messages 表中检索与当前问题相似的历史 Q&A。

    只扫描 role='user' 且 question_vec 不为空的记录。
    对每条记录计算余弦相似度，返回超过阈值的记录（按相似度降序）。

    Args:
        question_vec: 当前问题的 embedding 向量
        threshold: 余弦相似度阈值（0~1），默认 0.80
        limit: 最多返回几条

    Returns:
        [{"id": int, "question": str, "answer": str, "score": float}, ...]
        answer 为同 conversation 中紧跟该问题的 assistant 消息内容
    """
    if not question_vec:
        return []

    conn = get_db()
    try:
        # 查出所有有 embedding 的用户消息
        rows = conn.execute(
            """SELECT id, conversation_id, content, question_vec
               FROM messages
               WHERE role = 'user' AND question_vec IS NOT NULL
               ORDER BY created_at DESC"""
        ).fetchall()

        results = []
        for row in rows:
            try:
                cached_vec = json.loads(row["question_vec"])
                sim = cosine_similarity(question_vec, cached_vec)
            except Exception:
                continue

            if sim < threshold:
                continue

            # 查找该问题对应的助手回复（同一 conversation，紧跟着的下一条 assistant 消息）
            answer_row = conn.execute(
                """SELECT content FROM messages
                   WHERE conversation_id = ? AND role = 'assistant' AND id > ?
                   ORDER BY id ASC LIMIT 1""",
                (row["conversation_id"], row["id"])
            ).fetchone()

            answer = answer_row["content"] if answer_row else "（未找到对应回答）"
            results.append({
                "message_id": row["id"],
                "question": row["content"],
                "answer": answer,
                "score": round(sim, 4),
            })

        # 按相似度降序，取 top-N
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]
    finally:
        conn.close()


# ── 缓存写入 ────────────────────────────────────────────

@traceable(name="CACHE: 保存Q&A向量", run_type="chain")
def save_embedding(message_id: int, question_vec: list[float]) -> bool:
    """
    将问题向量写入 messages 表的 question_vec 字段。

    Args:
        message_id: messages 表的行 id
        question_vec: embedding 向量

    Returns:
        是否写入成功
    """
    try:
        conn = get_db()
        conn.execute(
            "UPDATE messages SET question_vec = ? WHERE id = ?",
            (json.dumps(question_vec, ensure_ascii=False), message_id),
        )
        conn.commit()
        conn.close()
        print(f"[CacheService] 嵌入已保存: message_id={message_id}")
        return True
    except Exception as e:
        print(f"[CacheService] 嵌入保存失败: {e}")
        return False


# ── 新缓存：qa_cache 表（KB 指纹 + 双阈值短路） ──────────


@traceable(name="CACHE: 分层检索(高/中/低)", run_type="retriever")
def search_qa_cache(
    question_vec: list[float],
    kb_version: str,
    high_threshold: float | None = None,
    med_threshold: float | None = None,
    min_threshold: float | None = None,
    top_k: int | None = None,
) -> dict:
    """
    在 qa_cache 表中检索与当前问题相似的历史 Q&A，并按 KB 指纹 + 三档阈值决策。

    Returns:
        {
            "level":       "high" | "med" | "low" | "miss",
            "answer":      str | None,         # high 时直接给完整答案
            "context":     str | None,         # med 时给完整答案作 prompt 注入
            "score":       float,              # best.score
            "kb_matched":  bool,               # best 是否通过 kb_version 校验
            "raw_candidates": list[dict],      # 调试用: 通过 min_threshold 的所有候选
        }

    决策流程:
      1. 全表扫 + 余弦相似度 ≥ min_threshold 得候选
      2. 过滤 kb_version == 当前 fingerprint 的候选
      3. 剩余候选按分数降序，取 top1 作为 best
      4. best.score ≥ high_threshold → "high"
         best.score ≥ med_threshold  → "med"
         else                        → "low" 或 "miss"（取决于是否有通过 min 但未达 med 的候选）
    """
    from core.config import (
        QA_CACHE_HIGH_CONFIDENCE,
        QA_CACHE_MED_CONFIDENCE,
        QA_CACHE_MIN_CONFIDENCE,
        QA_CACHE_TOP_K,
    )

    if not question_vec:
        return {
            "level": "miss", "answer": None, "context": None,
            "score": 0.0, "kb_matched": False, "raw_candidates": [],
        }

    high_threshold = high_threshold if high_threshold is not None else QA_CACHE_HIGH_CONFIDENCE
    med_threshold  = med_threshold  if med_threshold  is not None else QA_CACHE_MED_CONFIDENCE
    min_threshold  = min_threshold  if min_threshold  is not None else QA_CACHE_MIN_CONFIDENCE
    top_k          = top_k          if top_k          is not None else QA_CACHE_TOP_K

    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT id, question, question_vec, answer, kb_version, hit_count
               FROM qa_cache"""
        ).fetchall()

        all_candidates = []
        for row in rows:
            try:
                cached_vec = json.loads(row["question_vec"])
                sim = cosine_similarity(question_vec, cached_vec)
            except Exception:
                continue
            if sim < min_threshold:
                continue
            all_candidates.append({
                "id": row["id"],
                "question": row["question"],
                "answer": row["answer"],
                "kb_version": row["kb_version"],
                "hit_count": row["hit_count"],
                "score": round(sim, 4),
            })

        # 按分数降序，取 top_k
        all_candidates.sort(key=lambda x: x["score"], reverse=True)
        all_candidates = all_candidates[:top_k]

        # 过滤 KB 版本匹配的候选
        kb_matched = [c for c in all_candidates if c["kb_version"] == kb_version]

        if not all_candidates:
            return {
                "level": "miss", "answer": None, "context": None,
                "score": 0.0, "kb_matched": False, "raw_candidates": [],
            }

        # 优先取 kb_version 匹配中的最高分；无匹配时 best 视为 None
        if kb_matched:
            best = kb_matched[0]
            kb_ok = True
        else:
            best = all_candidates[0]
            kb_ok = False

        score = best["score"]
        answer = best["answer"]

        # 决策
        if kb_ok and score >= high_threshold:
            level = "high"
            return {
                "level": level, "answer": answer, "context": None,
                "score": score, "kb_matched": True, "raw_candidates": all_candidates,
            }
        if kb_ok and score >= med_threshold:
            level = "med"
            return {
                "level": level, "answer": None, "context": answer,
                "score": score, "kb_matched": True, "raw_candidates": all_candidates,
            }
        if kb_ok:
            return {
                "level": "low", "answer": None, "context": None,
                "score": score, "kb_matched": True, "raw_candidates": all_candidates,
            }
        # kb_version 不匹配 — 视为失效
        return {
            "level": "miss", "answer": None, "context": None,
            "score": score, "kb_matched": False, "raw_candidates": all_candidates,
        }
    finally:
        conn.close()


def save_qa_cache_entry(
    question: str,
    question_vec: list[float],
    answer: str,
    kb_version: str,
) -> int | None:
    """
    将一条 Q&A 写入 qa_cache 表（含 kb_version 字段）。
    Returns:
        新行 id，失败返回 None。
    """
    if not question_vec or not question or not answer or not kb_version:
        return None
    try:
        conn = get_db()
        cur = conn.execute(
            """INSERT INTO qa_cache (question, question_vec, answer, kb_version)
               VALUES (?, ?, ?, ?)""",
            (
                question,
                json.dumps(question_vec, ensure_ascii=False),
                answer,
                kb_version,
            ),
        )
        conn.commit()
        new_id = cur.lastrowid
        conn.close()
        print(f"[CacheService] qa_cache 写入: id={new_id}, kb_version={kb_version}")

        # 写入后概率性触发清理（20%），避免每次写入都全表扫描
        import random
        if random.random() < 0.2:
            cleanup_qa_cache()

        return new_id
    except Exception as e:
        print(f"[CacheService] qa_cache 写入失败: {e}")
        return None


# ── 缓存清理 ────────────────────────────────────────────

_MAX_QA_CACHE_ROWS = 1000
_MAX_DAYS_UNHIT = 7


def cleanup_qa_cache(
    max_rows: int = _MAX_QA_CACHE_ROWS,
    max_days_unhit: int = _MAX_DAYS_UNHIT,
) -> int:
    """
    清理 qa_cache 表，两个维度：
    1. 时间维度：删除超过 max_days_unhit 天未被命中的记录
    2. 数量维度：总数超过 max_rows 时，删除最久未命中的旧记录

    写入路径每次抽 20% 概率触发（避免每次写入都做全表扫描）。
    Returns:
        删除的记录条数。
    """
    deleted = 0
    conn = None
    try:
        conn = get_db()

        # 1. 时间清理：超过 N 天未命中（从未命中 + 创建超期的也纳入）
        conn.execute(
            """DELETE FROM qa_cache
               WHERE (last_hit_at IS NOT NULL
                      AND last_hit_at < datetime('now', ?))
                  OR (last_hit_at IS NULL
                      AND created_at < datetime('now', ?))""",
            (f"-{max_days_unhit} days", f"-{max_days_unhit} days"),
        )
        deleted += conn.total_changes

        # 2. 数量上限：超出 max_rows 时，删除最久未命中的记录
        count = conn.execute("SELECT COUNT(*) FROM qa_cache").fetchone()[0]
        overflow = count - max_rows
        if overflow > 0:
            conn.execute(
                """DELETE FROM qa_cache
                   WHERE id IN (
                       SELECT id FROM qa_cache
                       ORDER BY
                           CASE WHEN last_hit_at IS NULL THEN 1 ELSE 0 END,
                           COALESCE(last_hit_at, created_at) ASC
                       LIMIT ?
                   )""",
                (overflow,),
            )
            deleted += conn.total_changes

        conn.commit()
        if deleted > 0:
            print(f"[CacheService] 清理完毕: 删除 {deleted} 条旧缓存 (当前表大小 {count - overflow} 条)")
    except Exception as e:
        print(f"[CacheService] 清理失败（不影响主流程）: {e}")
    finally:
        if conn:
            conn.close()
    return deleted


@traceable(name="CACHE: 命中计数", run_type="chain")
def increment_qa_cache_hit(cache_id: int) -> None:
    """短路命中后调用，更新 hit_count 和 last_hit_at。仅用于 observability。"""
    try:
        conn = get_db()
        conn.execute(
            """UPDATE qa_cache
               SET hit_count = hit_count + 1, last_hit_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (cache_id,),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[CacheService] hit_count 更新失败: {e}")
