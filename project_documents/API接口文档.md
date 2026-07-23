# HNGD 知识助手 — API 接口文档

> 版本：v1.0 | 更新日期：2026-06-22
> 本文档为纯 API 参考规范，面向前端/第三方开发者，仅描述 HTTP 接口细节，不涉及历史迁移对照。

---

## 一、概述

| 服务 | 入口文件 | 端口 | 说明 |
|------|---------|------|------|
| **主 API 服务** | `api.py` | 28001 | HTML 前端业务接口，JWT 鉴权 |
| **静态文件服务** | `html_files/` | 28080 | 前端 HTML/JS/CSS 资源 |

**Base URL**：`http://localhost:28001`

---

## 二、公共约定

### 2.1 鉴权方式

| 鉴权层级 | 适用范围 | 说明 |
|----------|---------|------|
| **无鉴权** | `/api/auth/login` | 公开接口 |
| **`verify_token`** | 大部分 `/api/*` | JWT Bearer Token，所有登录用户可用 |
| **`require_admin`** | `/api/admin/*` | JWT + `role === "admin"`，否则 403 |
| **`embed_token`** | `/api/embed/*` | 不使用 JWT，请求体携带 `embed_token` 字段 |

### 2.2 JWT 结构

- **算法**：HS256
- **密钥**：`hngd-knowledge-agent-secret`（生产环境应改为环境变量）
- **有效期**：8 小时
- **Header**：`Authorization: Bearer <token>`

**Payload**：
```json
{
  "sub": "1",
  "username": "admin",
  "role": "admin",
  "display_name": "管理员",
  "exp": 1748000000
}
```

### 2.3 角色体系

| 角色 | 权限范围 |
|------|---------|
| `visitor` | 无使用权限（仅提示） |
| `user` | 对话、文档编写、数据统计、系统接口浏览 |
| `admin` | user 全部权限 + 管理后台（用户管理、审计日志、知识库、接口导入/删除/权限） |

### 2.4 错误响应格式

所有错误响应统一为：
```json
{ "detail": "错误描述文本" }
```

| 状态码 | 含义 |
|--------|------|
| 400 | 请求参数错误 |
| 401 | Token 无效或已过期 / embed_token 无效 |
| 403 | 需要管理员权限 |
| 404 | 资源不存在或无权限 |
| 409 | 资源冲突（如用户名重复） |
| 502 | 上游服务异常 |
| 503 | 服务未配置（如缺少 RAGFLOW_API_KEY） |

---

## 三、认证模块

### 3.1 POST `/api/auth/login`

用户登录，返回 JWT Token。

**鉴权**：无

**请求体**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `username` | string | 是 | 用户名 |
| `password` | string | 是 | 明文密码（HTTPS 传输） |
| `role` | string | 是 | 前端选择的身份：`"user"` 或 `"admin"` |

```json
{ "username": "admin", "password": "123456", "role": "admin" }
```

**成功响应 `200 OK`**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `token` | string | JWT，有效期 8 小时 |
| `user_id` | int | 用户 ID |
| `username` | string | 用户名 |
| `role` | string | 实际角色 |
| `display_name` | string | 显示名称 |
| `avatar` | string \| null | 头像（base64 或 null） |

```json
{
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "user_id": 1,
  "username": "admin",
  "role": "admin",
  "display_name": "管理员",
  "avatar": null
}
```

**错误响应**：

| 状态码 | `detail` | 触发条件 |
|--------|---------|---------|
| 401 | `用户名或密码错误` | 账号密码不匹配 |
| 401 | `该账号不是管理员账号，请切换登录身份` | role=admin 但实际不是管理员 |
| 401 | `该账号不是普通用户账号，请切换登录身份` | role=user 但实际不是普通用户 |

---

### 3.2 POST `/api/auth/logout`

记录登出审计日志。Token 失效由前端清除 localStorage 实现，服务端不主动撤销 Token。

**鉴权**：`verify_token`

**请求体**：无

**成功响应 `200 OK`**：
```json
{ "ok": true }
```

---

## 四、对话模块

### 4.1 GET `/api/conversations`

获取当前用户的对话列表，按 `updated_at` 降序排列。

**鉴权**：`verify_token`

