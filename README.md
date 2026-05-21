# 企业知识库智能体系统 (HNGD-Backend)

> 基于 LangGraph Supervisor 模式的企业级智能助手，支持文档检索问答与数据统计分析双引擎驱动。

---

## 📊 项目架构图

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                              用户交互层                                        ║
║   ┌──────────────────────┐              ┌──────────────────────┐             ║
║   │  🌐 Streamlit Web UI │              │  💻 命令行交互入口    │             ║
║   │     (app.py)         │              │    (main.py)         │             ║
║   └──────────┬───────────┘              └──────────┬───────────┘             ║
║              └─────────────────┬──────────────────┘                           ║
║                                ▼                                             ║
║                   ┌────────────────────────┐                                 ║
║                   │   📞 核心调度层        │                                 ║
║                   │    (agent.py)         │                                 ║
║                   └───────────┬──────────┘                                 ║
╚══════════════════════════════╪══════════════════════════════════════════════╝
                                 ▼
╔══════════════════════════════════════════════════════════════════════════════╗
║                         🎯 LangGraph Supervisor 调度中心                      ║
║                                                                               ║
║                    ┌──────────────────────────────┐                           ║
║                    │  🧭 Router 智能路由器         │                          ║
║                    │  (问题分类 + 任务分发)        │                           ║
║                    └────────────┬─────────────────┘                           ║
║                                 │                                             ║
║              ┌──────────────────┴──────────────────┐                          ║
║              ▼                                     ▼                          ║
║   ┌──────────────────────┐             ┌──────────────────────┐               ║
║   │  📚 rag_agent        │             │  📈 data_agent        │             ║
║   │  文档检索智能体       │             │  数据分析智能体        │              ║
║   │  (rag_agent.py)      │             │  (data_agent.py)      │              ║
║   └──────────┬───────────┘             └──────────┬───────────┘              ║
╚══════════════╪══════════════════════════╪════════════════════════════════════╝
               ▼                             ▼
╔══════════════════════════════════════════════════════════════════════════════╗
║                                   🔧 工具执行层                               ║
║                                                                               ║
║  rag_agent 工具集:                 data_agent 工具集:                         ║
║  ┌──────────────────────┐          ┌──────────────────────┐                  ║
║  │ 🔍 rag_search()      │          │ 📂 list_files()      │                  ║
║  │  Dify知识库语义检索   │          │  扫描数据文件列表      │                  ║
║  ├──────────────────────┤          ├──────────────────────┤                  ║
║  │ 📄 list_kb_documents()│         │ 🔎 inspect_file()    │                  ║
║  │  查询知识库文档列表    │          │  查看文件列名和结构    │                  ║
║  └──────────────────────┘          ├──────────────────────┤                  ║
║                                     │ 🚀 execute_data_query()│                 ║
║                                     │  生成并执行统计代码    │                  ║
║                                     └──────────┬───────────┘                  ║
╚═════════════════════════════════════╪════════════════════════════════════════╝
                                        ▼
╔══════════════════════════════════════════════════════════════════════════════╗
║                                 🗄️ 外部服务层                                  ║
║                                                                               ║
║  ┌────────────────────────┐      ┌────────────────────────┐                   ║
║  │  🌐 Dify 知识库 API    │      │  🔒 代码执行沙箱       │                   ║
║  │  (文档检索服务)         │      │  (code_executor.py)   │                   ║
║  │  - 混合检索            │      │  - FastAPI 服务        │                   ║
║  │  - 语义+关键词         │      │  - 30秒超时限制        │                   ║
║  │  - 重排序             │      │  - 安全隔离执行        │                   ║
║  └────────────────────────┘      └──────────┬───────────┘                   ║
║                                             │                               ║
║                                             ▼                               ║
║                                  ┌──────────────────┐                        ║
║                                  │  📊 Excel/CSV    │                        ║
║                                  │  企业数据文件     │                        ║
║                                  └──────────────────┘                        ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

---

## 🎯 项目概述

HNGD-Backend 是一个面向企业的智能知识助手系统，采用 **LangGraph Supervisor 多智能体架构**，能够：

