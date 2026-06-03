# 开发日志列表
:

## 2026-06-02 (记忆系统博客优化)

**内容**：优化 `blog/blog_05_记忆系统_长短期与混合记忆.md`，补全三层存储模型（STM/LTM/Hybrid），新增经验记忆缓存（cache_service）分析、语义降权标签说明、完整消息保存时间线、两周长期记忆（Dify RAG + Q&A向量匹配）对比。

---

## 2026-05-29 (经验记忆缓存：相似问题向量匹配)

**功能**：新增经验记忆缓存——提问时先与历史问题做向量相似度匹配，命中则将历史Q&A作为上下文参考注入LLM回答。

**方案**：
- database.py：messages表新增question_vec列，init_db兼容已有数据库迁移
- cache_service.py（新建）：embed_text（Qwen embedding）、cosine_similarity、search_cache、save_embedding、_should_cache（噪音过滤）
- rag_agent.py：rag_search内Step0先查缓存，命中附加历史Q&A到上下文（标注仅供参考）
- chat_page.py：回答后异步计算用户问题向量写入messages表（异常不影响主流程）

**修改文件**：core/database.py、agents/rag_agent.py、pages/chat_page.py；新建data/cache_service.py

**时间**：2026-05-29 16:30
## 2026-06-01 (Streamlit → HTML 前端迁移)

将原 Streamlit 多页面应用迁移为独立 HTML + REST API 架构，涵盖四个模块：

- **登录模块**：`login-page.html`，JWT 登录/注销，`/api/auth/login` & `/api/auth/logout`。
- **对话模块**：`home-page.html`，多会话 SSE 流式对话，`/api/conversations` & `/api/chat/stream`；文件管理入口 `more-features-page.html`。
- **文档编写模块**：`home-page.html` 内嵌文档区，两步流程（生成大纲 → 确认 → 生成正文），`/api/doc/*`。
- **用户设置模块**：`setting-page.html`，修改显示名称 & 密码，`PUT /api/user/display-name` & `PUT /api/user/password`。
- **管理员模块**：`admin-page.html`，用户管理/审计日志/知识库管理三 Tab，新增 8 个 `/api/admin/*` 接口，底层复用原有 service 函数不改动业务逻辑。

各模块均编写接口对照说明文档（`project_documents/接口对照说明_*.md`）。

**时间**：2026-06-01

---

## 2026-05-31 (data_schema.json 列名单位标注)

**优化**：考勤模板 columns 中新增单位后缀（`工作时长(小时)`），同时将原来无单位的假期列（事假/调休/年假/病假等）统一改为带单位标注，消除 LLM 自行推断和换算单位的动机，避免生成派生列导致 groupby.agg 找不到原始列而失败。

**修改文件**：`project_documents/data_schema.json` — 考勤 columns 各时长/假期列补全单位括号后缀。

**时间**：2026-05-31

---

## 2026-05-31 (data_agent 新增 lookup_schema 工具)

**优化**：新增 `lookup_schema` 工具，优先读取 `project_documents/data_schema.json` 中已登记的文件模板。命中模板后可直接调用 `execute_data_query`，跳过 `list_files` 和 `inspect_file`，减少 2 次工具调用和约 20s 等待；未命中时回退到原流程。同时修复 data_schema.json 中 `采购_硬件` notes 字段含未转义双引号导致 JSON 解析失败的 bug（将 `"元"` 改为 `'元'`）。

**根因**（JSON bug）：notes 字段内容为 `设备价格字段含单位"元"，...`，双引号未转义，导致 `lookup_schema` 读取时抛 `Expecting ',' delimiter` 错误，降级走 list_files 全流程，无优化效果。

**修改文件**：`agents/data_agent.py`（新增 `lookup_schema` 工具、更新 tools 列表和 prompt 优先流程）、`project_documents/data_schema.json`（修复 JSON 语法）。

**时间**：2026-05-31

---

## 2026-05-29 (生成文档标题去除"文档标题："前缀)

**优化**：提取 outline 中的 h1 标题时自动去掉 LLM 自动生成的"文档标题："前缀，只保留 `# 标题名`。

**修改文件**：`agents/doc_agent.py` — 标题提取行增加 `replace("文档标题：", "")` 清理。

**时间**：2026-05-29 11:13

---

## 2026-05-29 (新建对话时重置文档编写状态)

**问题**：文档撰写模式生成文章后，点击"新建对话"再切回文档撰写时仍显示旧文档；只有点击"新建文档"按钮才能开始新文档。

**方案**：`doc_page.py` 新增 `reset_doc_state()` 辅助函数，`index_page.py` 和 `chat_page.py` 的"新建对话"按钮及"文档编写/撰写"入口按钮均调用该函数，确保进入文档编写时始终是新文档。

**修改文件**：`pages/doc_page.py`（新增 `reset_doc_state()`）、`pages/chat_page.py`（2处）、`pages/index_page.py`（2处）

**时间**：2026-05-29 11:29

---

## 2026-05-29 (生成文档补齐标题)

**优化**：提取 outline 中的 h1 标题时自动去掉 LLM 自动生成的"文档标题："前缀，只保留 `# 标题名`。

**修改文件**：`agents/doc_agent.py` — 标题提取行增加 `replace("文档标题：", "")` 清理。

**时间**：2026-05-29 11:13

---

## 2026-05-29 (生成文档补齐标题)

**优化**：逐章生成文档时从 outline 中提取 `# 文档标题`（h1）并置于正文最前面，之前缺少标题行。

**修改文件**：`agents/doc_agent.py` — `generate_document_content` 中逐章生成前先解析 outline 首行 h1 标题，拼入 `full_doc_parts` 首部。

**时间**：2026-05-29 10:56

---

## 2026-05-29 (文档生成 APIConnectionError 兜底恢复)