**请求参数**：无

**成功响应 `200 OK`**：

```json
[
  {
    "id": 12,
    "title": "公司差旅报销制度",
    "created_at": "2026-05-31T10:00:00",
    "updated_at": "2026-05-31T10:05:30"
  }
]
```

---

### 4.2 POST `/api/conversations`

新建对话，默认标题"新对话"。

**鉴权**：`verify_token`

**请求体**：无

**成功响应 `200 OK`**：
```json
{ "id": 13, "title": "新对话" }
```

---

### 4.3 DELETE `/api/conversations/{conv_id}`

删除对话及其所有消息（级联删除）。

**鉴权**：`verify_token`

**Path 参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `conv_id` | int | 对话 ID |

**成功响应 `200 OK`**：
```json
{ "ok": true }
```

**错误响应**：`404` — 对话不存在或不属于当前用户

---

### 4.4 GET `/api/conversations/{conv_id}/messages`

获取指定对话的全部消息及对话基本信息。

**鉴权**：`verify_token`

**Path 参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `conv_id` | int | 对话 ID |

**成功响应 `200 OK`**：

```json
{
  "conversation": { "id": 12, "title": "公司差旅报销制度" },
  "messages": [
    {
      "id": 1,
      "role": "user",
      "content": "公司差旅报销制度是怎样的？",
      "steps_log": null,
      "agent_used": null,
      "created_at": "2026-05-31T10:00:10"
    },
    {
      "id": 2,
      "role": "assistant",
      "content": "根据知识库资料...",
      "steps_log": ["🔧 调用工具：rag_search", "✅ 工具返回：检索到3条记录"],
      "agent_used": "rag_agent",
      "created_at": "2026-05-31T10:00:18"
    }
  ]
}
```

**错误响应**：`404` — 对话不存在或无权限

---

## 五、对话交互模块（SSE）

### 5.1 POST `/api/chat/stream` ⭐ 核心接口

发送消息，以 SSE（Server-Sent Events）流式返回思考步骤和最终回答。

**鉴权**：`verify_token`

**请求体**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `message` | string | 是 | 用户输入内容 |
| `conversation_id` | int \| null | 否 | 当前对话 ID；`null` 时服务端自动创建新对话 |
| `mode` | string | 否 | 默认 `"rag"`，可选：`"rag"` / `"data"` / `"write"` / `"api"` |

```json
{ "message": "上月考勤异常情况统计", "conversation_id": 12, "mode": "data" }
```

**mode 与后端调用对应**：

| mode | 调用目标 | 说明 |
|------|---------|------|
| `rag` | `rag_agent` | 知识库检索问答 |
| `data` | `data_agent` | 数据统计分析 |
| `write` | `rag_agent` | 文档仿写（复用 rag_agent） |
| `api` | `api_agent` | 真实接口查询 |

**响应格式**：`Content-Type: text/event-stream`

每行格式：`data: <JSON>\n\n`，SSE 事件类型如下：

| 事件类型 | 字段 | 说明 | 推送时机 |
|----------|------|------|---------|
| `init` | `conversation_id`, `title` | 初始化信息，含对话 ID 和标题 | 流开始时；首条消息自动命名 |
| `queued` | `position` | 排队位次（前方人数） | 生成槽被占用时推送 |
| `progress` | `text` | 实时进度文本 | agent 工具调用过程中推送 |
| `step` | `text` | LangGraph 工具调用/返回步骤 | 每个 node update 时推送 |
| `answer` | `text`, `warning`, `agent` | 最终回答 | 回答完成后推送 |
| `done` | — | 流结束信号 | 流结束时推送 |
| `error` | `text` | 执行异常描述 | 异常时推送 |

**事件示例**：

```
data: {"type":"init","conversation_id":12,"title":"上月考勤..."}
data: {"type":"queued","position":0}
data: {"type":"progress","text":"正在检索知识库..."}
data: {"type":"step","text":"🔧 调用工具：rag_search"}
data: {"type":"answer","text":"以下是上月考勤异常汇总：...","warning":false,"agent":"data_agent"}
data: {"type":"done"}
```