- **智能路由**：自动识别用户意图，将问题精准分发给专精的智能体
- **文档问答**：从企业知识库检索相关文档，回答制度、政策、规定等问题
- **数据分析**：自动生成 Python 代码，对 Excel/CSV 数据进行统计分析和可视化
- **多轮对话**：支持上下文记忆，实现连贯的智能对话体验
- **用户管理**：完善的用户认证、角色权限控制、操作审计
- **对话管理**：支持多对话记录、持久化存储、自动标题生成

### 核心优势

| 优势 | 说明 |
|------|------|
| 🎯 精准路由 | Router 智能判断问题类型，自动选择最合适的智能体 |
| 🔒 安全可靠 | 代码沙箱隔离执行，防止恶意代码风险 |
| 🧠 上下文记忆 | 支持多轮对话，记住前文内容 |
| 📊 数据驱动 | 自动生成并执行数据分析代码，无需手动编写 |
| 🌐 双端支持 | 同时提供 Web 界面和命令行两种交互方式 |
| 👥 多角色管理 | 完善的用户认证、角色权限控制、操作审计 |
| 💬 对话管理 | 多对话记录、持久化存储、自动标题生成 |
| ⚙️ 用户自助 | 用户可自助修改密码和显示名称 |

---

## ✨ 功能特性

### 1. 文档检索问答 (RAG)

| 能力 | 说明 | 示例问题 |
|------|------|---------|
| 知识库检索 | 从企业知识库检索相关文档片段 | "合同中关于违约责任的条款是什么？" |
| 文档查询 | 查看知识库中有哪些文档 | "知识库里有哪些文件？" |
| 内容总结 | 对文档核心内容进行总结 | "总结一下员工手册的主要内容" |
| 内容仿写 | 基于文档风格仿写新内容 | "参考这份报告，写一份季度总结" |

### 2. 数据统计分析

| 能力 | 说明 | 示例问题 |
|------|------|---------|
| 基础统计 | 求和、平均值、最大值、最小值等 | "1月研发中心的平均工资是多少？" |
| 排名分析 | 按指定维度进行排名 | "哪个月份的迟到次数最多？" |
| 条件筛选 | 按条件筛选数据 | "列出工资大于10000的员工" |
| 跨月对比 | 多个月份数据对比分析 | "对比Q1和Q2的考勤情况" |
| 趋势分析 | 数据变化趋势分析 | "分析近半年离职率趋势" |

### 3. 对话记录管理

| 能力 | 说明 |
|------|------|
| 多对话管理 | 支持创建多个独立对话，每个对话有独立的上下文记忆 |
| 对话列表 | 侧边栏显示所有对话记录，支持切换、删除 |
| 自动标题 | 根据首条消息自动生成对话标题 |
| 持久化存储 | 对话记录和消息历史保存在数据库，随时可查看 |

### 4. 用户设置

| 能力 | 说明 |
|------|------|
| 基本信息查看 | 查看用户名、角色等基本信息 |
| 修改显示名称 | 自定义侧边栏显示的名称 |
| 修改密码 | 安全地修改登录密码（需验证当前密码） |

### 5. 知识库管理（管理员）

| 能力 | 说明 |
|------|------|
| 知识库列表 | 查看所有知识库，包括文档数量、总字数等信息 |
| 文档列表 | 查看每个知识库中的文档列表，包括索引状态、命中次数等 |
| 分页浏览 | 支持知识库列表和文档列表的分页浏览 |

---

## 📁 项目结构

