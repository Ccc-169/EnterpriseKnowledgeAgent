"""
data/cache_service.py — 经验记忆缓存（长期记忆：Q&A 向量相似度匹配）

提供：
- embed_text: 调用 Qwen embedding API 将文本转为向量
- cosine_similarity: 余弦相似度计算
- search_cache: 在 messages 表中检索与当前问题相似的历史 Q&A
- save_embedding: 将问题向量存入对应的 user 消息
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

@traceable(name="Qwen Embedding", run_type="embedding")
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
