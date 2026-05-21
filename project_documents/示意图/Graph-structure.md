# HNGD-Agent Graph 结构示意图

> 最后更新：2026-05-19

## 一、整体架构（Supervisor 模式）

```
┌─────────────────────────────────────────────────────────────────┐
│                        用户输入 (User Input)                     │
│                    chat_page.py / main.py                       │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Router (Supervisor)                         │
│                  agent.py → create_supervisor                   │
│                                                                 │
│  职责：判断问题类型 → 转发给对应 Agent → 原样返回结果              │
│  模型：qwen-plus / 本地 Ollama (qwen3.6:35b)                     │
│  记忆：MemorySaver (内存)                                        │
│                                                                 │
│  路由规则：                                                      │
│    → rag_agent  : 文档问答、制度查询、知识库查询、仿写             │
│    → data_agent : 统计排名、考勤分析、Excel 处理、数据计算         │
└──────────┬─────────────────────────────┬────────────────────────┘
           │                             │
           ▼                             ▼
┌──────────────────────┐    ┌──────────────────────────┐
│     rag_agent        │    │      data_agent          │
│  (ReAct Agent)       │    │  (ReAct Agent)           │
│                      │    │                          │
│  工具：              │    │  工具：                   │
│  - rag_search        │    │  - list_files            │
│  - list_kb_documents │    │  - inspect_file          │
│                      │    │  - execute_data_query    │
│  详见下方展开         │    │  详见下方展开             │
└──────────────────────┘    └──────────────────────────┘
```

---

## 二、RAG Agent（ReAct Agent）

### 设计理念

Agent 自主决策工具调用，不预设固定流程。`rag_search` 内置完整的"改写→检索→回退→生成→验证→重试"链路，Agent 通常只需调用一次即可获得答案。

### Agent 工具

| 工具 | 用途 | 调用时机 |
|------|------|---------|
| `rag_search(query)` | 检索知识库并生成答案 | 文档问答、制度查询、内容总结 |
| `list_kb_documents(keyword)` | 查看知识库文档列表 | 用户问"知识库里有什么" |

### rag_search 内部流程

```
query (用户问题)
    │
    ▼
┌──────────────────────────────────────────────────────────────┐
│  Step 1: 查询改写                                             │
│                                                              │
│  rewrite_query(llm, query)                                   │
│    ├─ 问题较短 (≤10字符 或 ≤3词) ──→ 跳过改写，使用原问题      │
│    └─ 问题较长 ──→ LLM 改写为结构化查询                        │
│                    (rewritten_query + keywords + sub_questions)│
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────┐
│  Step 2: 首次检索 (改写后的查询)                               │
│                                                              │
│  _retrieve_from_dify(rewritten_query)                        │
│  (semantic_search, top_k=10, 无分数阈值)                      │
└──────────────────────┬───────────────────────────────────────┘
                       │
              ┌────────┴────────┐
              │                 │
          有结果             无结果
              │                 │
              │                 ▼
              │    ┌────────────────────────────────────┐
              │    │  Step 3: 回退检索 (原始查询)        │
              │    │  _retrieve_from_dify(original_query)│
              │    └────────────┬───────────────────────┘
              │                 │
              │         ┌───────┴───────┐
              │     有结果            无结果
              │         │               │
              ▼         ▼               ▼
┌────────────────────────────┐   "知识库中未检索到相关内容"
│  Step 4: 生成答案           │
│  _generate_answer(llm,     │
│    query, context_text)     │
└────────────┬───────────────┘
             │
             ▼
┌────────────────────────────────────────────────────────────┐
│  Step 5: 答案验证                                           │
│                                                            │
│  verify_answer(llm, query, context, answer)                │
│  → GOOD / HALLUCINATION / NO_CONTEXT / INSUFFICIENT        │
└────────────┬───────────────────────────────────────────────┘
             │
    ┌────────┼────────────┬──────────────┐
    │        │            │              │
  GOOD   NO_CONTEXT  INSUFFICIENT   HALLUCINATION
    │        │            │              │
    │        │            ▼              ▼
    │        │   ┌─────────────────────────────────┐
    │        │   │  Step 6: 自动重试 (最多1次)       │
    │        │   │                                 │
    │        │   │  retry_query = "请详细介绍关于     │
    │        │   │  以下内容的规定：{query}"          │
    │        │   │                                 │
    │        │   │  _retrieve_from_dify(retry_query)│
    │        │   │  → _generate_answer()            │
    │        │   │  → verify_answer()               │
    │        │   └────────────┬────────────────────┘
    │        │                │
    │        │        ┌───────┴────────┐
    │        │    重试后 GOOD    重试后仍不行
    │        │        │                │
    ▼        ▼        ▼                ▼
  返回答案  "未找到"  返回答案    INSUFFICIENT → 部分答案 + ⚠️提示
                                 HALLUCINATION → "无法生成可靠答案"
```

