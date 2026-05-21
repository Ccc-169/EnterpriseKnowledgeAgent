---
name: admin-dify-kb-ui
overview: 为管理员页面新增"知识库管理"Tab，通过 Dify API 查看知识库列表及每个知识库内的文档列表。
design:
  styleKeywords:
    - Clean
    - Functional
  fontSystem:
    fontFamily: sans-serif
    heading:
      size: 24px
      weight: 600
    subheading:
      size: 18px
      weight: 500
    body:
      size: 14px
      weight: 400
  colorSystem:
    primary:
      - "#1E88E5"
    background:
      - "#FFFFFF"
      - "#F5F5F5"
    text:
      - "#212121"
      - "#757575"
    functional:
      - "#4CAF50"
      - "#FFC107"
      - "#F44336"
todos:
  - id: create-dify-service
    content: 创建 data/dify_service.py，封装 list_datasets 和 list_documents API 调用
    status: completed
  - id: add-kb-tab
    content: 修改 pages/admin_page.py，新增"知识库管理"Tab 及渲染函数
    status: completed
    dependencies:
      - create-dify-service
  - id: add-env-config
    content: 在 .env.example 中补充可选的 DIFY_API_BASE 配置说明
    status: completed
  - id: test-kb-ui
    content: 启动应用验证知识库管理界面，检查分页和错误处理
    status: completed
    dependencies:
      - add-kb-tab
---

## 产品概述

为 admin 管理员新增"知识库管理"界面，通过 Dify API 查看知识库列表及每个知识库中的文档详情。

## 核心功能

- 查看所有知识库列表（数据集名称、文档数量、字数、创建时间）
- 点击知识库查看其中的文档列表（文档名、索引状态、字数、命中次数）
- 知识库列表和文档列表均支持分页浏览
- 仅管理员可访问，只读模式（不支持上传/删除）

## 技术栈

- 现有 Streamlit 前端框架
- requests 库调用 Dify REST API
- 复用项目中已有的 Dify API 调用模式（参考 `agents/rag_agent.py`）

## 实现方案

### 系统架构

- 新增 `data/dify_service.py` 封装 Dify API 调用，与业务逻辑解耦
- 修改 `pages/admin_page.py`，新增第三个 Tab"知识库管理"

### 模块划分

1. **Dify API 服务模块**（`data/dify_service.py`）

- `list_datasets(page, limit)` — 调用 `GET /v1/datasets`
- `list_documents(dataset_id, page, limit)` — 调用 `GET /v1/datasets/{id}/documents`
- 统一处理认证 Header（`Bearer {DIFY_DATASET_KEY}`）
- 统一错误处理和响应解析

2. **管理员页面扩展**（`pages/admin_page.py`）

- 新增第三个 Tab："知识库管理"
- 渲染函数 `_render_knowledge_base()`
- 知识库列表 → 点击展开 → 文档列表（使用 `st.expander` 或 `st.dataframe`）

### 数据流

```
用户点击"知识库管理" Tab
  → 调用 list_datasets() 获取知识库列表
  → 用户点击某知识库
    → 调用 list_documents(dataset_id) 获取文档列表
    → 展示文档详情
```

### 实施细节

- **性能**：Dify API 本身支持分页（`page` + `limit` 参数），直接透传，不额外缓存
- **错误处理**：API 调用失败时显示 `st.error()` 友好提示，不抛出堆栈
- **向后兼容**：不修改现有"用户管理"和"审计日志"Tab，不影响已有功能
- **环境变量**：复用已有的 `DIFY_DATASET_KEY`，新增可选变量 `DIFY_API_BASE`（默认 `https://api.dify.ai/v1`）

## 目录结构

```
d:\App_data\HNGD-Agent\HNGD-backend\
├── data/
│   ├── conversation_service.py   # 已有
│   └── dify_service.py           # [NEW] Dify API 封装
└── pages/
    └── admin_page.py             # [MODIFY] 新增"知识库管理"Tab
```

## 设计风格

沿用现有 Streamlit 默认风格，保持与管理后台其他页面一致。

## 页面结构设计

### 知识库管理 Tab 布局（从上到下）

1. **页面标题区**

- `st.subheader("知识库管理")`
- 简要说明：当前为只读模式，展示 Dify 知识库及文档信息

2. **知识库列表区**

- 使用 `st.columns()` 展示每个知识库的关键信息卡片
- 每张卡片显示：知识库名称、文档数量、总字数、创建时间
- 使用 `st.button("查看文档")` 或 `st.expander()` 展开文档列表

3. **文档列表区**（展开后显示）

- 使用 `st.dataframe()` 或 `st.table()` 展示文档列表
- 列：文档名、索引状态（Completed/Processing）、字数、命中次数
- 支持分页（上一页/下一页按钮）

4. **分页控件**

- 知识库列表底部："上一页" "下一页" 按钮 + 当前页码显示
- 文档列表底部：同上