**问题**：文档生成时 Agent 工具调用（逐章生成）成功，但最后 Agent 将大型文档回传 LLM 做收尾决策时 Qwen API 断开连接（`Server disconnected without sending a response`），导致已生成的完整文档被丢弃。

**方案**：`agent.py` 的 `chat_direct()` stream 循环包裹 try/except，捕获连接错误后优先从 `ToolMessage`（工具返回）提取已生成文档，避免前功尽弃。

**修改文件**：`agent.py` — stream 循环加 APIConnectionError 捕获，`ToolMessage` 导入，答案提取改为先查 tool 返回再 AIMessage。

**时间**：2026-05-29 10:02

---


## 2026-05-28 (修复 SqliteSaver 导入错误 - venv 安装遗漏)

**问题**：`ModuleNotFoundError: No module named 'langgraph.checkpoint.sqlite'`，上次 `pip install` 装到了全局 Python 而非项目 venv。

**修复**：用 venv 路径 `venv\Scripts\pip.exe install langgraph-checkpoint-sqlite` 重新安装，并调整 `SqliteSaver` 初始化方式——`from_conn_string()` 是 context manager，模块级使用改用 `sqlite3.connect() + SqliteSaver(conn) + .setup()`。

**修改文件**：`agent.py`

---

## 2026-05-28 (修复多轮对话上下文记忆丢失 - 第二轮)

**问题**：同一对话中追问"那第二呢"时，LLM 仍无法理解上下文。

**根因分析（两个问题叠加）**：
1. **致命 Bug**：`_build_messages_with_history()` 调用 `get_messages(conv_id)` 缺少必需的 `user_id` 参数 → 触发 TypeError → 历史消息永远无法加载
2. **设计缺陷**：使用 `MemorySaver`（纯内存字典），Streamlit rerun 或服务重启后运行时状态必然丢失

**修复方案（双重保障）**：
1. **修复 Bug**：`_build_messages_with_history()` 新增 `user_id` 参数，从 `user_context["user_id"]` 提取并正确传递给 `get_messages(conv_id, user_id)`
2. **持久化 Checkpointer**：将 `MemorySaver` 替换为 `SqliteSaver`，checkpoint 数据写入 `data/checkpoints.sqlite` 文件，重启不丢失
3. **保留手动注入**：即使 SqliteSaver 已生效，仍保留 SQLite 历史消息注入作为 Streamlit rerun 场景下的额外保险

**修改文件**：`agent.py`, `requirements.txt`
**新增依赖**：`langgraph-checkpoint-sqlite>=2.0.0`

---

## 2026-05-28 (LangSmith 思考链分析 — data_agent 4轮迭代查询 135s)

分析 `trace_export.json`（28,907 行）中 data_agent 处理经费统计问题的完整思考链：诊断出 3 个核心问题（4 轮迭代查询、列名含空格括号识别失败、LLM 代码生成耗时过重），总耗时 135s（data_agent 占 96.9%），给出 5 条优化建议，预期降至 15-20s。

**输出文件**：`problem_document/problem_record_4.md`

## 2026-05-28 (LangSmith 思考链分析 — rag_agent 三子问题问答)

分析 `trace_export.json`（9871 行）中 rag_agent 处理复合问题的完整思考链：识别出 6 个问题（多子问题合并检索、答案重复生成、Dify 验证低效、知识库数据缺失、ParentCommand 异常、信息衰减），总耗时 45.8s / 8,267 tokens。

**输出文件**：`problem_document/problem_record_3.md`

---
## 2026-05-27 (更新智能体工作流说明文档)

同步当前代码变更到 `智能体工作流说明.md`：Supervisor agents 改为 [rag, data]、补充最多两次转发规则、doc_agent 仅直调不路由、新增 index_page 三种模式调用路径表。

**修改文件**：`project_documents/智能体工作流说明.md`

---

## 2026-05-27 (修复 GraphRecursionError 无限循环)

**问题**：Supervisor 收到子 Agent "未找到"类回答后，会尝试重新路由到另一个 Agent，形成死循环触发 recursion_limit=50。

**修复**：优化 Supervisor prompt，明确最多两次转发、达到上限后即使未找到也必须结束，同时 rag_agent 职责补充"咨询建议类问题"。

**修改文件**：`agent.py`

---

## 2026-05-27 (修复历史对话标题始终显示"新对话")

**问题**：点击"新建对话"时已设置 `current_conversation_id`，导致发送消息后标题更新逻辑被跳过，标题永远为"新对话"。

**修复**：在 `chat_page.py` 中新增 else 分支，检查对话标题是否为默认"新对话"，若是则用第一条用户消息更新标题。

**修改文件**：`pages/chat_page.py`

---

## 2026-05-27 (知识库问答模式移除 doc_agent 路由)

**问题**：知识库问答模式下 Supervisor 可能将写作类问题路由到 doc_agent，导致生成目录等不符合聊天 UI 的输出。

**修复**：Supervisor agents 列表从 `[rag, data, doc]` 改为 `[rag, data]`，写作类文本需求由 rag_agent 直接回答。doc_agent 仍通过文档撰写页 chat_direct 调用，不受影响。

**修改文件**：`agent.py`

**时间**：2026-05-27

---

## 2026-05-27 (项目概述重写)

重写 `项目概述.md`（约 450 字），涵盖系统定位、核心架构（Supervisor + 3 Agent）、功能亮点、技术栈和部署方式，聚焦宏观全局视角。

---

## 2026-05-27 (项目架构图全面重绘)

基于实际代码重绘 `项目架构图(文字+符号).md`：五层架构明确（展示层→网关层→业务逻辑层→基础设施层→数据层），新增 doc_agent 工具链、规则引擎三阶段工作流、Agent 注册表、核心数据流路径、系统启动流程、数据库表结构等完整图示。