```
HNGD-backend/
├── agent.py                  # 🎯 核心调度层：Router + Supervisor 创建和调用逻辑
├── agents/                   # 🤖 智能体模块
│   ├── __init__.py          # 包初始化文件
│   ├── rag_agent.py         # 文档检索智能体（RAG）
│   └── data_agent.py        # 数据分析智能体
├── auth/                     # 🔐 认证授权模块
│   ├── __init__.py          # 包初始化文件
│   ├── auth_service.py      # 用户认证、密码管理、权限控制
│   └── session.py           # Streamlit session 状态管理
├── audit/                    # 📝 审计日志模块
│   ├── __init__.py          # 包初始化文件
│   └── audit_service.py     # 操作日志记录和查询
├── core/                     # 🔧 核心基础设施
│   ├── __init__.py          # 包初始化文件
│   └── database.py          # SQLite 数据库连接和初始化
├── data/                     # 💾 数据服务模块
│   ├── conversation_service.py  # 对话记录 CRUD 操作
│   ├── dify_service.py      # Dify API 封装（知识库管理）
│   └── hngd.db              # SQLite 数据库文件
├── pages/                    # 🌐 Streamlit 页面
│   ├── __init__.py          # 包初始化文件
│   ├── admin_page.py        # 管理员页面（用户管理、审计日志、知识库管理）
│   └── chat_page.py         # 主对话页面（支持多对话记录、用户设置）
├── code_executor.py          # 🔒 代码执行沙箱服务（FastAPI）
├── app.py                    # 🌐 Streamlit Web 交互界面入口
├── main.py                   # 💻 命令行交互入口
├── requirements.txt          # Python 依赖清单
├── .env                      # 环境变量配置（需自行创建）
├── .env.example              # 环境变量配置模板
└── venv/                     # Python 虚拟环境
```

---

## 🚀 快速开始

### 1. 环境准备

```bash
# 克隆项目（如果尚未获取）
cd HNGD-backend

# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
.\venv\Scripts\Activate.ps1    # Windows PowerShell
# source venv/bin/activate     # macOS/Linux

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置环境变量

创建 `.env` 文件，填入以下配置：

```env
# LLM 配置（二选一）

# 选项1：使用本地 Ollama (默认)
# 需先安装 Ollama 并拉取模型：ollama pull deepseek-r1:32b
# 无需配置 API Key

# 选项2：使用阿里千问 API
# QWEN_API_KEY=sk-xxxxxxxxxxxxxxxx
# 并修改 agent.py 中的 model 和 base_url 配置

# Dify 知识库配置（文档检索功能必需）
DIFY_DATASET_KEY=dataset-xxxxxxxxxxxxxxxx
DIFY_KB_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
# Dify API 地址（可选，默认为 https://api.dify.ai/v1，自建实例请修改为对应地址）
DIFY_API_BASE=https://api.dify.ai/v1

# 代码执行沙箱地址
EXECUTOR_URL=http://localhost:8001/execute

# 数据文件目录（Excel/CSV 所在路径）
DATA_DIR=D:\path\to\your\data
```

### 3. 启动服务

**方式一：完整启动（推荐）**

打开两个终端窗口：

```bash
# 终端1：启动代码执行沙箱
uvicorn code_executor:app --port 8001

# 终端2：启动 Web 界面
streamlit run app.py
```

**方式二：命令行模式**

```bash
python main.py
```

---

## 🔧 核心模块详解

### agent.py — 核心调度层

负责创建 Supervisor 和智能体，协调整个系统的运行流程。

| 组件 | 说明 |
|------|------|
| `ChatOpenAI` | LLM 接口，支持 Ollama 本地模型和阿里千问 API |
| `create_supervisor` | 创建 Supervisor，配置 Router 的 prompt 和子智能体 |
| `rag_agent` | 文档检索智能体，处理知识库相关问题 |
| `data_agent` | 数据分析智能体，处理数据统计相关问题 |
| `chat()` | 入口函数，处理用户输入，返回答案和推理步骤 |
| `MemorySaver` | LangGraph 内存检查点，支持多轮对话上下文记忆 |

**Router 路由规则：**

```
用户问题
    ↓
Router 判断类型
    ├─ 文档类问题 → 转发给 rag_agent
    │   - 公司制度、规定、政策
    │   - 员工手册相关内容
    │   - 知识库文档查询
    │   - 内容总结和仿写
    │
    └─ 数据类问题 → 转发给 data_agent
        - 统计、排名、汇总、计算
        - 考勤数据分析
        - Excel 文件读取和分析
        - 跨月数据对比
```

### agents/rag_agent.py — 文档检索智能体

专注于企业知识库的文档检索和内容理解。

| 工具 | 功能 | 调用时机 |
|------|------|---------|
| `rag_search()` | 调用 Dify 知识库 API 进行混合检索（语义+关键词），支持重排序 | 用户询问文档内容时 |
| `list_kb_documents()` | 查询 Dify 知识库中有哪些文档 | 用户询问"有什么文件"时 |

**RAG 检索流程：**
```
用户提问
    ↓
