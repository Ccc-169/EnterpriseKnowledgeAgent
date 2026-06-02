# HNGD 企业智能知识助手系统

> 基于 LangGraph Supervisor 多智能体架构的企业级 AI 平台，支持知识库问答、数据统计分析、文档智能生成三大引擎，提供 HTML 静态前端 + FastAPI REST 后端的现代化架构。

---

## 🏗️ 系统架构

```
╔══════════════════════════════════════════════════════════════╗
║                        用户接入层                              ║
║   ┌──────────────────────────────────────────────────┐       ║
║   │          🌐 HTML 静态前端（html_files/）           │       ║
║   │  login · home · admin · setting · more-features  │       ║
║   └──────────────────────┬───────────────────────────┘       ║
╚═════════════════════════╪════════════════════════════════════╝
                           ▼ HTTP / SSE
╔══════════════════════════════════════════════════════════════╗
║                   🔌 FastAPI 后端 (api.py · :8000)            ║
║   JWT 认证 / 角色鉴权 / 审计日志 / SSE 流式推送              ║
║                           │                                   ║
║        ┌──────────────────┴──────────────────┐               ║
║        ▼                                     ▼               ║
║  ┌─────────────┐                    ┌────────────────────┐   ║
║  │  agent.py   │                    │  doc 接口          │   ║
║  │  Router     │                    │  /api/doc/*        │   ║
║  │  Supervisor │                    └─────────┬──────────┘   ║
║  └──────┬──────┘                              │              ║
╚═════════╪═══════════════════════════════════╪═══════════════╝
          ▼                                   ▼
╔══════════════════════════════════════════════════════════════╗
║                   🤖 LangGraph 智能体层                        ║
║                                                              ║
║   ┌───────────────┐  ┌───────────────┐  ┌───────────────┐   ║
║   │  rag_agent    │  │  data_agent   │  │  doc_agent    │   ║
║   │  知识库问答   │  │  数据统计     │  │  文档编写     │   ║
║   └───────┬───────┘  └───────┬───────┘  └───────┬───────┘   ║
╚═══════════╪══════════════════╪══════════════════╪═══════════╝
            ▼                  ▼                  ▼
╔══════════════════════════════════════════════════════════════╗
║                      🔧 工具 & 外部服务层                      ║
║                                                              ║
║   Dify 知识库 API         代码执行沙箱 (:8001)                 ║
║   rag_search              execute_data_query                  ║
║   list_kb_documents       lookup_schema                       ║
║   search_knowledge_base   list_files / inspect_file          ║
║                                                              ║
║               规则引擎 (rules/rule_config.yaml)               ║
║          pre_generate · pre_execute · post_retrieve          ║
║                                                              ║
║                    SQLite 持久化层                             ║
║         users · conversations · messages · audit_logs        ║
╚══════════════════════════════════════════════════════════════╝
```

---

## ✨ 功能特性

### 三大智能体

| 智能体 | 核心能力 | 入口 |
|--------|----------|------|
| **rag_agent** | 从企业 Dify 知识库语义检索，回答制度/政策/文档类问题 | Router 自动路由 |
| **data_agent** | 自动识别 Excel/CSV 结构，生成 Python 代码在沙箱执行统计分析 | Router 自动路由 |
| **doc_agent** | 两步工作流（生成目录 → 确认 → 生成正文），参考知识库风格撰写文档 | 仿写模式直连 |

### 系统能力

| 能力 | 说明 |
|------|------|
| **SSE 流式对话** | 后端实时推送 step/answer/done 事件，前端逐步显示推理过程 |
| **多对话管理** | 支持创建/切换/删除多个独立会话，历史持久化 |
| **角色权限** | visitor / user / admin 三级，粒度到每个 Agent |
| **规则引擎** | 17 条 YAML 规则，覆盖代码安全、回答质量三个检查阶段 |
| **代码沙箱** | 独立 FastAPI 进程预热进程池，30s 超时，禁止文件写/网络访问 |
| **审计日志** | 所有用户操作（登录/对话/修改密码）均记录 |
| **数据模板** | `data_schema.json` 注册常用文件模板，命中时跳过文件探查减少两次工具调用 |

---

## 📁 项目结构