**并发控制**：
- 信号量限制：默认并发数为 1（对齐 Ollama `-np 1`）
- 单飞机制：同一用户发送新请求时自动挤掉旧任务
- 客户端断开检测：可配置 `CHAT_CANCEL_ON_DISCONNECT` 自动取消

**服务端内部流程**：
```
验证 JWT
→ 若 conversation_id=null → 自动创建新对话
→ save_message(role="user")
→ 若标题为"新对话" → 自动生成标题
→ SSE: type:"init"
→ 注册 cancel_event（单飞）
→ 进入生成槽信号量 → 若被占用则推送 type:"queued"
→ 调用 chat_direct(mode 对应的 agent)
  ├─ 实时进度 → SSE: type:"progress"
  └─ 工具步骤 → SSE: type:"step"
→ 取得最终回答
→ save_message(role="assistant", steps_log, agent_used)
→ log_event("chat")
→ SSE: type:"answer"
→ SSE: type:"done"
```

> **前端接入建议**：使用 `fetch + ReadableStream` 而非 `EventSource`，因为 EventSource 不支持自定义 Header（无法携带 Authorization）。

---

### 5.2 POST `/api/chat/stop`

主动停止当前用户正在进行的对话生成。

**鉴权**：`verify_token`

**请求体**：无

**成功响应 `200 OK`**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `ok` | bool | 操作成功 |
| `stopped` | bool | 是否实际停止了一个正在进行的任务 |

```json
{ "ok": true, "stopped": true }
```

---

## 六、用户设置模块

### 6.1 PUT `/api/user/display-name`

修改当前用户的显示名称。

**鉴权**：`verify_token`

**请求体**：

| 字段 | 类型 | 必填 | 校验 |
|------|------|------|------|
| `display_name` | string | 是 | 非空，长度 ≤ 50 |

```json
{ "display_name": "新显示名称" }
```

**成功响应 `200 OK`**：
```json
{ "ok": true, "display_name": "新显示名称" }
```

**错误响应**：

| 状态码 | `detail` |
|--------|---------|
| 400 | `显示名称长度不能超过 50 个字符` |
| 400 | 其他 auth_service 返回的错误消息 |

---

### 6.2 PUT `/api/user/avatar`

更新当前用户的头像（base64 图片或 SVG data URL）。

**鉴权**：`verify_token`

**请求体**：

| 字段 | 类型 | 必填 | 校验 |
|------|------|------|------|
| `avatar` | string | 是 | 必须以 `data:` 开头 |

```json
{ "avatar": "data:image/png;base64,iVBORw0KGgo..." }
```

**成功响应 `200 OK`**：
```json
{ "ok": true }
```

**错误响应**：

| 状态码 | `detail` |
|--------|---------|
| 400 | `头像格式无效` |
| 400 | 其他 auth_service 返回的错误消息 |

---

### 6.3 PUT `/api/user/password`

修改当前用户的登录密码，需提供旧密码验证。

**鉴权**：`verify_token`

**请求体**：

| 字段 | 类型 | 必填 | 校验 |
|------|------|------|------|
| `old_password` | string | 是 | 非空 |
| `new_password` | string | 是 | 长度 ≥ 6 |

```json
{ "old_password": "旧密码", "new_password": "新密码123" }
```

**成功响应 `200 OK`**：
```json
{ "ok": true }
```

**错误响应**：

| 状态码 | `detail` |
|--------|---------|
| 400 | `新密码长度至少 6 位` |
| 400 | 其他 auth_service 返回的错误消息（如旧密码不正确） |

---

## 七、文档编写模块

### 7.1 POST `/api/doc/generate-outline`

Step 1：根据用户需求（+ 可选附件）调用 doc_agent 生成文档目录。

**鉴权**：`verify_token`

**请求格式**：`multipart/form-data`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `requirements` | string (Form) | 是 | 用户需求描述文本 |
| `files` | File[] (File) | 否 | 参考附件，支持多文件上传 |

**附件处理**：
- 支持格式：txt、md、docx、pdf 等（由 `data/file_parser.py` 按扩展名解析）
- 单文件内容超过 8000 字符时自动截断

**成功响应 `200 OK`**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `outline` | string | AI 生成的文档目录（Markdown 格式） |
| `steps_log` | string[] | 工具调用步骤记录 |
| `reference_context` | string | 附件解析后的文本上下文（Step 2 需原样回传） |