rag_search() 调用 Dify API
    ↓
混合检索（语义检索 + 关键词检索）
    ↓
重排序（Reranking）
    ↓
返回 Top 5 相关文档片段
    ↓
基于文档内容回答用户问题
```

### agents/data_agent.py — 数据分析智能体

专注于 Excel/CSV 数据的统计分析和代码生成。

| 工具 | 功能 | 调用时机 |
|------|------|---------|
| `list_files()` | 扫描 DATA_DIR 下的 Excel/CSV 文件 | 任何数据分析任务开始前 |
| `inspect_file()` | 读取文件列名、数据类型、样本数据 | `list_files` 之后，生成代码之前 |
| `execute_data_query()` | LLM 生成 Python 代码 → 发送沙箱执行 → 返回结果 | 获取文件结构后 |

**数据分析流程：**
```
用户提问（如："1月平均工资是多少？"）
    ↓
1. list_files() → 获取所有数据文件
    ↓
2. inspect_file() → 查看文件结构，获取真实列名
    ↓
3. LLM 根据列名生成 Python 统计代码
    ↓
4. execute_data_query() → 发送代码到沙箱执行
    ↓
5. 返回统计结果
    ↓
整理并返回自然语言答案
```

### code_executor.py — 代码执行沙箱

提供安全的 Python 代码执行环境，防止恶意代码风险。

**安全机制：**
- 仅允许读取指定 `DATA_PATH` 的文件，LLM 不能自行指定文件路径
- 30 秒执行超时限制，防止无限循环
- 使用临时文件执行，执行完毕后自动清理
- 捕获标准输出和错误输出，返回执行状态

**API 接口：**
- `POST /execute`
- 请求体：`{"code": "Python代码字符串", "data_path": "数据文件路径"}`
- 响应：`{"status": "success/error", "output": "执行输出", "error": "错误信息"}`

### app.py — Streamlit Web 界面

提供友好的 Web 交互界面。

**功能特性：**
- 实时对话界面，支持消息历史显示
- 展开式推理过程查看（点击可查看工具调用过程）
- 自动管理对话线程 ID，支持多轮对话
- 响应式布局，支持宽屏显示
- 用户认证和角色权限控制
- 用户设置界面（修改密码、显示名称）

### main.py — 命令行入口

提供简单的命令行交互方式，适合快速测试和后段运行。

### auth/auth_service.py — 认证授权服务

负责用户认证、密码管理和权限控制。

| 函数 | 功能 |
|------|------|
| `hash_password()` | bcrypt 哈希密码 |
| `verify_password()` | 验证密码是否匹配 |
| `authenticate_user()` | 用户名密码认证，返回用户信息 |
| `create_user()` | 创建新用户（管理员功能） |
| `list_users()` | 获取所有用户列表（管理员功能） |
| `update_user_role()` | 修改用户角色（管理员功能） |
| `toggle_user_active()` | 启用/禁用用户（管理员功能） |
| `update_password()` | 修改用户密码（需验证当前密码） |
| `update_display_name()` | 修改用户显示名称 |

### auth/session.py — Session 状态管理

管理 Streamlit session_state 中的用户会话。

| 函数 | 功能 |
|------|------|
| `is_logged_in()` | 检查当前 session 是否已登录 |
| `get_current_user()` | 获取当前用户信息 |
| `login_session()` | 将用户信息写入 session_state |
| `logout_session()` | 清空 session_state 中的用户信息 |
| `require_login()` | 未登录则显示提示并 st.stop() |
| `require_role()` | 角色不在允许列表中则显示无权限提示并 st.stop() |

### audit/audit_service.py — 审计日志服务

记录用户操作日志，支持查询和统计。

| 函数 | 功能 |
|------|------|
| `log_event()` | 记录操作日志（用户ID、用户名、操作类型、状态等） |
| `get_logs()` | 查询日志记录（支持分页、过滤） |
| `get_summary_stats()` | 获取审计日志统计信息 |

### core/database.py — 数据库核心

管理 SQLite 数据库连接和初始化。

| 函数 | 功能 |
|------|------|
| `get_db()` | 获取数据库连接（自动创建表结构） |
| `init_db()` | 初始化数据库表结构 |

**数据库表结构：**
- `users` - 用户表（id, username, password_hash, display_name, role, is_active, created_at）
- `conversations` - 对话表（id, user_id, title, created_at, updated_at）
- `messages` - 消息表（id, conversation_id, role, content, steps_log, agent_used, timestamp）
- `audit_logs` - 审计日志表（id, user_id, username, action, agent_used, question, status, timestamp）

### data/conversation_service.py — 对话记录服务

实现对话记录的 CRUD 操作。

| 函数 | 功能 |
|------|------|
| `create_conversation()` | 创建新对话 |
| `get_conversations()` | 获取用户的所有对话列表 |
| `get_conversation()` | 获取指定对话详情 |
| `update_conversation_title()` | 更新对话标题 |
| `delete_conversation()` | 删除对话（同时删除相关消息） |
| `save_message()` | 保存消息到数据库 |
| `get_messages()` | 获取对话的所有消息 |
| `update_conversation_timestamp()` | 更新对话时间戳 |
| `generate_title_from_message()` | 根据消息内容生成对话标题 |

### data/dify_service.py — Dify API 服务

封装 Dify 知识库 API 调用，支持分页和错误处理。

| 函数 | 功能 |
|------|------|
| `list_datasets()` | 获取知识库列表（支持分页） |
| `list_documents()` | 获取指定知识库内的文档列表（支持分页） |

### pages/chat_page.py — 主对话页面

渲染主对话界面，支持多对话记录管理。

**功能特性：**
- 侧边栏显示对话列表（支持新建/切换/删除）
- 主区域显示对话消息和输入框
- 用户设置界面（基本信息、修改显示名称、修改密码）
- 推理过程展开显示

### pages/admin_page.py — 管理员页面

渲染管理员界面，提供用户管理和审计日志功能。

**功能特性：**
- 用户管理（查看、创建、修改角色、启用/禁用）
- 审计日志（查看、过滤、统计）
- 知识库管理（查看知识库列表、查看文档列表、分页浏览）

---

## 📖 推理过程示例

### 示例1：文档类问题

```
用户：公司年假制度是怎么规定的？

