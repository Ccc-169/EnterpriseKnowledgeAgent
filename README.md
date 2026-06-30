# HNGD 企业智能知识助手系统

> 基于 LangGraph Supervisor 多智能体架构的企业级 AI 平台，支持知识库问答、数据统计分析、文档智能生成、真实接口查询四大引擎，提供 HTML 静态前端 + FastAPI REST 后端的现代化架构。

---

## 🏗️ 系统架构

```
╔══════════════════════════════════════════════════════════════╗
║                        用户接入层                              ║
║   ┌──────────────────────────────────────────────────┐       ║
║   │          🌐 HTML 静态前端（html_files/）           │       ║
║   │  login · home · admin · setting · more-features  │       ║
║   │  config.js 统一配置 · chat-ball.js 嵌入组件      │       ║
║   └──────────────────────┬───────────────────────────┘       ║
╚═════════════════════════╪════════════════════════════════════╝
                           ▼ HTTP / SSE
╔══════════════════════════════════════════════════════════════╗
║              🔌 FastAPI 后端 (api.py · :28000)                 ║
║   JWT 认证 / 角色鉴权 / 审计日志 / SSE 流式推送 / 接口管理   ║
║                           │                                   ║
║        ┌──────────────────┴──────────────────┐               ║
║        ▼                                     ▼               ║
║  ┌─────────────┐                    ┌────────────────────┐   ║
║  │  agent.py   │                    │  doc / interface   │   ║
║  │  Supervisor │                    │  /api/doc/*        │   ║
║  │  + Router   │                    │  /api/system-*     │   ║
║  └──────┬──────┘                    └─────────┬──────────┘   ║
║         │                                     │               ║
║         │     ┌────────────────────────┐      │               ║
║         │     │  alarm_api.py (:28002) │      │               ║
║         │     │  安全监控平台示例后端  │      │               ║
║         │     └────────────────────────┘      │               ║
╚═════════╪═══════════════════════════════════╪═══════════════╝
          ▼                                   ▼
╔══════════════════════════════════════════════════════════════╗
║                   🤖 LangGraph 智能体层                        ║
║                                                              ║
║  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌────────┐ ║
║  │  rag_agent  │ │ data_agent  │ │  doc_agent  │ │api_agent│ ║
║  │ 知识库问答  │ │ 数据统计    │ │ 文档编写    │ │接口查询 │ ║
║  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘ └───┬────┘ ║
╚═════════╪═══════════════╪════════════════╪═══════════╪══════╝
          ▼               ▼                  ▼           ▼
╔══════════════════════════════════════════════════════════════╗
║                      🔧 工具 & 外部服务层                      ║
║                                                              ║
║   RAGFlow 知识库 API       代码执行沙箱 (:28001)              ║
║   rag_search               execute_data_query                ║
║   list_kb_documents        lookup_schema                     ║
║   search_knowledge_base    list_files / inspect_file          ║
║   api_agent 动态调用 data_interface/ 下 OpenAPI 接口          ║
║                                                              ║
║               规则引擎 (rules/rule_config.yaml)               ║
║          pre_generate · pre_execute · post_retrieve          ║
║                                                              ║
║                    SQLite 持久化层                             ║
║  users · conversations · messages · audit_logs · interfaces  ║
╚══════════════════════════════════════════════════════════════╝
```

---

## ✨ 功能特性

### 四大智能体

| 智能体 | 核心能力 | 入口 |
|--------|----------|------|
| **rag_agent** | 从企业 RAGFlow 知识库语义检索，回答制度/政策/文档类问题 | Router 自动路由 |
| **data_agent** | 自动识别 Excel/CSV 结构，生成 Python 代码在沙箱执行统计分析 | Router 自动路由 |
| **doc_agent** | 两步工作流（生成目录 → 确认 → 生成正文），参考知识库风格撰写文档 | 仿写模式直连 |
| **api_agent** | 从 `data_interface/` 加载 OpenAPI 3.0 规范，动态发现并调用真实 HTTP 接口获取实时数据 | Router 自动路由 |