---

## 2026-05-27 (功能点清单全面梳理更新)

全面梳理项目核心功能点，基于实际代码更新 `function_point.md`：从 10 个章节扩展为 14 个章节，新增规则引擎、LLM 与可观测性、Agent 注册与权限、文件解析四大章节；RAG/数据分析/文档编写/代码沙箱/对话功能等章节大幅补充实现细节（查询改写、答案验证、代码缓存、进程池预热、逐章生成等）。

---

## 2026-05-26 (三智能体工作流文档整理)

新增 `project_documents/智能体工作流说明.md`，详细记录 rag_agent/data_agent/doc_agent 的工作流、关键机制和共享架构。

---

## 2026-05-26 (仅保存有实际消息的对话 + 文档生成记录融入侧边栏)

**问题1**：进入任意模式即自动创建空对话（即使用户未输入）。

**修复1**：`chat_page.py` 去掉 `render_chat_main()` 的自动创建逻辑，改为仅在用户真正发送消息时创建对话并生成标题。

**问题2**：文档生成历史仅在 doc_page 底部独立展示，不在侧边栏统一显示。

**修复2**：`_auto_save_document()` 同步创建 conversations 记录（用户消息=需求，助手消息=文档内容），侧边栏自动刷新；移除 doc_page 底部独立历史区域和废弃函数。

**修改文件**：`pages/chat_page.py`、`pages/doc_page.py`

**时间**：2026-05-26 18:04

---

## 2026-05-26 (修复模式切换 no-op 错误 + 历史对话无响应)

**问题1**：点击文档撰写出现 "Calling st.rerun() within a callback is a no-op"。

**根因**：Streamlit `st.button(on_click=...)` 回调内部不允许调用 `st.rerun()`。

**修复1**：回退为 `if st.button(...):` 模式，在按钮判断体内调用 `st.rerun()`。

**问题2**：文档撰写模式下点击侧边栏历史对话无响应。

**根因**：只设置了 `current_conversation_id`/`messages`，未切换 `agent_mode`，页面仍渲染文档撰写。

**修复2**：点击历史对话时同步设置 `agent_mode = "knowledge_qa"`。

**补充**：`doc_page.render(embedded=True)` 只是跳过独立标题（index_page 已统一渲染），侧边栏由 index_page 统一管理，无需额外统一。

**修改文件**：`pages/index_page.py`

**时间**：2026-05-26 17:42

**问题**：在首页切换"知识库问答"→"数据统计"时，对话状态不清空，用户仍在上一模式的对话中继续。

**方案**：`_render_agent_selector()` 三个模式按钮改用 `st.button(on_click=_switch_mode)` 回调，切换时自动清除 `current_conversation_id` 和 `messages`。

**修改文件**：`pages/index_page.py`

**时间**：2026-05-26 17:25

---

## 2026-05-26 (修复相对时间显示 8 小时偏差)

**问题**：对话和文档历史的相对时间（"X小时前"）始终比实际多约 8 小时。

**根因**：SQLite `CURRENT_TIMESTAMP` 返回 UTC 时间，而 `datetime.now()` 返回本地时间（UTC+8），导致 8 小时偏差。

**方案**：创建 `core/time_utils.py` 统一工具函数，使用 `datetime.now(timezone.utc)` 与数据库 UTC 时间戳对齐；所有页面统一调用 `calc_rel_time()`，消除重复代码。

**修改文件**：`core/time_utils.py`（新增）、`pages/index_page.py`、`pages/chat_page.py`、`pages/doc_page.py`

**时间**：2026-05-26 17:08

---

## 2026-05-26 (文档撰写接入 Agent 框架 + 完整 LangSmith Trace)

**问题**：`doc_page.py` 绕过 `doc_agent`，直接 `llm.invoke()` 调用 LLM，LangSmith trace 中看不到 Agent 调用链和 KB 检索步骤。

**方案**：`doc_page.py` 保持三步 UI，每步通过 `chat_direct("doc_agent", ...)` 调用 doc_agent；doc_agent 新增 `search_knowledge_base` 工具（直调 Dify 语义检索），KB 检索纳入 Agent trace。

**改动1**：`agents/doc_agent.py` — 新增 `search_knowledge_base` 工具，`generate_document_outline/content` 增加 `reference_context` 参数，prompt 改为单阶段调用。
**改动2**：`agent.py` — `chat_direct()` 的 `agent_map` 新增 `doc_agent`。
**改动3**：`pages/doc_page.py` — 删除重复的 `OUTLINE_PROMPT`/`SECTION_PROMPT`/`_parse_sections`/`_invoke_with_retry`；附件解析保留，KB 检索移入 doc_agent；Step 1/2 改用 `chat_direct("doc_agent", ...)` + 展示 steps_log。

**工作流**：用户需求+附件 → doc_page 解析附件 → chat_direct("doc_agent") → search_knowledge_base（检索 Dify KB）→ generate_document_outline（生成目录）→ 用户确认 → generate_document_content（逐章生成文档）→ 完整 LangSmith trace。

**修改文件**：`agents/doc_agent.py`、`agent.py`、`pages/doc_page.py`

**时间**：2026-05-26 16:17

---

## 2026-05-25 (页面布局统一与侧边导航优化)

**优化5**：三种模式内容区统一显示"当前智能体：XXX"标签，文档撰写模式与问答/统计模式保持一致。

**修改文件**：`pages/index_page.py`

**时间**：2026-05-25 18:59

---

## 2026-05-25 (页面布局统一与侧边导航优化)

**优化1**：创建 `.streamlit/config.toml` 设置 `showSidebarNavigation = false`，隐藏 Streamlit 自动生成的左侧页面导航列表。