[RAG Agent 推理过程]
🔧 调用工具：**rag_search**
   参数 query：公司年假制度规定
✅ 工具返回：[来源：员工手册.docx] 根据国家规定...

助手：根据《员工手册》第五章规定，公司年假制度如下：
1. 入职满1年可享受5天年假
2. 入职满10年可享受10天年假
...
```

### 示例2：数据类问题

```
用户：1月研发中心的平均工资是多少？

[Data Agent 推理过程]
🔧 调用工具：**list_files**
✅ 工具返回：共找到3个文件：薪资.xlsx、考勤.xlsx、绩效.xlsx
🔧 调用工具：**inspect_file**
   参数 file_path：D:\data\薪资.xlsx
✅ 工具返回：列名：['部门', '月份', '姓名', '工资']
🔧 调用工具：**execute_data_query**
   参数 query：计算1月研发中心的平均工资
✅ 工具返回：{"status":"success","summary":"1月研发中心平均工资为8500元",...}

助手：根据数据分析结果，1月研发中心的平均工资为 8500 元。
```

---

## 📱 用户界面预览

### 普通用户视图

1. **对话界面**：侧边栏显示对话列表，主区域显示对话消息
2. **用户设置**：点击侧边栏"用户设置"按钮，可修改显示名称和密码

### 管理员视图

1. **对话界面**：同普通用户
2. **管理后台**：点击侧边栏"管理后台"按钮，进入管理员页面
   - **用户管理**：查看、创建、修改用户角色、启用/禁用用户
   - **审计日志**：查看用户操作日志、统计信息
   - **知识库管理**：查看知识库列表、查看文档列表

---

## 📝 开发指南

### 添加新工具给现有智能体

1. 在对应的 agent 文件中定义新的 `@tool` 函数
2. 将工具添加到 `create_react_agent()` 的 `tools` 参数中
3. 更新 agent 的 `prompt`，告知 LLM 何时使用新工具

### 添加新的智能体

1. 在 `agents/` 目录创建新文件（如 `report_agent.py`）
2. 定义 `create_xxx_agent(llm)` 函数，返回 `create_react_agent()`
3. 在 `agent.py` 中导入并创建新智能体
4. 将新智能体添加到 `create_supervisor()` 的 `agents` 参数中
5. 更新 Router 的 `prompt`，添加新智能体的触发条件

### 添加新页面

1. 在 `pages/` 目录创建新文件（如 `new_page.py`）
2. 定义 `render()` 函数作为页面入口
3. 在 `app.py` 中添加页面路由逻辑
4. 根据需要添加侧边栏导航

### 调试技巧

- 查看 `.streamlit/config.toml` 配置 Streamlit 行为
- 在 `chat()` 函数中，`steps_log` 记录了完整的工具调用过程
- 使用 `streamlit run app.py` 的 Web 界面，展开"查看推理过程"可以看到详细日志
- 查看 `data/hngd.db` 数据库文件，了解数据持久化情况

---

## ⚠️ 注意事项

1. **API Key 安全**：请勿将 `.env` 文件提交到 Git 仓库
2. **数据文件路径**：确保 `DATA_DIR` 配置的路径存在且有读取权限
3. **代码沙箱**：`code_executor.py` 需要确保 `DATA_PATH` 只允许读取指定目录
4. **LLM 切换**：修改 `agent.py` 中的 `model` 和 `base_url` 可切换不同 LLM
5. **Dify 知识库**：需要提前在 Dify 平台创建知识库并获取 API Key
6. **数据库备份**：定期备份 `data/hngd.db` 数据库文件，防止数据丢失
7. **密码安全**：用户密码使用 bcrypt 哈希存储，无法逆向解密

---

## 📄 许可证

内部项目，仅供企业使用。

---

## 📞 联系方式

如有问题或建议，请联系项目维护团队。

---

## 🚀 快速启动（三步即可运行）

> 新环境从零开始，只需三步即可启动系统。

### 第一步：复制环境变量模板

```bash
cp .env.example .env
```

编辑 `.env` 文件，填写必要配置项（至少填写 `QWEN_API_KEY`、`DIFY_DATASET_KEY`、`DIFY_KB_ID`）。

### 第二步：安装依赖

```bash
python -m venv venv

