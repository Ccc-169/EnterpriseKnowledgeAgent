"""
data/kb_search.py — Dify 知识库语义检索

提供文档编写场景下的知识库检索能力：
- search_knowledge_base: 调用 Dify 检索 API
- format_kb_results: 将检索结果格式化为 LLM 可用的参考文本（含来源标注）
"""

import requests
from core.config import RAGFLOW_API_BASE, RAGFLOW_API_KEY, RAGFLOW_DATASET_ID


def search_knowledge_base(query: str, top_k: int = 5) -> list:
    """调用 Dify 知识库语义检索，返回记录列表。

    Args:
        query: 搜索查询（通常是用户的需求描述）
        top_k: 最大返回条数

    Returns:
        list[dict]，每条：{"score": float, "segment": {"document": {"name": str}, "content": str}}
        网络错误或未配置时返回空列表。
    """
    if not RAGFLOW_API_KEY or not RAGFLOW_DATASET_ID:
        return []

    try:
        resp = requests.post(
            f"{RAGFLOW_API_BASE}/retrieval",
            headers={
                "Authorization": f"Bearer {RAGFLOW_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "question": query,
                "dataset_ids": [RAGFLOW_DATASET_ID],
                "page": 1,
                "page_size": top_k,
                "similarity_threshold": 0.2,
                "vector_similarity_weight": 0.3,
                "keyword": False,
            },
            timeout=30,
        )
        if resp.status_code != 200:
            return []
        data = resp.json().get("data", {})
        chunks = data.get("chunks", [])
        doc_name_map = {d["doc_id"]: d["doc_name"] for d in data.get("doc_aggs", [])}
        return [
            {
                "score": c.get("similarity", 0),
                "segment": {
                    "content": c.get("content", ""),
                    "document": {"name": doc_name_map.get(c.get("document_id", ""), "未知文档")},
                },
            }
            for c in chunks
        ]
    except Exception:
        return []


def format_kb_results(records: list, max_chars: int = 3000) -> str:
    """将检索记录格式化为参考文本，含文档来源标注。

    Args:
        records: search_knowledge_base 返回值
        max_chars: 最大返回字符数，按 score 降序优先保留高分记录

    Returns:
        格式化的参考文本，每条格式：
        [知识库：文档名]
        内容片段...
        ---
    """
    if not records:
        return ""

    chunks = sorted(records, key=lambda x: x.get("score", 0), reverse=True)
    parts = []
    total_chars = 0

    for c in chunks:
        doc_name = c["segment"]["document"]["name"]
        text = c["segment"]["content"]
        if total_chars + len(text) > max_chars:
            remaining = max_chars - total_chars
            if remaining < 50:
                break
            text = text[:remaining] + "..."
        parts.append(f"[知识库：{doc_name}]\n{text}")
        total_chars += len(text)
        if total_chars >= max_chars:
            break

    return "\n---\n".join(parts)


def build_reference_context(uploaded_contents: list[tuple[str, str]], kb_query: str) -> str:
    """融合附件内容和知识库检索结果，构建统一参考上下文。

    Args:
        uploaded_contents: [(文件名, 正文), ...]
        kb_query: 知识库检索查询词

    Returns:
        格式化的参考上下文字符串，可供 LLM prompt 拼接使用。
        若两者都为空则返回空字符串。
    """
    parts = []

    # 附件部分
    if uploaded_contents:
        attachment_lines = []
        for i, (fname, text) in enumerate(uploaded_contents, start=1):
            attachment_lines.append(f"[附件{i}：{fname}]\n{text}")
        parts.append("=== 用户上传附件 ===\n" + "\n\n".join(attachment_lines))

    # 知识库部分
    records = search_knowledge_base(kb_query)
    kb_text = format_kb_results(records)
    if kb_text:
        parts.append("=== 知识库参考资料 ===\n" + kb_text)

    if not parts:
        return ""

    return "\n\n".join(parts) + "\n\n---\n"