**优化2**：首页 `_render_agent_selector()` 改为公共母版样式，所有模式统一显示"企业知识库智能体"标题 + "支持文档问答·数据统计·文档编写·内容仿写"副标题 + 三个模式切换按钮。

**优化3**：`render_chat_main()` 移除标题/副标题（已上移至母版），知识库问答和数据统计模式下方直接显示对话输入框。

**优化4**：`doc_page.render()` 新增 `embedded` 参数，嵌入首页时跳过自有标题/副标题，由母版统一展示，保持三步流程不变。

**修改文件**：`.streamlit/config.toml`(新增)、`pages/index_page.py`、`pages/chat_page.py`、`pages/doc_page.py`

**时间**：2026-05-25 18:52

---

## 2026-05-25 (登录与交互流程优化)

**优化1**：登录页改为身份标签切换（管理员/普通用户），选择身份后输入账号密码登录，验证角色匹配，登录后直入首页。

**优化2**：首页智能体标题从"使用不同智能体开始对话"改为动态"当前智能体：{模式名}"，随切换实时更新。

**优化3**：知识库问答/数据统计模式下自动创建对话，直接显示聊天输入框，无需手动点击"新建对话"。

**优化4**："新建对话"按钮同步重置 `agent_mode` 为知识库问答，确保每次新建对话均回到初始模式。

**修改文件**：`app.py`、`pages/index_page.py`、`pages/chat_page.py`

**时间**：2026-05-25 18:36

---

## 2026-05-25 (首页重构收尾修复)

**修复**：恢复 `app.py` 中 `init_db()` 调用（之前被误注释），确保启动时自动补建缺失的数据库表。

**修复**：首页文档撰写模式下隐藏智能体选择器标题，避免与 doc_page 标题重复。

**修复**：doc_page 中"← 返回首页"按钮同步重置 `agent_mode` 为 `knowledge_qa`，确保从文档撰写模式返回时正确切换到知识库问答模式。

**修改文件**：`app.py`、`pages/index_page.py`、`pages/doc_page.py`

**时间**：2026-05-25 18:30

---

## 2026-05-25 (UI重构：首页 + 三种智能体模式切换)

**新增**：创建首页 `pages/index_page.py`，左侧导航栏（新建对话/历史对话/后台管理/账号管理/退出登录），右侧三种智能体模式切换按钮（知识库问答/数据统计/文档撰写）。

**新增**：`agent.py` 新增 `chat_direct()` 函数，支持直接调用指定智能体（数据统计模式使用 data_agent 直调，不经过 Supervisor 自动路由）。

**修改**：`pages/chat_page.py` — 提取 `render_chat_main(user, use_direct_agent)` 独立函数供首页复用，支持自动路由模式和指定智能体直调模式。

**修改**：`app.py` — 登录后默认路由到"首页"；保留旧路由"对话"/"文档编写"向后兼容。

**修改**：`pages/admin_page.py` — 侧边栏添加"← 返回首页"按钮。

**修改**：`pages/doc_page.py` — "返回对话"按钮改为"← 返回首页"，跳转目标同步更新。

**时间**：2026-05-25 18:00

---

## 2026-05-25 (历史文档列表改为单行布局)

**优化**：将时间提示、文档标题、查看query、删除合并为同一行，时间提示用灰色圆角标签与按钮等高对齐，整体更紧凑美观。

**修改文件**：`pages/doc_page.py` — `_render_doc_history` 和底部渲染处统一改为四列布局（col_time/col_title/col_query/col_del），时间提示使用 `st.markdown` + 内联 CSS 标签样式，移除独立 caption 行

**时间**：2026-05-25 16:57

---

## 2026-05-25 (查看用户query功能移至按钮交互)

**优化**：移除历史文档列表中默认的 query 截断预览框，将"📋 查看"改为"📋 查看用户query"按钮；点击后局部展开完整需求原文，再次点击收起，不影响其他文档项。

**修改文件**：`pages/doc_page.py` — 按钮重命名+切换展开逻辑（`doc_expanded_id` session_state 追踪），所有重置路径同步清除展开状态

**时间**：2026-05-25 16:37

---

## 2026-05-25 (历史文档需求原文支持局部展开查看)

**优化**：历史文档列表中需求原文超过40字时，使用 `st.expander` 折叠显示，点击即可局部展开查看完整内容，无需触发页面重载。

**修改文件**：`pages/doc_page.py` — caption 处改用条件 expander（超过40字折叠、不足直接显示）

**时间**：2026-05-25 16:17

---

## 2026-05-25 (修复 document_history 表缺失导致启动报错)

**修复**：`app.py` 启动时自动调用 `init_db()`，确保每次应用启动都会补建缺失的数据库表（CID 幂等）。原方案仅在 `start.bat` 中运行一次 `init_db.py`，旧数据库文件新增表后不会自动迁移。

**修改文件**：`app.py` — 在 `load_dotenv()` 后增加 `from core.database import init_db; init_db()`

**时间**：2026-05-25 16:03

---

## 2026-05-25 (文档编写历史记录持久化)

**功能**：文档编写页支持保存和查看历史生成文档，与对话页的历史记录模式一致。生成文档时自动保存到 SQLite `document_history` 表；页面底部展示历史列表，支持加载、查看、删除。

**新增/修改文件**：
- `core/database.py`：新增 `document_history` 表（id/user_id/title/requirements/outline/content/reference_context/timestamps）
- `data/document_service.py`：文档历史 CRUD 服务（save_document/get_documents/get_document/delete_document/generate_title_from_requirements）
- `pages/doc_page.py`：文档生成后自动保存（`_auto_save_document` 5分钟去重）；页面底部新增"📚 历史生成文档"区域，按更新时间倒序展示，支持点击加载/删除

**时间**：2026-05-25 15:50

---

