"""
data/ragflow_service.py — RAGFlow 知识库 API 封装

提供知识库和文档的查询接口，供管理员页面调用。
"""

import os

import requests


RAGFLOW_API_BASE   = os.environ.get("RAGFLOW_API_BASE", "http://localhost/api/v1")
RAGFLOW_API_KEY    = os.environ.get("RAGFLOW_API_KEY", "")


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {RAGFLOW_API_KEY}",
        "Content-Type": "application/json",
    }


def list_datasets(page: int = 1, limit: int = 20) -> dict:
    """
    获取知识库列表。

    Returns:
        {
            "data": [{"id", "name", "description", "document_count", "chunk_count", ...}],
            "total": int,
        }

    Raises:
        RuntimeError: API 调用失败时抛出，包含状态码和错误信息。
    """
    resp = requests.get(
        f"{RAGFLOW_API_BASE}/datasets",
        headers=_headers(),
        params={"page": page, "page_size": limit},
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"获取知识库列表失败：{resp.status_code} {resp.text}")
    body = resp.json()
    datasets = body.get("data", [])
    return {
        "data": datasets,
        "total": len(datasets),
        "page": page,
        "limit": limit,
        "has_more": False,
    }


def list_documents(dataset_id: str, page: int = 1, limit: int = 20) -> dict:
    """
    获取指定知识库内的文档列表。

    Returns:
        {
            "data": [{"id", "name", "run", "chunk_count", "created_at", ...}],
            "total": int,
        }

    Raises:
        RuntimeError: API 调用失败时抛出，包含状态码和错误信息。
    """
    resp = requests.get(
        f"{RAGFLOW_API_BASE}/datasets/{dataset_id}/documents",
        headers=_headers(),
        params={"page": page, "page_size": limit},
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"获取文档列表失败：{resp.status_code} {resp.text}")
    data = resp.json().get("data", {})
    docs = data.get("docs", [])
    return {
        "data": docs,
        "total": data.get("total", len(docs)),
        "page": page,
        "limit": limit,
        "has_more": False,
    }
