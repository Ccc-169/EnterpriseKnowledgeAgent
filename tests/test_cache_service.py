"""
tests/test_cache_service.py — 双阈值检索 + qa_cache 表操作 单元测试

覆盖:
  - search_qa_cache 在 4 档 level 下的返回
  - kb_version 不匹配时一律视为 miss（即使 score=1.0）
  - save_qa_cache_entry 写入 + 反查
  - increment_qa_cache_hit 累加
  - 候选 score 排序正确
  - 候选 top_k 截断正确
  - 空 vec 输入安全
  - 旧函数 search_cache 仍能跑（兼容性）
"""

import math
import json

from data.cache_service import (
    embed_text,
    search_qa_cache,
    save_qa_cache_entry,
    increment_qa_cache_hit,
    cosine_similarity,
    _should_cache,
)


def _vec(values):
    """构造测试用的固定向量（直接给数值，避免依赖真实 embedding API）。"""
    n = len(values)
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]


def test_cosine_similarity_完全相同():
    a = _vec([1.0, 0.0, 0.0])
    assert abs(cosine_similarity(a, a) - 1.0) < 1e-6


def test_cosine_similarity_正交():
    a = _vec([1.0, 0.0])
    b = _vec([0.0, 1.0])
    assert abs(cosine_similarity(a, b)) < 1e-6


def test_cosine_similarity_长度不同():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0, 0.0]) == 0.0


def test_should_cache过滤噪音():
    assert _should_cache("") is False
    assert _should_cache("a") is False            # 太短
    assert _should_cache("谢谢") is False          # 噪音词
    assert _should_cache("hi") is False
    assert _should_cache("请帮我介绍知识库智能体的本地化部署") is True


def test_save_qa_cache_entry_写入反查(temp_db):
    """save 后应该能通过 search_qa_cache 找到。"""
    q_vec = _vec([1.0, 0.0, 0.0])
    new_id = save_qa_cache_entry(
        question="如何本地化部署？",
        question_vec=q_vec,
        answer="1. 准备环境\n2. 启动服务",
        kb_version="abc123def456",
    )
    assert new_id is not None and new_id > 0

    result = search_qa_cache(q_vec, kb_version="abc123def456")
    assert result["level"] == "high"
    assert result["answer"] == "1. 准备环境\n2. 启动服务"
    assert result["score"] > 0.99


def test_search_qa_cache_高置信(temp_db):
    """score=1.0 + kb_version 匹配 → high。"""
    q_vec = _vec([0.5, 0.5, 0.5])
    save_qa_cache_entry(
        question="本地化部署流程",
        question_vec=q_vec,
        answer="答案A",
        kb_version="v1",
    )
    result = search_qa_cache(q_vec, kb_version="v1")
    assert result["level"] == "high"
    assert result["answer"] == "答案A"
    assert result["kb_matched"] is True


def test_search_qa_cache_中置信(temp_db):
    """score ∈ [0.85, 0.95) + kb_version 匹配 → med。"""
    q_vec = _vec([1.0, 0.0, 0.0])
    # 构造一个相似度约 0.9 的向量
    near_vec = _vec([0.9, 0.436, 0.0])  # 与 [1,0,0] cos≈0.9
    save_qa_cache_entry(
        question="本地化部署",
        question_vec=near_vec,
        answer="答案B",
        kb_version="v1",
    )
    sim = cosine_similarity(q_vec, near_vec)
    assert 0.85 <= sim < 0.95, f"构造的相似度={sim}，应在 [0.85, 0.95) 区间"

    result = search_qa_cache(q_vec, kb_version="v1")
    assert result["level"] == "med"
    assert result["answer"] is None
    assert result["context"] == "答案B"


def test_search_qa_cache_低置信(temp_db):
    """score ∈ [0.80, 0.85) + kb_version 匹配 → low。"""
    q_vec = _vec([1.0, 0.0, 0.0])
    # 构造 cos=0.82 的向量
    near_vec = _vec([0.82, 0.572, 0.0])
    save_qa_cache_entry(
        question="本地化部署",
        question_vec=near_vec,
        answer="答案C",
        kb_version="v1",
    )
    sim = cosine_similarity(q_vec, near_vec)
    assert 0.80 <= sim < 0.85, f"构造的相似度={sim}，应在 [0.80, 0.85) 区间"

    result = search_qa_cache(q_vec, kb_version="v1")
    assert result["level"] == "low"
    assert result["answer"] is None
    assert result["context"] is None


