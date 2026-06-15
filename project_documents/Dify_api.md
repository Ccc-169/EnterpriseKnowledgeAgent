# Dify API 接口汇总

本项目共调用了 **3 个 Dify API**，分布在 `rag_agent`、`doc_agent`、`dify_service.py` 中。

Base URL 由环境变量 `DIFY_API_BASE` 控制，默认为 `https://api.dify.ai/v1`。  
认证方式：所有接口均使用 `Authorization: Bearer <DIFY_DATASET_KEY>` 请求头。

---

## 1. 知识库语义检索

**调用方**：`rag_agent`（`rag_search` 工具、`list_kb_documents` 回退检索）、`doc_agent`（`search_knowledge_base` 工具）、`data/kb_search.py`（`search_knowledge_base` 函数）

```
POST {DIFY_API_BASE}/datasets/{dataset_id}/retrieve
```

**请求头**
```
Authorization: Bearer <DIFY_DATASET_KEY>
Content-Type: application/json
```

**请求体**
```json
{
  "query": "检索查询字符串",
  "retrieval_model": {
    "search_method": "semantic_search",
    "reranking_enable": false,
    "top_k": 10,
    "score_threshold_enabled": false
  }
}
```

> `top_k` 取值：`rag_agent` 中首次检索为 10，`doc_agent` 为 5，`kb_search.py` 为 5（可通过参数覆盖）。

**响应体**
```json
{
  "records": [
    {
      "score": 0.85,
      "segment": {
        "content": "文档片段内容",
        "document": {
          "name": "文件名.docx"
        }
      }
    }
  ]
}
```

**调用位置**

| 文件 | 函数/工具 | 用途 |
|------|-----------|------|
| `agents/rag_agent.py` | `_retrieve_from_dify()` | rag_agent 主检索（含改写查询、回退查询、重试查询） |
| `agents/doc_agent.py` | `search_knowledge_base` tool | doc_agent 在生成目录/文档前检索参考资料 |
| `data/kb_search.py` | `search_knowledge_base()` | 供 doc_page 等页面直接调用的检索封装 |

---

## 2. 获取知识库文档列表

**调用方**：`rag_agent`（`list_kb_documents` 工具）、`data/dify_service.py`（`list_documents` 函数）

```
GET {DIFY_API_BASE}/datasets/{dataset_id}/documents
```

**请求头**
```
Authorization: Bearer <DIFY_DATASET_KEY>
```

**Query 参数**

| 参数 | 类型 | 说明 |
|------|------|------|
| `page` | int | 页码，从 1 开始 |
| `limit` | int | 每页条数，默认 20 |

**响应体**
```json
{
  "data": [
    {
      "id": "doc-id",
      "name": "文件名.docx",
      "indexing_status": "completed",
      "word_count": 1234,
      "hit_count": 56,
      "created_at": 1700000000
    }
  ],
  "has_more": false,
  "limit": 20,
  "total": 5,
  "page": 1
}
```

**调用位置**

| 文件 | 函数/工具 | 用途 |
|------|-----------|------|
| `agents/rag_agent.py` | `list_kb_documents` tool | 用户询问知识库中有哪些文档时，分页遍历全量返回 |
| `data/dify_service.py` | `list_documents()` | 管理员页面查看指定知识库的文档列表 |

---

## 3. 获取知识库列表

**调用方**：`data/dify_service.py`（`list_datasets` 函数），供管理员页面调用

```
GET {DIFY_API_BASE}/datasets
```

**请求头**
```
Authorization: Bearer <DIFY_DATASET_KEY>
Content-Type: application/json
```

**Query 参数**

| 参数 | 类型 | 说明 |
|------|------|------|
| `page` | int | 页码，从 1 开始 |
| `limit` | int | 每页条数，默认 20 |

**响应体**
```json
{
  "data": [
    {
      "id": "dataset-id",
      "name": "知识库名称",
      "description": "描述",
      "document_count": 10,
      "word_count": 50000,
      "created_at": 1700000000
    }
  ],
  "has_more": false,
  "limit": 20,
  "total": 2,
  "page": 1
}
```

**调用位置**

| 文件 | 函数 | 用途 |
|------|------|------|
| `data/dify_service.py` | `list_datasets()` | 管理员页面展示所有可用知识库 |

---

## 环境变量

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `DIFY_API_BASE` | `https://api.dify.ai/v1` | Dify 服务端点，私有部署时需修改 |
| `DIFY_DATASET_KEY` | —（必填）| Dataset API Key，用于所有接口认证 |
| `DIFY_KB_ID` | —（必填）| 目标知识库 ID，检索接口使用 |