# 激活虚拟环境
.\venv\Scripts\Activate.ps1    # Windows PowerShell
# source venv/bin/activate     # macOS/Linux

pip install -r requirements.txt
```

### 第三步：一键启动

```bash
# Linux / macOS
bash start.sh

# Windows
start.bat
```

启动后访问 http://localhost:8501 即可使用。

---

## 🔑 默认账号

> **上线前必须修改所有默认密码！**

| 用户名 | 默认密码 | 角色 | 说明 |
|--------|----------|------|------|
| admin | Admin@123 | admin | 系统管理员，拥有全部权限 |
| user01 | User@123 | user | 普通用户，可使用对话功能 |
| visitor | Visitor@123 | visitor | 访客，仅能查看界面，无法使用功能 |

---

## 🏗️ 系统架构说明

系统采用五层架构设计，职责清晰、易于扩展：

| 层级 | 名称 | 组件 | 职责 |
|------|------|------|------|
| L1 | 接入层 | Streamlit Web UI / CLI | 用户交互界面，支持 Web 和命令行两种方式 |
| L2 | 网关层 | 登录认证 / 角色鉴权 / 审计日志 | 身份验证、权限控制、操作留痕 |
| L3 | 智能体核心层 | Router / RAG Agent / Data Agent / Agent 注册表 | 智能路由分发，双引擎协同，可扩展注册 |
| L4 | 基础设施层 | Dify 知识库 / 代码沙箱 / LLM 服务 / SQLite 数据库 | 外部服务对接、数据持久化、安全隔离 |
| L5 | 扩展层（预留） | MCP 接入 / Skill 插件 / 企业集成 | 预留扩展能力，当前版本不实现 |

**模块依赖关系：**

```
Streamlit UI (app.py / pages/)
    ↓