```
EnterpriseKnowledgeAgent/
├── html_files/               # 🌐 HTML 静态前端
│   ├── login-page.html       # 登录
│   ├── home-page.html        # 首页（对话 + 仿写）
│   ├── admin-page.html       # 管理后台
│   ├── setting-page.html     # 用户设置
│   └── more-features-page.html
├── agents/                   # 🤖 智能体模块
│   ├── registry.py           # Agent 注册表（名称、权限、开关）
│   ├── rag_agent.py          # rag_search · list_kb_documents
│   ├── data_agent.py         # lookup_schema · list_files · inspect_file · execute_data_query
│   └── doc_agent.py          # search_knowledge_base · generate_document_outline · generate_document_content · improve_document_outline
├── auth/                     # 🔐 认证授权
│   ├── auth_service.py       # 用户 CRUD · bcrypt 密码 · JWT
│   └── session.py            # Streamlit session 状态（兼容旧版）
├── audit/                    # 📝 审计日志
│   └── audit_service.py
├── core/                     # 🔧 基础设施
│   ├── database.py           # SQLite 初始化（幂等）
│   ├── config.py             # 环境变量加载
│   └── time_utils.py
├── rules/                    # 🛡️ 规则引擎
│   └── rule_config.yaml      # 17 条 YAML 规则（GEN_SAFETY / GEN_STYLE / GEN_QUALITY）
├── pages/                    # Streamlit 页面（旧版，仍可用）
│   ├── index_page.py
│   ├── chat_page.py
│   ├── doc_page.py
│   └── admin_page.py
├── data/
│   ├── files/                # Excel / CSV 数据文件
│   ├── hngd.db               # SQLite 主数据库
│   └── checkpoints.sqlite    # LangGraph 状态检查点
├── project_documents/
│   └── data_schema.json      # 数据文件模板注册表
├── scripts/
│   ├── init_db.py            # 初始化 / 重置数据库
│   ├── test_code_executor.py
│   └── test_rag_retrieve.py
├── api.py                    # FastAPI 后端主服务 (:8000)
├── agent.py                  # LangGraph Supervisor 编排入口
├── app.py                    # Streamlit 入口（旧版兼容）
├── code_executor.py          # 代码执行沙箱 (:8001)
├── main.py                   # CLI 命令行入口
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
# LLM（阿里千问，必填）
QWEN_API_KEY=sk-xxxxxxxxxxxxxxxx

# Dify 知识库（RAG 和文档功能必填）
DIFY_DATASET_KEY=dataset-xxxxxxxxxxxxxxxx
DIFY_KB_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
DIFY_API_BASE=https://api.dify.ai/v1

# 代码沙箱
EXECUTOR_URL=http://localhost:8001/execute
EXECUTOR_POOL_SIZE=4

# 数据文件目录
DATA_DIR=./data/files

# 安全（上线前必改）
SECRET_KEY=change-this-to-a-random-32-char-string
ACCESS_TOKEN_EXPIRE_MINUTES=480

# 数据库
DB_PATH=./data/hngd.db

# 可观测性（可选）
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=lsv2_pt_xxxx
LANGCHAIN_PROJECT=hngd-backend
```

### 3. 启动三个服务

```powershell
# 终端 1：代码执行沙箱（:8001）
uvicorn code_executor:app --port 8001

# 终端 2：FastAPI 后端（:8000）
uvicorn api:app --port 8000

# 用浏览器打开 html_files/login-page.html 即可使用
```

> CLI 模式（无需沙箱和后端）：`python main.py`

---

## 🔌 API 接口一览

所有接口均需 `Authorization: Bearer <token>` 请求头（登录接口除外）。

| 路由 | 方法 | 说明 |
|------|------|------|
| `/api/auth/login` | POST | 用户名密码登录，返回 JWT token |
| `/api/auth/logout` | POST | 登出，写审计日志 |
| `/api/conversations` | GET | 获取当前用户的对话列表 |
| `/api/conversations` | POST | 新建对话 |
| `/api/conversations/{id}` | DELETE | 删除对话 |
| `/api/conversations/{id}/messages` | GET | 获取对话消息历史 |
| `/api/chat/stream` | POST | **SSE 流式对话**（返回 init/step/answer/done/error 事件） |
| `/api/user/display-name` | PUT | 修改显示名称 |
| `/api/user/password` | PUT | 修改登录密码（需验证旧密码） |
| `/api/doc/generate-outline` | POST | 生成文档目录（支持文件附件上传） |
| `/api/doc/generate-content` | POST | 根据目录生成完整文档正文 |
| `/api/admin/users` | GET | 获取用户列表（admin） |
| `/api/admin/users` | POST | 创建用户（admin） |
| `/api/admin/users/{id}/role` | PUT | 修改用户角色（admin） |
| `/api/admin/users/{id}/toggle` | PUT | 启用/禁用用户（admin） |
| `/api/admin/audit-logs` | GET | 查询审计日志（admin） |
| `/api/admin/kb/datasets` | GET | 知识库列表（admin） |
| `/api/admin/kb/documents` | GET | 知识库文档列表（admin） |

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
| 查看自己的对话记录 | ❌ | ✅ | ✅ |
| 修改个人密码/名称 | ❌ | ✅ | ✅ |
| 管理后台 | ❌ | ❌ | ✅ |
| 用户管理（增删改角色）| ❌ | ❌ | ✅ |
| 查看审计日志 | ❌ | ❌ | ✅ |
| 知识库管理 | ❌ | ❌ | ✅ |

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
确认 `uvicorn code_executor:app --port 8001` 已启动；检查 `EXECUTOR_URL` 配置与端口是否一致。

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