## 2026-05-25 (文档编写增加文件上传+知识库检索)

**功能**：输入需求时支持上传参考附件（.txt/.md/.docx/.pdf/.xlsx 等），可选；同时自动调用 Dify 知识库语义检索用户 query 相关文档。附件内容 + 知识库结果融合为"参考上下文"，传入目录生成和内容生成 LLM prompt。LLM 在正文中引用参考资料时标注来源（[附件1]、[知识库：文件名.docx]）。

**新增文件**：
- `data/file_parser.py`：多格式文件内容提取器（txt/md/docx/pdf/xlsx/csv 等），自动截断超长内容（8000 字符）
- `data/kb_search.py`：`search_knowledge_base()` 调用 Dify 检索 API，`format_kb_results()` 格式化来源标注文本，`build_reference_context()` 融合两路参考上下文

**依赖新增**：`python-docx>=0.8.11`、`PyPDF2>=3.0.0`

**影响文件**：`pages/doc_page.py`（file_uploader + 参考上下文注入）、`agents/doc_agent.py`（提示词同步更新引用标注指令）、`requirements.txt`

**时间**：2026-05-25 15:02

---

## 2026-05-25 (二级标题丢失修复)

**问题**：逐章节生成文档时，一级标题正常，二级标题（如 1.1）在最终文档中消失。
**根因**：`_parse_sections` 只提取 `## ` 一级标题，没有把下属 `### ` 二级标题传入 LLM prompt，导致 LLM 不知道需要输出哪些二级标题。
**修复**：改 `_parse_sections` 返回 `[{title, subsections}]` 字典列表，在每章节 prompt 中显式列出"该章节下的二级标题（必须写入）"清单；`SECTION_PROMPT` 新增"保留所有二级标题"的硬性要求。`doc_page.py` 和 `doc_agent.py` 同步修改。

**时间**：2026-05-25 10:44

---

## 2026-05-24 (复制按钮 React 兼容修复)

**问题**：复制按钮报 `React error #231`，因为 Streamlit 底层用 React 渲染，React 不允许 HTML 标签里的 `onclick="..."` 字符串式事件绑定，必须用 `addEventListener`。

**修复**：将 `<button onclick="...">` 改为纯 `<button>` + `<script>addEventListener("click", ...)</script>`，绕过 React 对字符串事件处理的限制。复制逻辑不变（`navigator.clipboard` 优先，`execCommand('copy')` 兜底）。

**时间**：2026-05-24 15:46

---

## 2026-05-24 (复制按钮样式与标题字体再优化)

**复制按钮**：改为 SVG 图标（两个重叠矩形），白色背景、浅灰边框、圆角 0.375rem，与 Streamlit `st.code` 自带复制按钮视觉一致。复制逻辑改进为 `navigator.clipboard.writeText` 主路径 + `execCommand('copy')` fallback（临时 textarea 定位到视口外），确保各浏览器均可一键复制。按钮嵌入 `doc-display-area` 容器内部右上角，通过 `padding-top: 2.5rem` 避免遮挡正文。

**标题字体再调**：h1 1.3→1.2rem、h2 1.1→1.05rem、h3 0.95→0.9rem，阅读密度进一步提升。

**时间**：2026-05-24 14:56

---

## 2026-05-24 (文档展示体验优化 4 项)

**优化 1·去除描述说明**：`_parse_sections` 用正则 `re.split(r"\s*[—－]\s*")` 去除目录中 "— 内容说明" 部分，只保留章节名传给 LLM 生成正文。`SECTION_PROMPT` 和 `DOCUMENT_PROMPT` 均加入"标题只用章节名"约束。

**优化 2·字体缩小**：Step 3 注入自定义 CSS，`.doc-display-area` 范围内 h1/h2/h3 分别缩至 1.3/1.1/0.95rem，正文 0.85rem、行高 1.55，提升阅读密度。

**优化 3·一键复制**：文档容器右上角新增 "📋 复制" 按钮，通过隐藏 `<textarea>` + `navigator.clipboard.writeText` 实现整篇复制，点击后显示 "✅ 已复制" 2 秒。

**优化 4·按钮单行**：将 "🔄 修改目录重新生成" 缩写为 "🔄 重新生成"，列宽调为 `[1.3, 1, 1, 1.7]`，确保不再换行。

**时间**：2026-05-24 14:29

---

## 2026-05-24 (文档生成 APIConnectionError 修复)

**修复问题**：文档编写功能生成全文时偶发 `APIConnectionError: Connection error`，原因是 LLM 未设置 `max_tokens`（默认 2048），长篇文档超出限制导致服务端断开连接。

**修复内容**：`agent.py` 全局 LLM 加 `max_tokens=8192`、`timeout=300`、`max_retries=2`。`doc_page.py` 和 `doc_agent.py` 增加 `_invoke_with_retry` 重试函数，连接超时自动重试 3 次（指数退避）。

**时间**：2026-05-24 13:28

---

## 2026-05-24 (文档编写 Agent + 专用交互页面)

**新增功能**：Doc Agent 文档编写智能体 + 文档编写专用页面，实现"需求→目录→确认→生成"两步交互流程。

**架构**：新增 `agents/doc_agent.py`（ReAct Agent，含 `generate_document_outline`/`generate_document_content`/`improve_document_outline` 三个工具），与现有 rag_agent、data_agent 架构统一。`agent.py` Supervisor 路由新增 `doc_agent`，支持对话中处理编写文档/报告/方案等请求。

**专用页面**：`pages/doc_page.py` 实现三步流程指示器（输入需求→确认目录→生成文档）。Step1 用户输入需求，LLM 生成结构化目录；Step2 目录放入可编辑文本区，用户自由修改；Step3 用户确认后 LLM 生成完整文档并展示。支持修改目录重新生成、新建文档、查看 Markdown 源码复制等操作。