认证授权 (auth/)
    ↓
核心调度 (agent.py) ← 审计日志 (audit/)
    ↓
智能体 (agents/)
    ↓
数据服务 (data/) / 外部服务 (Dify / 代码沙箱)
    ↓
数据库 (core/database.py)
```

---

## 🛡️ 角色权限表

| 功能 | visitor 访客 | user 普通用户 | admin 管理员 |
|------|:-----------:|:------------:|:-----------:|
| 登录系统 | ✅ | ✅ | ✅ |
| RAG 知识库问答 | ❌ | ✅ | ✅ |
| Data 数据统计分析 | ❌ | ✅ | ✅ |
| 查看自己的对话记录 | ❌ | ✅ | ✅ |
| 用户设置（修改密码/名称）| ❌ | ✅ | ✅ |
| 管理员页面 | ❌ | ❌ | ✅ |
| 查看所有用户日志 | ❌ | ❌ | ✅ |
| 管理用户（增删改角色）| ❌ | ❌ | ✅ |
| 知识库管理 | ❌ | ❌ | ✅ |

> visitor 角色用于演示场景：领导扫码进来能看到界面，但无法使用功能，引导联系管理员开通账号。

---

## ❓ 常见问题

### 沙箱启动失败怎么排查？

1. **端口占用**：检查 8001 端口是否被占用，执行 `netstat -ano | findstr 8001`（Windows）或 `lsof -i :8001`（macOS/Linux）
2. **依赖缺失**：确认已执行 `pip install -r requirements.txt`，uvicorn 和 fastapi 已安装
3. **手动启动沙箱**：单独运行 `uvicorn code_executor:app --port 8001`，观察报错信息
4. **DATA_DIR 路径**：确认 `.env` 中 `DATA_DIR` 指向的目录存在且有读取权限

### 忘记 admin 密码怎么重置？

执行以下命令重新初始化数据库（会重置所有用户数据）：

```bash
# 备份现有数据库
copy data\hngd.db data\hngd.db.bak    # Windows
# cp data/hngd.db data/hngd.db.bak   # macOS/Linux

# 删除数据库并重新初始化
del data\hngd.db                       # Windows
# rm data/hngd.db                      # macOS/Linux
python scripts/init_db.py
```

如果只想重置 admin 密码而不影响其他数据，可在 Python 中执行：

```python
from auth.auth_service import hash_password
from core.database import get_db

db = get_db()
new_hash = hash_password("YourNewPassword123")
db.execute("UPDATE users SET password_hash = ? WHERE username = 'admin'", (new_hash,))
db.commit()
db.close()
print("admin 密码已重置")
```

### 启动后页面空白或报错？

1. 确认 `.env` 文件存在且配置正确
2. 确认 `data/hngd.db` 已初始化（运行 `python scripts/init_db.py`）
3. 查看终端中的错误日志

### 如何切换 LLM 模型？

编辑 `agent.py` 中的 `model` 和 `base_url` 参数：
- 本地 Ollama：使用 `deepseek-r1:32b`，无需 API Key
- 阿里千问：设置 `QWEN_API_KEY`，模型使用 `qwen-plus`

### 如何修改用户密码？

1. **用户自助修改**：登录后点击侧边栏"用户设置"按钮，在"修改密码"部分输入当前密码和新密码
2. **管理员重置**：管理员可以在"管理后台"→"用户管理"中禁用账号，或联系开发者直接修改数据库

### 知识库管理界面显示"未配置 DIFY_DATASET_KEY"怎么办？

需要在 `.env` 文件中配置 `DIFY_DATASET_KEY`。该 Key 可以在 Dify 平台的知识库设置中找到。

### 如何备份数据库？

执行以下命令备份数据库：

```bash
# Windows
copy data\hngd.db data\hngd.db.bak

# macOS/Linux
cp data/hngd.db data/hngd.db.bak
```

### 对话记录太多，如何管理？

- 在侧边栏的对话列表中，点击对话右侧的"🗑️"按钮可以删除对话
- 系统会自动生成对话标题（基于首条消息）
- 点击对话列表中的对话可以切换不同对话