```json
{
  "outline": "# 一、概述\n## 1.1 背景...",
  "steps_log": ["调用工具：doc_agent"],
  "reference_context": "=== 用户上传附件 ===\n[附件1：xxx.pdf]\n..."
}
```

**错误响应**：`500` — `目录生成失败：{异常信息}`

---

### 7.2 POST `/api/doc/generate-content`

Step 2：根据已确认目录调用 doc_agent 生成完整文档，并自动保存到历史记录。

**鉴权**：`verify_token`

**请求体**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `requirements` | string | 是 | 用户原始需求 |
| `outline` | string | 是 | 用户确认/修改后的目录 |
| `reference_context` | string | 否 | Step 1 返回的附件上下文（原样回传） |

```json
{
  "requirements": "撰写安全生产规范文档",
  "outline": "# 一、概述\n## 1.1 背景...",
  "reference_context": "=== 用户上传附件 ===\n..."
}
```

**成功响应 `200 OK`**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `content` | string | 生成的完整文档内容（Markdown 格式） |
| `steps_log` | string[] | 工具调用步骤记录 |
| `document_id` | int \| null | 自动保存的文档记录 ID |

```json
{
  "content": "# 安全生产规范文档\n\n## 一、概述...",
  "steps_log": ["调用工具：doc_agent"],
  "document_id": 42
}
```

**错误响应**：`500` — `文档生成失败：{异常信息}`

**服务端内部流程**：
- 生成完成后自动调用 `_auto_save_document()`：保存文档记录 + 创建侧边栏对话条目
- 写审计日志 `doc_generate`

---

## 八、管理员 — 用户管理

> 所有管理员接口需 `role === "admin"`，否则返回 `403`。

### 8.1 GET `/api/admin/stats`

返回系统统计摘要。

**鉴权**：`require_admin`

**成功响应 `200 OK`**：
```json
{
  "total_users": 42,
  "active_users_today": 8,
  "total_chats_today": 156,
  "total_chats_all": 3042
}
```

---

### 8.2 GET `/api/admin/users`

返回全部用户列表。

**鉴权**：`require_admin`

**成功响应 `200 OK`**：
```json
[
  {
    "id": 1,
    "username": "admin",
    "display_name": "管理员",
    "role": "admin",
    "is_active": true,
    "created_at": "2024-01-15 10:30:00"
  }
]
```

---

### 8.3 POST `/api/admin/users`

创建新用户。

**鉴权**：`require_admin`

**请求体**：

| 字段 | 类型 | 必填 | 校验 |
|------|------|------|------|
| `username` | string | 是 | 非空，唯一 |
| `password` | string | 是 | 非空 |
| `display_name` | string | 否 | 默认空串 |
| `role` | string | 是 | `visitor` / `user` / `admin` |

```json
{ "username": "zhangsan", "password": "123456", "display_name": "张三", "role": "user" }
```

**成功响应 `200 OK`**：
```json
{ "ok": true }
```

**错误响应**：

| 状态码 | `detail` |
|--------|---------|
| 400 | `无效角色，可选值：visitor, user, admin` |
| 409 | `用户名「xxx」已存在` |

---

### 8.4 PUT `/api/admin/users/{target_id}/role`

修改指定用户的角色。

**鉴权**：`require_admin`

**Path 参数**：`target_id` — 目标用户 ID

**请求体**：

| 字段 | 类型 | 必填 | 校验 |
|------|------|------|------|
| `role` | string | 是 | `visitor` / `user` / `admin` |

```json
{ "role": "admin" }
```

**成功响应 `200 OK`**：
```json
{ "ok": true }
```

**错误响应**：

| 状态码 | `detail` |
|--------|---------|
| 400 | `无效角色，可选值：visitor, user, admin` |
| 404 | `用户不存在` |

---

### 8.5 PUT `/api/admin/users/{target_id}/active`

启用或禁用指定用户。

**鉴权**：`require_admin`

**Path 参数**：`target_id` — 目标用户 ID

**请求体**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `is_active` | bool | 是 | `true`=启用，`false`=禁用 |