### 系统能力

| 能力 | 说明 |
|------|------|
| **SSE 流式对话** | 后端实时推送 step/answer/done 事件，前端逐步显示推理过程；支持中途停止 |
| **多对话管理** | 支持创建/切换/删除多个独立会话，历史持久化 |
| **角色权限** | visitor / user / admin 三级，粒度到每个 Agent；接口级细粒度权限控制 |
| **规则引擎** | YAML 规则，覆盖代码安全、回答质量三个检查阶段 |
| **代码沙箱** | 独立 FastAPI 进程预热进程池，30s 超时，禁止文件写/网络访问 |
| **审计日志** | 所有用户操作（登录/对话/修改密码）均记录 |
| **数据模板** | `data_schema.json` 注册常用文件模板，命中时跳过文件探查减少两次工具调用 |
| **接口管理** | 通过 OpenAPI 规范自动发现、导入、测试真实数据接口；支持 URL/JSON/标签多种导入方式 |
| **嵌入对话** | `chat-ball.js` 嵌入式组件，可在外部页面接入对话能力 |
| **安全监控示例** | `alarm_api.py` 提供安全生产监控平台模拟后端，含报警/设备/工单等接口 |
| **一键启动** | `start.bat` / `start.sh` 自动初始化并启动全部服务 |

---

## 📁 项目结构

```
EnterpriseKnowledgeAgent/
├── html_files/               # 🌐 HTML 静态前端
│   ├── login-page.html       # 登录
│   ├── home-page.html        # 首页（对话 + 仿写）
│   ├── admin-page.html       # 管理后台
│   ├── setting-page.html     # 用户设置
│   ├── more-features-page.html
│   ├── interface_config.html # 接口配置管理
│   ├── chat-embed.html       # 嵌入式聊天页面
│   ├── implant_test.html     # 嵌入测试页
│   ├── config.js             # 前端统一配置（API 地址等）
│   ├── chat-ball.js          # 嵌入式对话浮球组件
│   └── style.md              # 样式说明
├── agents/                   # 🤖 智能体模块
│   ├── registry.py           # Agent 注册表（名称、权限、开关）
│   ├── rag_agent.py          # rag_search · list_kb_documents
│   ├── data_agent.py         # lookup_schema · list_files · inspect_file · execute_data_query
│   ├── doc_agent.py          # search_knowledge_base · generate_document_outline · generate_document_content
│   └── api_agent.py          # 动态加载 data_interface/ 下 OpenAPI 规范，调用真实 HTTP 接口
├── auth/                     # 🔐 认证授权
│   ├── auth_service.py       # 用户 CRUD · bcrypt 密码 · JWT
│   └── session.py            # Streamlit session 状态（兼容旧版）
├── audit/                    # 📝 审计日志
│   └── audit_service.py
├── core/                     # 🔧 基础设施
│   ├── database.py           # SQLite 初始化（幂等）
│   ├── config.py             # 环境变量加载
│   ├── chat_registry.py      # 对话注册与 LLM 状态管理
│   └── time_utils.py
├── rules/                    # 🛡️ 规则引擎
│   ├── rule_config.yaml      # YAML 规则配置（GEN_SAFETY / GEN_STYLE / GEN_QUALITY）
│   ├── engine.py             # 规则引擎核心
│   ├── loader.py             # 规则加载器
│   ├── models.py             # 规则数据模型
│   └── integration.py        # 与 Agent 流程的集成层
├── data/                     # 📊 数据层服务
│   ├── files/                # Excel / CSV 数据文件
│   ├── hngd.db               # SQLite 主数据库
│   ├── checkpoints.sqlite    # LangGraph 状态检查点
│   ├── dify_service.py       # Dify 知识库服务（已弃用，保留兼容）
│   ├── ragflow_service.py    # RAGFlow 知识库服务（当前使用）
│   ├── kb_search.py           # 知识库检索封装
│   ├── conversation_service.py # 对话管理服务
│   ├── document_service.py   # 文档生成服务
│   ├── interface_service.py  # 系统接口索引、导入与权限管理
│   ├── file_parser.py        # 文件解析
│   └── cache_service.py      # 缓存服务
├── pages/                    # Streamlit 页面（旧版，仍可用）
│   ├── index_page.py
│   ├── chat_page.py
│   ├── doc_page.py
│   └── admin_page.py
├── project_documents/
│   ├── data_schema.json      # 数据文件模板注册表
│   ├── interface_configs.json # 接口配置
│   ├── Dev_log.md            # 开发日志
│   └── *.md                  # 接口对照说明、功能点、架构图等文档
├── problem_document/         # 问题记录与排查文档
├── scripts/
│   ├── init_db.py            # 初始化 / 重置数据库
│   ├── import_swagger_specs.py # 从 URL 导入 OpenAPI 规范
│   ├── test_code_executor.py
│   ├── test_rag_retrieve.py
│   └── test_models.py        # 模型测试
├── api.py                    # FastAPI 后端主服务 (:28000)
├── agent.py                  # LangGraph Supervisor 编排入口
├── alarm_api.py              # 安全生产监控平台示例后端 (:28002)
├── code_executor.py          # 代码执行沙箱 (:28001)
├── app.py                    # Streamlit 入口（旧版兼容）
├── main.py                   # CLI 命令行入口
├── start.bat                 # Windows 一键启动脚本
├── start.sh                  # Linux/Mac 一键启动脚本
├── safety_platform_apis.json # 安全平台 OpenAPI 规范定义
├── requirements.txt
├── .env.example
└── CLAUDE.md                 # 开发规范
```

