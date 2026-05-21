"""
data/dify_service.py — Dify 知识库 API 封装

提供知识库和文档的查询接口，供管理员页面调用。
"""

import os

import requests


DIFY_API_BASE = os.environ.get("DIFY_API_BASE", "https://api.dify.ai/v1")
DIFY_API_KEY = os.environ.get("DIFY_DATASET_KEY", "")


def _headers() -> dict:
    """构造 Dify API 请求头。"""
    return {
        "Authorization": f"Bearer {DIFY_API_KEY}",
        "Content-Type": "application/json",
    }


def list_datasets(page: int = 1, limit: int = 20) -> dict:
    """
    获取知识库列表。

    Returns:
        {
            "data": [{"id", "name", "description", "document_count",
                      "word_count", "created_at", ...}],
            "has_more": bool,
            "limit": int,
            "total": int,
            "page": int,
        }

    Raises:
        RuntimeError: API 调用失败时抛出，包含状态码和错误信息。
    """
    resp = requests.get(
        f"{DIFY_API_BASE}/datasets",
        headers=_headers(),
        params={"page": page, "limit": limit},
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"获取知识库列表失败：{resp.status_code} {resp.text}")
    return resp.json()


def list_documents(dataset_id: str, page: int = 1, limit: int = 20) -> dict:
    """
    获取指定知识库内的文档列表。

    Returns:
        {
            "data": [{"id", "name", "indexing_status", "word_count",
                      "hit_count", "created_at", ...}],
            "has_more": bool,
            "limit": int,
            "total": int,
            "page": int,
        }

    Raises:
        RuntimeError: API 调用失败时抛出，包含状态码和错误信息。
    """
    resp = requests.get(
        f"{DIFY_API_BASE}/datasets/{dataset_id}/documents",
        headers=_headers(),
        params={"page": page, "limit": limit},
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"获取文档列表失败：{resp.status_code} {resp.text}")
    return resp.json()