**集成**：`agents/registry.py` 注册 doc_agent；`app.py` 新增"文档编写"页面路由；`chat_page.py` 侧边栏新增"📝 文档编写"入口按钮。

**效果**：第三个业务功能上线，支持文档/报告/方案/手册/规章制度的智能编写，不影响原有 RAG 问答和数据统计功能。

**时间**：2026-05-24 12:42

---

## 2026-05-22 (全局规则 v2.0 重构——柔性拦截)

**问题**：v1.0 规则过于死板，SAFETY-001 拦截 import os 导致 os.path.basename() 等正常操作被阻断，多文件分析等功能不可用。

**重构**：重写 rule_config.yaml 和 integration.py，将一刀切 BLOCKLIST 改为精准拦截。仅 os.system/subprocess/eval/exec/compile/file-write 等真正危险操作标记 CRITICAL 并阻断；import os/os.path 等安全操作正常放行；风格/质量规则全部降为 WARNING，不阻断执行仅日志记录。

**新增 CODEBASE 类别**：7条代码库完整性指引（模块隔离/Registry扩展/功能开关/不可变核心/接口兼容/错误隔离/日志规范），enabled=false 仅作文档指导不自动检查，防止 AI 工具随意修改已验证完善的功能代码。

**修复**：data_agent.py 安全检查提示更明确；rag_agent.py 移除侵入式答案警告标记，仅对裸技术错误信息做静默替换。

**效果**：import os + os.path.basename() 正常通过；os.system/eval/subprocess 仍被 CRITICAL 阻断；规则从18条优化为17条（10条执行+7条文档指引）。

**时间**：2026-05-22 13:52

---

## 2026-05-22 (全局规则引擎)

**新增**：设计并实现全局规则配置系统，确保AI代码生成的一致性与高质量。

**架构**：rules/模块含models（Rule/RuleCategory/RuleSeverity/CheckResult数据模型）、engine（RulesEngine检查引擎，BLOCKLIST/ALLOWLIST/PATTERN/LLM_CHECK四种检查方式）、loader（YAML配置加载器）、integration（全局单例+便捷集成接口）。

**规则分类**：安全规则（禁止危险模块/文件操作/网络请求/代码注入，CRITICAL阻断）、代码风格（DATA_PATH/结构化输出/禁止硬编码，ERROR级）、输出质量（禁止编造/空答案/裸错误信息，CRITICAL~WARNING级）、业务领域（数值转换/日期处理/来源标记，ERROR~WARNING级），共18条。

**配置方式**：rules/rule_config.yaml以声明式YAML定义全部规则，支持按category/severity/type/stage/applies_to过滤，修改YAML即可调整规则不改变代码。

**集成点**：agent.py启动时初始化引擎含LLM检查器+用户输入安全校验；data_agent.py在代码发往沙箱前做BLOCKLIST/ALLOWLIST/PATTERN检查，CRITICAL违规拒绝执行；rag_agent.py在答案返回前做LLM_CHECK/PATTERN质量检查，违规附加警告或替换。

**配置项**：新增RULES_CONFIG_PATH/RULES_ENABLED/RULES_BLOCK_ON_CRITICAL环境变量；requirements.txt新增PyYAML>=6.0。

**效果**：AI生成代码在沙箱执行前通过12道安全+风格+领域检查，不安全代码被拦截反馈LLM修正；生成答案通过4道质量检查，空答案和异常错误被自动过滤。

**时间**：2026-05-22 11:26

---

## 2026-05-20 (code_executor 进程池预热改造)

**问题**：code_executor 每次请求通过 subprocess.run 创建新进程执行代码，pandas 冷启动 ~1.5s + 解释器启动 ~0.5s，占单次查询 60%+ 耗时。

**改造**：将 subprocess 冷启动改为 multiprocessing.Pool 进程池预热。Worker 启动时预加载 pandas/json/os/warnings，请求到达时直接 exec(code, namespace) 执行；stdout 通过 StringIO 重定向捕获；pool.apply_async + get(timeout=30) 实现超时控制；FastAPI lifespan 管理 Pool 生命周期。同时将 data_agent.py 的 requests.post 改为 Session 复用连接，消除每次 TCP 建连 ~2s 开销。

**效果**：预热后单次代码执行 9-10ms（对比 subprocess 冷启动 ~1.5-2s，提升 150x+）；data_agent 连接复用后消除 ~2s TCP 建连开销。

**时间**：2026-05-20 20:42

---

## 2026-05-20 (多文件查询 + 规则7优化)

**问题**：考勤多文件查询耗时185s，根因：多文件concat后无来源标识致月份统计全0→反复重试5次（-120s）；规则7强制对整数列调pd.to_datetime致ValueError崩溃（-20s）。

**修改**：多文件模板改为for循环逐个读取并注入`_source_file`列；规则7改为仅对datetime类型列转换；code_executor添加import os；prompt补充分组提示。

**效果**：预期消除5次无效重试和ValueError崩溃，185s→45-60s。

**时间**：2026-05-20 20:06

---

## 2026-05-20 (execute_data_query 专项优化)

**问题**：execute_data_query 调用 5 次共 125s（占 54%），根因：code_prompt 缺 Timestamp 序列化规则致失败重试 + Agent 主动拆句 + 无代码缓存 + 子进程冷启动。

**修改**：R1 code_prompt 新增日期转字符串+default=str 兜底；R2 agent prompt 增加合并统计/禁止拆句/失败先修代码等效率规则；R3 增 _code_cache 闭包缓存；R4 code_executor 新增 /execute_batch 批量端点。

**效果**：预期 5次→1-2次调用，125s→30-50s。

**时间**：2026-05-20 09:49

---

## 2026-05-20 (Trace 性能分析)