---

## 🚀 快速开始

### 1. 环境准备

```powershell
# 激活虚拟环境
.\venv\Scripts\Activate.ps1

# 安装依赖
pip install -r requirements.txt

# 初始化数据库
python scripts/init_db.py
```

### 2. 配置环境变量

复制并编辑 `.env`：

```env
# LLM（阿里千问 或 本地 Ollama）
QWEN_API_KEY=sk-xxxxxxxxxxxxxxxx

# RAGFlow 知识库（RAG 和文档功能必填）
RAGFLOW_API_KEY=ragflow-xxxxxxxxxxxxxxxx
RAGFLOW_DATASET_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
RAGFLOW_API_BASE=http://localhost/api/v1

# 代码沙箱
EXECUTOR_URL=http://localhost:28001/execute
EXECUTOR_POOL_SIZE=4

# 数据文件目录
DATA_DIR=./data/files

# 安全（上线前必改）
SECRET_KEY=change-this-to-a-random-32-char-string
ACCESS_TOKEN_EXPIRE_MINUTES=480

# 数据库
DB_PATH=./data/hngd.db

# 真实数据接口认证 Token（api_agent 调用需要认证的接口时使用）
REAL_API_TOKEN=your-jwt-token-here

# 嵌入式对话鉴权 Token
EMBED_TOKEN=hngd-embed-2024

# 可观测性（可选）
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=lsv2_pt_xxxx
LANGCHAIN_PROJECT=enterprise-knowledge-agent
```

### 3. 启动服务

**方式一：一键启动（推荐）**

```powershell
# Windows
start.bat

# Linux / Mac
./start.sh
```

脚本会自动：初始化数据库 → 启动代码沙箱(:28001) → 启动业务 API(:28000) → 启动静态文件服务(:28080) → 打开浏览器。

**方式二：手动启动**

```powershell
# 终端 1：代码执行沙箱（:28001）
uvicorn code_executor:app --port 28001

# 终端 2：FastAPI 后端（:28000）
uvicorn api:app --port 28000

# 终端 3：（可选）安全监控平台示例后端（:28002）
uvicorn alarm_api:app --port 28002

# 终端 4：静态文件服务（:28080）
python -m http.server 28080

# 浏览器打开 http://localhost:28080/html_files/login-page.html
```

> CLI 模式（无需沙箱和后端）：`python main.py`
>
> 前端 API 地址通过 `html_files/config.js` 统一配置，换部署环境只需改此文件。