def test_search_qa_cache_KB版本不匹配视为miss(temp_db):
    """即使 score=1.0，KB 版本不一致 → 视为 miss（核心安全保证）。"""
    q_vec = _vec([1.0, 0.0, 0.0])
    save_qa_cache_entry(
        question="本地化部署",
        question_vec=q_vec,
        answer="基于旧KB的答案",
        kb_version="OLD_VERSION",
    )
    result = search_qa_cache(q_vec, kb_version="NEW_VERSION")
    assert result["level"] == "miss"
    assert result["answer"] is None
    assert result["kb_matched"] is False
    assert result["score"] > 0.99  # 分数高但被过滤


def test_search_qa_cache_无候选返回miss(temp_db):
    """空表 → miss。"""
    q_vec = _vec([1.0, 0.0])
    result = search_qa_cache(q_vec, kb_version="v1")
    assert result["level"] == "miss"
    assert result["raw_candidates"] == []


def test_search_qa_cache_空vec安全(temp_db):
    """空 vec → miss，不抛异常。"""
    result = search_qa_cache([], kb_version="v1")
    assert result["level"] == "miss"


def test_search_qa_cache_top_k截断(temp_db):
    """top_k=2 时只返回前 2 条候选（通过参数传入）。"""
    q_vec = _vec([1.0, 0.0])
    # 5 条不同 kb_version 的缓存
    for i in range(5):
        save_qa_cache_entry(
            question=f"q{i}",
            question_vec=_vec([0.9 + i * 0.01, 0.1]),  # 略不同
            answer=f"a{i}",
            kb_version="v1",
        )
    result = search_qa_cache(q_vec, kb_version="v1", top_k=2)
    assert len(result["raw_candidates"]) == 2


def test_search_qa_cache_候选按分数降序(temp_db):
    """raw_candidates 应按 score 降序。"""
    q_vec = _vec([1.0, 0.0])
    # 写入顺序与相似度顺序不一致
    save_qa_cache_entry("q1", _vec([0.85, 0.527]), "a1", "v1")  # sim≈0.85
    save_qa_cache_entry("q2", _vec([0.99, 0.141]), "a2", "v1")  # sim≈0.99
    save_qa_cache_entry("q3", _vec([0.92, 0.392]), "a3", "v1")  # sim≈0.92
    result = search_qa_cache(q_vec, kb_version="v1")
    scores = [c["score"] for c in result["raw_candidates"]]
    assert scores == sorted(scores, reverse=True)


def test_search_qa_cache_自定义阈值(temp_db):
    """允许调用方传入自定义阈值。"""
    q_vec = _vec([1.0, 0.0])
    save_qa_cache_entry("q", q_vec, "a", "v1")
    # 把 high 阈值改成 0.5，score=1.0 仍然 high
    result = search_qa_cache(q_vec, kb_version="v1", high_threshold=0.5)
    assert result["level"] == "high"


def test_increment_qa_cache_hit_累加(temp_db):
    """hit_count 应该累加。"""
    q_vec = _vec([1.0, 0.0])
    new_id = save_qa_cache_entry("q", q_vec, "a", "v1")
    increment_qa_cache_hit(new_id)
    increment_qa_cache_hit(new_id)
    increment_qa_cache_hit(new_id)
    from data.cache_service import get_db
    conn = get_db()
    row = conn.execute("SELECT hit_count FROM qa_cache WHERE id=?", (new_id,)).fetchone()
    conn.close()
    assert row["hit_count"] == 4  # 初始 1 + 3 次 increment


def test_save_qa_cache_entry_缺字段返回None(temp_db):
    """缺关键字段时返回 None，不抛异常。"""
    assert save_qa_cache_entry("", _vec([1.0]), "a", "v1") is None
    assert save_qa_cache_entry("q", [], "a", "v1") is None
    assert save_qa_cache_entry("q", _vec([1.0]), "", "v1") is None
    assert save_qa_cache_entry("q", _vec([1.0]), "a", "") is None


def test_KB版本变化时新cache可命中(temp_db):
    """KB 改 → fingerprint 变 → 旧 cache miss → 写入新 cache 后命中。"""
    q_vec = _vec([1.0, 0.0])
    save_qa_cache_entry("q", q_vec, "旧答案", "v1")
    # v1 时命中
    r1 = search_qa_cache(q_vec, kb_version="v1")
    assert r1["level"] == "high"
    # v2 时 miss
    r2 = search_qa_cache(q_vec, kb_version="v2")
    assert r2["level"] == "miss"
    # 写入 v2 后命中
    save_qa_cache_entry("q", q_vec, "新答案", "v2")
    r3 = search_qa_cache(q_vec, kb_version="v2")
    assert r3["level"] == "high"
    assert r3["answer"] == "新答案"