**问题**：trace_export.json 记录完整执行过程，总耗时 232.3s，需定位性能瓶颈。

**分析结果**：data_agent 占 89% 耗时（206.3s），execute_data_query 调用 5 次共 125s（54%）为最大瓶颈；rag_agent 未参与调用；61K prompt tokens 大量重复无缓存。

**优化方向**：P0 合并 data_query 调用（-50~75s），P1 文件缓存（-20s），P2 Prompt 精简（-30s），P3 LLM 缓存（-15s）。

**时间**：2026-05-20 09:22

---

## 2026-05-19 (RAG Agent 架构重构)

**问题**：`rag_agent.py` 使用 StateGraph 手动构建固定流水线（检索→验证→重试），Agent 无自主决策权，重试策略硬编码，`list_kb_documents` 定义但从未被调用（死代码）。

**重构内容**：将 rag_agent 从 StateGraph 改为 React Agent，与 data_agent 架构统一。
1. `rag_search` 工具升级：内置查询改写、回退检索、答案生成、验证和自动重试，Agent 通常只需调用一次
2. `list_kb_documents` 工具现在可被 Agent 自主调用（之前是死代码）
3. 删除 StateGraph、RagAgentState、所有节点函数和条件路由
4. Agent prompt 采用"工具说明+硬性约束"设计，与 data_agent 风格一致
5. 辅助函数提取为 `_retrieve_from_dify`、`_format_records`、`_log_records`、`_generate_answer`，职责单一
6. 更新测试脚本 `scripts/test_rag_retrieve.py`，适配 React Agent 的 messages 接口

**效果**：Agent 可根据问题复杂度自主决策工具调用顺序和次数，不再被固定流程限制。

**时间**：2026-05-19 14:20

---

## 2026-05-19 (第三轮修复)

**问题**：LLM 生成的代码中错误调用 `inspect_file()` 函数（这是 agent 工具，代码执行环境中不可用），导致执行失败后反复重试。同时 `max_iterations` 参数不被 `create_react_agent` 支持。

**修复内容**：
1. 给 `execute_data_query` 添加 `skiprows` 参数，agent 调用时直接传入已确定的 skiprows 值
2. 修改 `code_prompt`：使用 `skiprows={skiprows}` 硬编码值，不再引用 `inspect_file`
3. 新增规则：禁止在生成代码中调用任何 agent 工具
4. 移除不支持的 `max_iterations=10` 参数
5. 修改 agent prompt：要求调用 `execute_data_query` 时必须传入 `skiprows` 参数

**时间**：2026-05-19 13:49

**补充**：将 agent prompt 从"固定调用流程"改为"工具说明+硬性约束"设计，只约束运行环境的物理限制（不可违反），不约束 Agent 的思考方式（自由决策）。

---

## 2026-05-19 (第二轮修复)

**问题**：`agents/data_agent.py` 中 `execute_data_query` 生成的代码可能错误使用 `pd.read_csv()` 读取 Excel 文件（.xlsx/.xls），导致执行失败。加上缺少 `max_iterations` 限制，导致无限循环重试，消耗大量 token 和时间（592.84秒，418.1k token）。

**修复内容**：
1. 修改 `execute_data_query` 的 `code_prompt`：明确指定根据文件扩展名选择读取函数（.xlsx/.xls → `pd.read_excel()`，.csv → `pd.read_csv()`）
2. 修改 `multi_file_rules`：明确指定根据文件扩展名选择读取函数，并提供示例代码
3. 修改 ReAct agent 的 system prompt：新增严格要求，强调必须使用正确的读取函数
4. 添加 `max_iterations=10` 到 `create_react_agent`：防止无限循环

**效果**：Agent 将根据文件扩展名选择正确的读取函数，避免因错误读取导致的无限循环，显著提升响应速度并降低 token 消耗。

**时间**：2026-05-19 13:00 - 13:30

---

## 2026-05-19

**问题**：`agents/data_agent.py` 中 `inspect_file` 和 `execute_data_query` 硬编码 `skiprows=2`，假设所有 Excel 表头都在第3行，但实际表头位置不固定。

**修复内容**：
1. 修改 `inspect_file` 函数：读取原始前10行（`header=None`），返回原始内容让 LLM 判断表头所在行
2. 修改 ReAct agent 的 system prompt：新增规则要求根据 `inspect_file` 结果确定 `skiprows` 值
3. 修改 `execute_data_query` 的 `code_prompt`：删除硬编码 `skiprows=2`，改为动态提示
4. 修改 `multi_file_rules`：删除硬编码 `skiprows=2`，提示从 `inspect_file` 结果获取

**效果**：Agent 能自动识别不同 Excel 文件的表头行位置，不再依赖固定的 `skiprows=2`。

**时间**：2026-05-19 09:00 - 09:30

---

## 2026-05-18 (第二轮修复)

**问题**：检索已成功返回10条相关记录（最高分0.863），但 `AnswerVerify` 连续两次判断为 `INSUFFICIENT`，导致路由到 `no_answer_node`，前端显示"未找到"。

**根因分析**：
- `route_after_verify` 中 `INSUFFICIENT` 与 `HALLUCINATION` 同等对待，重试后都走向 `no_answer`
- `INSUFFICIENT` 表示有部分相关内容，不应等同于"未找到"
- 验证提示词过于严格，将不够全面的答案判定为 `INSUFFICIENT`

**修复内容**：
1. **修改路由逻辑**：`INSUFFICIENT` 重试后走向新的 `insufficient_done` 节点（展示部分答案+提示），而非 `no_answer`
2. **新增 `insufficient_done_node`**：输出部分答案并附加"可能不够完整"的提示
3. **放宽验证提示词**：只要文档与问题有相关性且答案基于文档生成，就判定为 `GOOD`；不再因不够全面而判定 `INSUFFICIENT`
4. **条件路由增加 `insufficient_done` 分支**