---

## 🔌 API 接口一览

所有接口均需 `Authorization: Bearer <token>` 请求头（登录和嵌入接口除外）。

#### 认证 & 用户

| 路由 | 方法 | 说明 |
|------|------|------|
| `/api/auth/login` | POST | 用户名密码登录，返回 JWT token |
| `/api/auth/logout` | POST | 登出，写审计日志 |
| `/api/user/display-name` | PUT | 修改显示名称 |
| `/api/user/avatar` | PUT | 修改头像 |
| `/api/user/password` | PUT | 修改登录密码（需验证旧密码） |

#### 对话 & 文档

| 路由 | 方法 | 说明 |
|------|------|------|
| `/api/conversations` | GET | 获取当前用户的对话列表 |
| `/api/conversations` | POST | 新建对话 |
| `/api/conversations/{id}` | DELETE | 删除对话 |
| `/api/conversations/{id}/messages` | GET | 获取对话消息历史 |
| `/api/chat/stream` | POST | **SSE 流式对话**（init/step/answer/done/error 事件） |
| `/api/chat/stop` | POST | 中止正在进行的流式对话 |
| `/api/doc/generate-outline` | POST | 生成文档目录（支持文件附件上传） |
| `/api/doc/generate-content` | POST | 根据目录生成完整文档正文 |

#### 系统接口管理

| 路由 | 方法 | 说明 |
|------|------|------|
| `/api/system-interfaces/tree` | GET | 接口树形列表 |
| `/api/system-interfaces/{id}/detail` | GET | 接口详情 |
| `/api/system-interfaces/{id}/test` | POST | 测试接口调用 |
| `/api/interface-configs` | GET | 接口配置列表 |
| `/api/interface-configs` | POST | 保存接口配置 |

#### 管理后台（admin）

| 路由 | 方法 | 说明 |
|------|------|------|
| `/api/admin/stats` | GET | 仪表盘统计数据 |
| `/api/admin/users` | GET | 获取用户列表 |
| `/api/admin/users` | POST | 创建用户 |
| `/api/admin/users/{id}/role` | PUT | 修改用户角色 |
| `/api/admin/users/{id}/active` | PUT | 启用/禁用用户 |
| `/api/admin/users/{id}` | DELETE | 删除用户 |
| `/api/admin/logs` | GET | 查询审计日志 |
| `/api/admin/kb/datasets` | GET | 知识库列表 |
| `/api/admin/kb/datasets/{id}/documents` | GET | 知识库文档列表 |
| `/api/admin/data-files` | GET | 数据文件列表 |
| `/api/admin/interfaces/discover-services` | POST | 从 URL 发现 OpenAPI 服务 |
| `/api/admin/interfaces/import-selected-tags` | POST | 按标签批量导入接口 |
| `/api/admin/interfaces/import-from-url` | POST | 从 URL 导入 OpenAPI 规范 |
| `/api/admin/interfaces/import-from-json` | POST | 从 JSON 文件导入 |
| `/api/admin/interfaces/{id}` | DELETE | 删除单个接口 |
| `/api/admin/interfaces/file/{service}/{file}` | DELETE | 删除接口文件 |
| `/api/admin/interfaces/service/{service}` | DELETE | 删除整个服务 |
| `/api/admin/services/list` | GET | 已注册服务列表 |
| `/api/admin/interfaces/all` | GET | 所有接口列表 |
| `/api/admin/user-permissions/{user_id}` | GET | 用户接口权限 |
| `/api/admin/user-permissions/{user_id}` | PUT | 修改用户接口权限 |
| `/api/admin/user-permissions/{user_id}/grant-all` | PUT | 授予用户所有接口权限 |
| `/api/admin/user-permissions/{user_id}/revoke-all` | PUT | 撤销用户所有接口权限 |

#### 嵌入式对话