```json
{ "is_active": false }
```

**成功响应 `200 OK`**：
```json
{ "ok": true }
```

**错误响应**：

| 状态码 | `detail` |
|--------|---------|
| 400 | `不能禁用当前登录账户`（target_id == 当前用户且 is_active=false） |
| 404 | `用户不存在` |

---

### 8.6 DELETE `/api/admin/users/{target_id}`

删除用户及其全部历史数据（对话、消息、审计日志、文档历史），不可撤销。

**鉴权**：`require_admin`

**Path 参数**：`target_id` — 目标用户 ID

**成功响应 `200 OK`**：
```json
{ "ok": true }
```

**错误响应**：

| 状态码 | `detail` |
|--------|---------|
| 400 | `不能删除当前登录账户` |
| 404 | `用户不存在` |

---

## 九、管理员 — 审计日志

### 9.1 GET `/api/admin/logs`

查询审计日志，支持多维过滤。

**鉴权**：`require_admin`

**Query 参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `username` | string | 否 | 精确匹配用户名 |
| `action` | string | 否 | 操作类型：`login` / `logout` / `chat` / `admin_op` / `denied` / `update_display_name` / `update_password` / `update_avatar` / `doc_outline_generate` / `doc_generate` / `import_interfaces_url` / `import_interfaces_json` / `import_interfaces_selected_tags` / `delete_interface` / `delete_interface_file` / `delete_service` / `update_permissions` / `grant_all_permissions` / `revoke_all_permissions` |
| `date_from` | string | 否 | 开始日期 `YYYY-MM-DD` |
| `date_to` | string | 否 | 结束日期 `YYYY-MM-DD` |
| `limit` | int | 否 | 默认 200，最大 500 |
| `offset` | int | 否 | 默认 0 |

**成功响应 `200 OK`**：

```json
{
  "total": 42,
  "logs": [
    {
      "id": 1,
      "created_at": "2026-05-20 15:30:45",
      "username": "admin",
      "action": "login",
      "agent_used": null,
      "question": null,
      "status": "success"
    }
  ]
}
```

---

## 十、管理员 — 知识库管理

> 知识库接口依赖 RAGFLOW_API_KEY 环境变量，未配置时返回 `503`。

### 10.1 GET `/api/admin/kb/datasets`

获取 RAGFlow 知识库列表（分页）。

**鉴权**：`require_admin`

**Query 参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `page` | int | 否 | 默认 1 |
| `limit` | int | 否 | 默认 20 |

**成功响应 `200 OK`**（透传 RAGFlow 响应）：
```json
{
  "data": [
    {
      "id": "uuid-string",
      "name": "产品手册",
      "description": "...",
      "document_count": 32,
      "word_count": 128000,
      "embedding_model": "text-embedding-ada-002"
    }
  ],
  "has_more": true,
  "total": 8
}
```

**错误响应**：

| 状态码 | `detail` |
|--------|---------|
| 503 | `未配置 RAGFLOW_API_KEY，请在 .env 文件中配置后重启服务` |
| 502 | RAGFlow 服务异常 |

---

### 10.2 GET `/api/admin/kb/datasets/{dataset_id}/documents`

获取指定知识库的文档列表（分页）。

**鉴权**：`require_admin`

**Path 参数**：`dataset_id` — 知识库 ID

**Query 参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `page` | int | 否 | 默认 1 |
| `limit` | int | 否 | 默认 20 |

**成功响应 `200 OK`**：
```json
{
  "data": [
    {
      "name": "2024年产品规格书.pdf",
      "indexing_status": "completed",
      "display_status": "已完成",
      "word_count": 4200,
      "hit_count": 87
    }
  ],
  "has_more": false,
  "total": 12
}
```

**错误响应**：同 10.1

---

## 十一、管理员 — 数据文件

### 11.1 GET `/api/admin/data-files`

列出 DATA_DIR 目录下的数据文件。

**鉴权**：`require_admin`

**成功响应 `200 OK`**：
```json
{
  "dir": "/path/to/data_dir",
  "files": [
    { "name": "attendance.csv", "ext": "csv", "size_kb": 128.5 },
    { "name": "safety_report.xlsx", "ext": "xlsx", "size_kb": 256.0 }
  ]
}
```