### list_kb_documents 流程

```
keyword 参数 (可选)
    │
    ▼
分页遍历 Dify API (/documents)
    │
    ├─ 有 keyword ──→ 过滤匹配文档名
    └─ 无 keyword  ──→ 返回全部文档
    │
    ▼
格式化输出 (✓ 已索引 / ⏳ 索引中)
```

### Agent Prompt 设计

采用"工具说明 + 硬性约束"模式，不规定调用顺序：
- 工具说明：描述每个工具做什么、何时使用
- 硬性约束：运行环境物理限制（违反必然失败）

---

## 三、Data Agent（ReAct Agent）

### Agent 工具

| 工具 | 用途 | 调用时机 |
|------|------|---------|
| `list_files()` | 列出数据目录中的 Excel 文件 | 统计前必须先调用 |
| `inspect_file(file_path)` | 读取文件原始内容，判断表头位置 | 获取列名和 skiprows |
| `execute_data_query(query, file_path, skiprows)` | 生成 Python 代码并执行统计 | 实际数据计算 |

### 工具调用流程（Agent 自主决策，非固定）

```
用户问题 (统计/排名/计算类)
    │
    ▼
┌──────────────────────────────────────┐
│  list_files()                        │
│  列出 DATA_DIR 下所有 Excel 文件       │
│  返回文件名 + 完整路径                 │
└──────────────┬───────────────────────┘
               │
               ▼
┌──────────────────────────────────────┐
│  inspect_file(file_path)             │
│  读取原始前10行 (header=None)         │
│  + 参考列名 (header=0)               │
│  → Agent 自主判断表头行位置 skiprows   │
└──────────────┬───────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────┐
│  execute_data_query(query, file_path,         │
│                     skiprows)                 │
│                                              │
│  1. LLM 根据 query + 列名 生成 Python 代码    │
│  2. 发送到 EXECUTOR_URL 沙箱执行              │
│  3. 返回 {status, summary, data}              │
│                                              │
│  多文件：file_path 逗号分隔                    │
│  → 代码自动循环读取+合并再分析                 │
└──────────────────────────────────────────────┘
```

### Agent Prompt 设计

同样采用"工具说明 + 硬性约束"模式：
- 工具说明：描述每个工具的功能和参数
- 硬性约束：
  1. `skiprows` 必须传入 `inspect_file` 判断出的值
  2. 代码不能调用 agent 工具（沙箱中不可用）
  3. `.xlsx/.xls` 必须用 `pd.read_excel()`，`.csv` 必须用 `pd.read_csv()`

---

## 四、State 数据流

### Supervisor State (由 create_supervisor 管理)

| 字段           | 类型                    | 说明               |
|----------------|------------------------|--------------------|
| `messages`     | `list[BaseMessage]`    | 完整对话消息流       |
| `user_context` | `dict` (可选)          | 用户身份信息         |

### Sub-Agent State

两个 Sub-Agent 均为 ReAct Agent，使用标准 `messages` 接口，无自定义 State。

---

## 五、外部服务依赖

```
┌────────────────────┐     ┌────────────────────┐
│   Dify API         │     │   Code Executor    │
│ (知识库检索)        │     │ (代码执行服务)      │
│                    │     │                    │
│ POST /retrieve     │     │ POST EXECUTOR_URL  │
│ GET  /documents    │     │ {code, data_path}  │
│                    │     │                    │
│ rag_agent 调用     │     │ data_agent 调用     │
└────────────────────┘     └────────────────────┘

┌────────────────────┐
│   LLM              │
│ (云端/本地)         │
│                    │
│ 云端：Qwen API     │
│  model: qwen-plus  │
│                    │
│ 本地：Ollama       │
│  model: qwen3.6:35b│
│  :11434/v1         │
│                    │
│ 所有 Agent 共用     │
└────────────────────┘
```

---

## 六、文件与模块映射

```
agent.py                  → Router (Supervisor) 定义 + chat() 入口
agents/rag_agent.py       → RAG Agent (ReAct Agent)
                             工具：rag_search, list_kb_documents
                             辅助：rewrite_query, verify_answer,
                                    _retrieve_from_dify, _format_records,
                                    _log_records, _generate_answer
agents/data_agent.py      → Data Agent (ReAct Agent)
                             工具：list_files, inspect_file, execute_data_query
agents/registry.py        → Agent 注册表与权限声明
app.py                    → Streamlit 主入口 + 登录/页面路由
pages/chat_page.py        → 对话页 UI
pages/admin_page.py       → 管理后台 UI
main.py                   → CLI 入口
auth/                     → 认证模块 (登录/会话/角色)
audit/                    → 审计日志
data/                     → 数据服务 (对话存储/dify服务)
code_executor.py          → 代码执行服务 (供 data_agent 调用)
```