**效果**：即使答案不够完整，也会展示已有内容并提示用户，而非直接显示"未找到"。

**时间**：2026-05-18 23:15 - 23:30

---

## 2026-05-18

**问题**：Dify 知识库检索返回"未匹配"，即使知识库中存在相关文档（如"公司的核心价值观是什么"、"公司核心优势"等简单问题）。

**优化方法**：
- 在 `agents/rag_agent.py` 的 `rag_search` 函数中添加调试日志，打印查询、返回记录数、每个记录的分数和来源
- 调整检索参数：使用语义搜索（`semantic_search`）、禁用重排序（`reranking_enable: False`）、增加候选文档数（`top_k: 10`）、禁用分数阈值（`score_threshold_enabled: False`）
- 优化查询改写：在 `rewrite_query` 函数中添加短问题跳过逻辑（长度≤10字符或词汇数≤3的问题直接使用原始查询）
- 添加回退机制：当改写查询未找到记录时，自动使用原始查询重新检索
- 创建测试脚本 `scripts/test_rag_retrieve.py`，用于验证改进效果

**效果**：提高检索召回率，确保简单问题能够正确匹配知识库中的相关文档。

**时间**：2026-05-18 22:00 - 22:30

---

## 2026-05-18

**新增功能**：按照 PLAN.md 执行三个阶段改进。

**Phase 1 — 接入 LangSmith 可观测性 Tracing**：
- 在 `.env` 和 `.env.example` 中添加 LangSmith 配置（LANGCHAIN_TRACING_V2, LANGCHAIN_API_KEY, LANGCHAIN_PROJECT）
- 修改 `agent.py` 的 `chat()` 函数，注入 LangSmith metadata（user_id, conversation_id）
- 修改 `main.py`，调用 `chat()` 时传 `username="cli-user"`

**Phase 2 — RAG Query 改写**：
- 在 `agents/rag_agent.py` 中添加 `QUERY_REWRITE_PROMPT` 和 `rewrite_query()` 函数
- 修改 `rag_search` 工具，使用改写后的 `search_query` 进行检索
- 支持回退策略：改写失败时使用示例查询，保证主流程不中断

**Phase 3 — RAG 答案验证 + 重检索节点**：
- 在 `agents/rag_agent.py` 中添加 `ANSWER_VERIFY_PROMPT` 和 `verify_answer()` 函数
- 定义 `RagAgentState`（包含 messages, question, retrieved_context, answer, verdict, retry_count）
- 将 `create_rag_agent()` 从简单的 `create_react_agent` 改造为带验证分支的 StateGraph 子图
- 添加 4 个节点：`retrieve_and_answer_node`, `verify_node`, `retry_node`, `no_answer_node`
- 添加条件路由：`route_after_verify`（根据 verdict 和 retry_count 决定走向）
- 修改 `pages/chat_page.py`，无答案时显示橙色警告框

**时间**：2026-05-18 14:00 - 19:00

---

## 2026-05-17

**新增功能**：用户设置界面。为普通用户（user）添加简单的设置界面，包含基本信息显示、修改显示名称、修改密码等功能。

**实现方法**：
- 在 `auth/auth_service.py` 中添加 `update_password()` 和 `update_display_name()` 函数
- 修改 `pages/chat_page.py`：
  - 在侧边栏添加"用户设置"按钮
  - 添加 `show_settings` 状态控制设置界面显示
  - 创建 `_render_user_settings()` 函数渲染设置界面
  - 支持修改显示名称（实时更新 session）
  - 支持修改密码（需验证当前密码，新密码至少 6 位）

**时间**：2026-05-17 13:50 - 14:00

---

## 2026-05-15

**问题**：智能体处理用户问题时，同一个流程会执行两次（先 stream 收集日志，再 invoke 获取答案），导致所有 LLM 调用和工具执行都重复运行，回复缓慢。

**优化方法**：合并 stream 和 invoke 为单次 stream 执行。在流过程中同时收集步骤日志（steps_log）和所有消息（all_messages），流结束后从 all_messages 中提取最终答案，删除第二次 invoke 调用。

**效果**：响应速度提升约 50%，LLM 调用和工具执行只跑一次。

---

## 2026-05-15

**新增功能**：对话记录持久化。实现用户对话记录管理（新建/切换/删除），侧边栏改为对话列表布局，数据表采用单表设计（conversations + messages），每个对话使用独立 thread_id 隔离记忆。

**实现方法**：
- 数据库：在 `core/database.py` 新增 `conversations` 和 `messages` 两张表
- 数据服务：创建 `data/conversation_service.py` 实现 CRUD 操作
- 前端改造：`pages/chat_page.py` 侧边栏显示对话列表，支持切换/删除/新建对话
- 布局调整：`app.py` 移除原侧边栏导航，管理员入口移至 chat_page 侧边栏底部
- 记忆隔离：每个对话使用 `conversation-{id}` 作为独立 thread_id

**时间**：2026-05-15 13:00 - 14:00

---

## 2026-05-17

**新增功能**：管理员知识库管理界面。为 admin 用户新增"知识库管理"Tab，通过 Dify API 查看知识库列表及每个知识库内的文档列表。

**实现方法**：
- 创建 `data/dify_service.py` 封装 `list_datasets` 和 `list_documents` API 调用，支持分页和错误处理
- 修改 `pages/admin_page.py` 新增第三个 Tab"知识库管理"，使用 expander 展示知识库，dataframe 展示文档列表
- 支持知识库列表和文档列表独立分页
- 修改 `.env.example` 补充可选的 `DIFY_API_BASE` 配置说明（默认 `https://api.dify.ai/v1`）

**时间**：2026-05-17 12:40 - 13:00