**错误响应**：

| 状态码 | `detail` |
|--------|---------|
| 503 | `未配置 DATA_DIR，请在 .env 文件中配置后重启服务` |
| 503 | `DATA_DIR 目录不存在：{path}` |

---

## 十二、系统接口浏览

> 所有登录用户均可浏览有权访问的接口。

### 12.1 GET `/api/system-interfaces/tree`

返回当前用户有权访问的接口树结构（按服务分组）。

**鉴权**：`verify_token`

**成功响应 `200 OK`**：

返回按服务名分组的接口树。`admin` 角色看到全部接口，`user` 角色只看到已授权的接口。

---

### 12.2 GET `/api/system-interfaces/{interface_id}/detail`

返回单个接口的完整 OpenAPI 定义。

**鉴权**：`verify_token`

**Path 参数**：`interface_id` — 接口索引 ID

**成功响应 `200 OK`**：接口完整定义详情

**错误响应**：`404` — `接口不存在`

---

### 12.3 POST `/api/system-interfaces/{interface_id}/test`

代理发送接口测试请求，返回目标服务的响应。

**鉴权**：`verify_token`

**Path 参数**：`interface_id` — 接口索引 ID

**请求体**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `params` | dict | 否 | Query 参数映射，默认 `{}` |
| `body` | dict \| null | 否 | 请求体 JSON |
| `base_url` | string | 否 | 覆盖接口默认 base_url |

```json
{ "params": {"start_date": "2026-01-01"}, "body": null, "base_url": "" }
```

**成功响应 `200 OK`**：目标服务的原始响应

---

## 十三、管理员 — 接口导入

### 13.1 POST `/api/admin/interfaces/discover-services`

探测 Swagger/OpenAPI 端点类型，返回可用服务列表。

**鉴权**：`require_admin`

**请求体**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `url` | string | 是 | Swagger/OpenAPI 文档 URL |

```json
{ "url": "http://192.168.1.160:18888/v3/api-docs" }
```

**错误响应**：

| 状态码 | `detail` |
|--------|---------|
| 400 | `URL 不能为空` |

---

### 13.2 POST `/api/admin/interfaces/import-from-url`

通过 Swagger URL 导入接口。

**鉴权**：`require_admin`

**请求体**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `url` | string | 是 | Swagger/OpenAPI 文档 URL |
| `service_name` | string | 否 | 服务名（空时自动提取） |

```json
{ "url": "http://192.168.1.160:18888/v3/api-docs", "service_name": "safety_platform" }
```

**成功响应**：导入结果，含 `{ok, message, ...}`。如果检测到大型 spec 需要自定义选择，返回 `type: "custom_select"`。

---

### 13.3 POST `/api/admin/interfaces/import-from-json`

上传 OpenAPI JSON 内容导入接口。

**鉴权**：`require_admin`

**请求体**：JSON 格式，必须包含 OpenAPI spec 结构。可选附加 `service_name` 字段。

```json
{
  "service_name": "my_service",
  "openapi": "3.0.0",
  "info": { "title": "My API", "version": "1.0" },
  "paths": { ... }
}
```

**错误响应**：

| 状态码 | `detail` |
|--------|---------|
| 400 | `请求体必须是 JSON 格式` |
| 400 | 导入失败的错误消息 |

---

### 13.4 POST `/api/admin/interfaces/import-selected-tags`

从自定义 openapi-ui 中选择标签导入接口。

**鉴权**：`require_admin`

**请求体**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `url` | string | 是 | Swagger/OpenAPI 文档 URL |
| `service_name` | string | 是 | 服务名称 |
| `selected_queries` | list[dict] | 是 | 选择的标签列表 |

`selected_queries` 每项格式：
```json
{ "query": "/api/alarms/count:get", "tag_name": "报警管理", "tag_desc": "报警相关接口" }
```

**错误响应**：

| 状态码 | `detail` |
|--------|---------|
| 400 | `URL 不能为空` |
| 400 | `必须指定服务名称` |
| 400 | `必须选择至少一个标签` |
| 400 | `导入失败` |

---

## 十四、管理员 — 接口删除