| 路由 | 方法 | 说明 |
|------|------|------|
| `/embed/chat` | GET | 嵌入式聊天页面 |
| `/api/embed/chat` | POST | 嵌入式对话接口（需 `EMBED_TOKEN`） |
| `/static/chat-ball.js` | GET | 嵌入式浮球组件 JS |

### SSE 流式事件格式

```
data: {"type": "init",   "conversation_id": 1, "title": "..."}
data: {"type": "step",   "text": "调用工具 rag_search..."}
data: {"type": "answer", "text": "回答内容", "warning": false}
data: {"type": "done"}
data: {"type": "error",  "text": "错误描述"}
```

---

## 🛡️ 规则引擎

规则配置在 `rules/rule_config.yaml`，无需修改代码即可调整安全策略。

| 阶段 | 说明 | 触发时机 |
|------|------|---------|
| `pre_generate` | 用户输入检测（注入防护） | 发送给 LLM 前 |
| `pre_execute` | 生成代码安全检查 | 沙箱执行前 |
| `post_retrieve` | 回答质量检查 | LLM 返回后 |

`CRITICAL` 级别规则触发 `RuleViolationError` 阻断执行；`WARNING` 级别仅附加提示，不阻断。

---

## 👥 角色权限

| 功能 | visitor | user | admin |
|------|:-------:|:----:|:-----:|
| 登录系统 | ✅ | ✅ | ✅ |
| 知识库问答 | ❌ | ✅ | ✅ |
| 数据统计分析 | ❌ | ✅ | ✅ |
| 文档仿写 | ❌ | ✅ | ✅ |
| 真实接口查询 | ❌ | ✅ | ✅ |
| 查看自己的对话记录 | ❌ | ✅ | ✅ |
| 修改个人密码/名称/头像 | ❌ | ✅ | ✅ |
| 管理后台 | ❌ | ❌ | ✅ |
| 用户管理（增删改角色）| ❌ | ❌ | ✅ |
| 查看审计日志 | ❌ | ❌ | ✅ |
| 知识库管理 | ❌ | ❌ | ✅ |
| 接口导入与管理 | ❌ | ❌ | ✅ |
| 用户接口权限分配 | ❌ | ❌ | ✅ |

---

## 🔑 默认账号

> **上线前必须修改所有默认密码！**

| 用户名 | 默认密码 | 角色 |
|--------|----------|------|
| admin | Admin@123 | 管理员 |
| user01 | User@123 | 普通用户 |
| visitor | Visitor@123 | 访客 |

---

## 🧩 扩展开发

### 给现有 Agent 添加工具

1. 在 agent 文件中定义 `@tool` 函数
2. 加入 `create_react_agent(tools=[...])` 的 tools 列表
3. 更新 agent prompt 说明工具用途和调用时机

### 添加新 Agent

1. 创建 `agents/new_agent.py`，实现 `create_new_agent(llm)`
2. 在 `agents/registry.py` 的 `AGENT_REGISTRY` 中注册
3. 在 `agent.py` 中实例化
4. 若需 Router 自动路由：加入 `create_supervisor(agents=[...])`；若直连：从页面调用 `chat_direct("new_agent", ...)`

### 修改安全规则

直接编辑 `rules/rule_config.yaml`，`applies_to` 字段可将规则限定到特定 Agent 或用 `"*"` 全局生效。

---

## ❓ 常见问题

**沙箱无法连接？**  
确认 `uvicorn code_executor:app --port 28001` 已启动；检查 `EXECUTOR_URL` 配置与端口是否一致。

**LLM 无响应？**  
检查 `QWEN_API_KEY` 是否有效；查看终端报错是否为余额不足或速率限制。

**忘记 admin 密码？**  
```python
from auth.auth_service import hash_password
from core.database import get_db
db = get_db()
db.execute("UPDATE users SET password_hash=? WHERE username='admin'",
           (hash_password("NewPass@123"),))
db.commit()
```

**切换 LLM 模型？**  
编辑 `agent.py` 中 `ChatOpenAI` 的 `model` 和 `base_url` 参数。本地 Ollama 无需 API Key。

---

## 📄 许可证

内部项目，仅供企业使用。