### 14.1 DELETE `/api/admin/interfaces/{interface_id}`

删除单个接口（仅从索引中移除，不删除文件）。

**鉴权**：`require_admin`

**Path 参数**：`interface_id` — 接口索引 ID

**成功响应 `200 OK`**：
```json
{ "ok": true }
```

**错误响应**：`404` — 接口不存在

---

### 14.2 DELETE `/api/admin/interfaces/file/{service_name}/{file_name}`

删除一个接口文件（文件 + 对应索引）。

**鉴权**：`require_admin`

**Path 参数**：

| 参数 | 说明 |
|------|------|
| `service_name` | 服务目录名 |
| `file_name` | 文件名 |

**成功响应 `200 OK`**：
```json
{ "ok": true }
```

**错误响应**：`404` — 文件不存在

---

### 14.3 DELETE `/api/admin/interfaces/service/{service_name}`

删除整个服务目录（目录 + 全部索引）。

**鉴权**：`require_admin`

**Path 参数**：`service_name` — 服务目录名

**成功响应 `200 OK`**：
```json
{ "ok": true }
```

**错误响应**：`404` — 服务目录不存在

---

## 十五、管理员 — 用户接口权限

### 15.1 GET `/api/admin/user-permissions/{user_id}`

查看指定用户的接口访问权限。

**鉴权**：`require_admin`

**Path 参数**：`user_id` — 目标用户 ID

**成功响应 `200 OK`**：权限列表

---

### 15.2 PUT `/api/admin/user-permissions/{user_id}`

批量设置用户的接口权限（授权 + 撤销）。

**鉴权**：`require_admin`

**Path 参数**：`user_id` — 目标用户 ID

**请求体**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `granted_ids` | list[int] | 否 | 授权的接口 ID 列表，默认 `[]` |
| `revoked_ids` | list[int] | 否 | 撤销的接口 ID 列表，默认 `[]` |

```json
{ "granted_ids": [1, 2, 3], "revoked_ids": [5] }
```

**成功响应 `200 OK`**：权限更新结果

---

### 15.3 PUT `/api/admin/user-permissions/{user_id}/grant-all`

一键授予用户所有接口的访问权限。

**鉴权**：`require_admin`

**Path 参数**：`user_id` — 目标用户 ID

**成功响应 `200 OK`**：
```json
{ "ok": true }
```

---

### 15.4 PUT `/api/admin/user-permissions/{user_id}/revoke-all`

一键撤销用户所有接口的访问权限。

**鉴权**：`require_admin`

**Path 参数**：`user_id` — 目标用户 ID

**成功响应 `200 OK`**：
```json
{ "ok": true }
```

---

### 15.5 GET `/api/admin/services/list`

列出所有已索引的服务名。

**鉴权**：`require_admin`

**成功响应 `200 OK`**：
```json
{ "services": ["safety_platform", "hr_system", "attendance_api"] }
```

---

### 15.6 GET `/api/admin/interfaces/all`

管理员查看所有接口（用于管理面板，无视用户权限限制）。

**鉴权**：`require_admin`

**成功响应 `200 OK`**：完整接口树

---

## 十六、接口配置存取

### 16.1 GET `/api/interface-configs`

读取接口配置文件（`project_documents/interface_configs.json`）。

**鉴权**：`verify_token`

**成功响应 `200 OK`**：

配置文件内容，不存在时返回空结构：
```json
{ "groups": [], "interfaces": [] }
```

---

### 16.2 POST `/api/interface-configs`

覆盖写入接口配置文件。

**鉴权**：`verify_token`

**请求体**：JSON 格式，完整配置内容（将原样写入文件）

**成功响应 `200 OK`**：
```json
{ "ok": true }
```

---

## 十七、嵌入式对话

> 嵌入式对话使用 `embed_token` 鉴权，不使用 JWT。

### 17.1 GET `/embed/chat`

提供网页嵌入版对话页面（HTML），供 iframe 加载。

**鉴权**：无

**成功响应 `200 OK`**：`Content-Type: text/html`，返回 `html_files/chat-embed.html`

**错误响应**：`404` — `嵌入页面尚未部署`

---

### 17.2 GET `/static/chat-ball.js`

提供聊天球 widget 脚本，外部前端通过 `<script src>` 引入。

**鉴权**：无

**成功响应 `200 OK`**：`Content-Type: application/javascript`，返回 `html_files/chat-ball.js`

**错误响应**：`404` — `chat-ball.js 尚未部署`

---

### 17.3 POST `/api/embed/chat`

嵌入式对话接口，支持两种调用模式：

- **单轮（聊天球）**：不传 `thread_id`，每次生成新 UUID，对话无上下文
- **多轮（网页嵌入）**：传入 `thread_id`，LangGraph 保留会话内上下文

**鉴权**：`embed_token`（请求体字段，非 JWT Header）

**请求体**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `message` | string | 是 | 用户输入内容 |
| `thread_id` | string \| null | 否 | 会话线程 ID；null 时自动生成 |
| `embed_token` | string | 是 | 嵌入鉴权 Token（环境变量 `EMBED_TOKEN`，默认 `hngd-embed-2024`） |

```json
{ "message": "公司差旅报销制度是怎样的？", "thread_id": null, "embed_token": "hngd-embed-2024" }
```

**成功响应 `200 OK`**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `response` | string | AI 回答内容 |
| `thread_id` | string | 实际使用的线程 ID（前端需回传以维持上下文） |

```json
{ "response": "根据知识库资料...", "thread_id": "embed-a1b2c3d4" }
```

**错误响应**：

| 状态码 | `detail` |
|--------|---------|
| 401 | `embed_token 无效` |
| 500 | `对话失败：{异常信息}` |

---

## 附录 A：请求模型汇总

| 模型名 | 字段 | 用途 |
|--------|------|------|
| `LoginRequest` | username, password, role | 登录 |
| `ChatRequest` | message, conversation_id?, mode | 流式对话 |
| `DocContentRequest` | requirements, outline, reference_context | 文档生成 |
| `UpdateDisplayNameRequest` | display_name | 修改显示名 |
| `UpdateAvatarRequest` | avatar | 修改头像 |
| `UpdatePasswordRequest` | old_password, new_password | 修改密码 |
| `CreateUserRequest` | username, password, display_name?, role | 创建用户 |
| `UpdateRoleRequest` | role | 修改角色 |
| `UpdateActiveRequest` | is_active | 启用/禁用用户 |
| `EmbedChatRequest` | message, thread_id?, embed_token | 嵌入对话 |
| `SwaggerImportRequest` | url, service_name? | URL导入接口 |
| `PermissionUpdateRequest` | granted_ids, revoked_ids | 权限更新 |
| `InterfaceTestRequest` | params, body?, base_url | 接口测试 |
| `DiscoverServicesRequest` | url | 探测服务 |
| `ImportSelectedTagsRequest` | url, service_name, selected_queries | 选择标签导入 |

## 附录 B：SSE 事件类型速查

| type | 必有字段 | 可选字段 | 说明 |
|------|---------|---------|------|
| `init` | conversation_id, title | — | 流开始 |
| `queued` | position | — | 排队等待 |
| `progress` | text | — | 实时进度 |
| `step` | text | — | 工具步骤 |
| `answer` | text, warning, agent | — | 最终回答 |
| `done` | — | — | 流结束 |
| `error` | text | — | 异常 |

## 附录 C：角色权限矩阵

| 功能 | visitor | user | admin |
|------|---------|------|-------|
| 登录 | ✅（但无使用权限） | ✅ | ✅ |
| 知识库对话 | ❌ | ✅ | ✅ |
| 数据统计 | ❌ | ✅ | ✅ |
| 文档编写 | ❌ | ✅ | ✅ |
| 系统接口浏览 | ❌ | ✅（仅已授权接口） | ✅（全部接口） |
| 接口测试 | ❌ | ✅（仅已授权接口） | ✅ |
| 用户管理 | ❌ | ❌ | ✅ |
| 审计日志 | ❌ | ❌ | ✅ |
| 知识库管理 | ❌ | ❌ | ✅ |
| 接口导入/删除 | ❌ | ❌ | ✅ |
| 用户接口权限 | ❌ | ❌ | ✅ |
| 嵌入式对话 | ✅（embed_token 鉴权） | ✅ | ✅ |
