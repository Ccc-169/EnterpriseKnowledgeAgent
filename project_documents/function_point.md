# 功能点清单

## 一、前端与接口层

- **HTML 静态前端**：五个独立 HTML 页面（login / home / admin / setting / more-features），无需 Node.js 构建，直接浏览器打开即用。
- **FastAPI REST 后端**：`api.py` 提供全套 REST 接口（:8000），与前端通过 JSON 和 SSE 通信，完全解耦于 Streamlit。
- **SSE 流式推送**：`/api/chat/stream` 使用 Server-Sent Events 实时推送 `init / step / answer / done / error` 五类事件，前端逐步显示推理过程。
- **JWT 认证**：登录后颁发 JWT token，存储于 `localStorage`，所有接口携带 `Authorization: Bearer <token>` 请求头；后端统一鉴权、过期自动重定向到登录页。
- **Streamlit 兼容层保留**：`app.py` 及 `pages/` 保留可用，供本地调试；新功能优先在 HTML + FastAPI 侧开发。

## 二、用户与权限

- **用户登录**：基于用户名密码的登录验证，密码使用 bcrypt 哈希存储；登录成功返回 JWT，前端缓存至 `localStorage`。
- **角色权限控制**：三种角色（admin / user / visitor），visitor 登录后仅提示无权限；admin 可访问管理后台。
- **会话管理**：JWT 有效期可配（默认 8 小时），过期或未携带 token 时返回 401，前端自动跳转登录页清除缓存。
- **个人账号管理**：用户可修改显示名称和密码，密码修改需验证旧密码且新密码至少 6 位。

## 三、对话功能

- **多轮对话**：基于 `thread_id`（`conversation-{对话ID}`）维护 MemorySaver 多轮对话记忆，上下文连贯。
- **对话记录持久化**：对话和消息分别存入 `conversations` 和 `messages` 表，刷新不丢失。
- **对话列表管理**：侧边栏展示所有对话，支持新建、切换、删除操作，按更新时间倒序排列。
- **智能标题生成**：新对话的首条消息由 LLM 自动提炼生成对话标题，非简单截断。
- **相对时间显示**：基于 UTC 时间对比计算"刚刚 / 分钟前 / 小时前 / 昨天"等相对时间，避免时区偏差。
- **消息详情记录**：每条消息同步保存 `steps_log`（工具调用步骤）和 `agent_used`（使用的智能体），刷新后可完整恢复。

## 四、智能体架构

- **Supervisor Router 路由分发**：接收用户问题，判断类型后转发给对应的 Sub-Agent，禁止修改/总结/补充 Agent 回答，原样返回。
- **RAG 文档问答 Agent**：内置查询改写、回退检索、答案验证和自动重试，调用 Dify 知识库 API 做语义搜索。
- **数据分析 Agent**：四工具流水线（`lookup_schema` → `list_files` → `inspect_file` → `execute_data_query`），命中模板时跳过文件探查直接生成代码；自然语言转 Python 代码后在沙箱执行。
- **文档编写 Agent**：四工具组合（`search_knowledge_base` → `generate_document_outline` → `generate_document_content` → `improve_document_outline`），支持逐章节分段生成降低单次请求压力。
- **直接调用模式**：`chat_direct()` 绕过 Router 直接指定 Sub-Agent，用于文档编写等需要精确控制的场景；`doc_agent` 始终通过 `chat_direct` 调用，不参与 Router 路由。
- **工具调用日志**：记录 Agent 调用的工具名称、参数和返回结果摘要，可展开查看推理过程；`transfer` 类内部转发已过滤。

## 五、RAG 文档功能

- **查询改写**：LLM 将口语化问题改写为适合向量语义检索的形式，输出 `rewritten_query + keywords + sub_questions`；短问题（≤10 字或 ≤3 词）自动跳过改写。
- **知识库检索**：调用 Dify API 的 `semantic_search` 方法，top_k=10，返回文档原文片段及来源文件名。
- **回退检索**：改写查询无结果时自动使用原始查询回退检索，避免改写损失关键信息。
- **答案验证**：LLM 审核答案质量，返回 `GOOD / HALLUCINATION / NO_CONTEXT / INSUFFICIENT` 四种裁决。
- **自动重试**：`HALLUCINATION` 或 `INSUFFICIENT` 时自动换表达重新检索（最多 1 次），`NO_CONTEXT` 时直接告知用户未找到。
- **答案后校验**：规则引擎对生成答案做质量检查，仅对裸技术错误信息做替换，非阻断式仅日志记录。
- **文档列表查询**：分页遍历 Dify 知识库文档列表，显示索引状态（✓已完成 / ⏳处理中），支持关键词过滤。

## 六、数据分析功能

- **数据模板快速路径**：`lookup_schema` 工具优先查询 `project_documents/data_schema.json` 中已登记的文件模板；命中时直接调用 `execute_data_query`，跳过 `list_files` + `inspect_file`，减少约 2 次工具调用和 ~20s 等待。
- **文件列表查询**：扫描 `DATA_DIR` 目录，列出所有 `.xlsx/.xls/.csv` 文件及完整路径。
- **文件结构检查**：读取原始前 10 行（不指定 header），由 LLM 自行判断表头行号（`skiprows=N`），同时提供参考列名和数据类型。
- **代码生成缓存**：以 `(file_path, skiprows, query)` 为 key 缓存生成的代码，同一组合不重复调用 LLM。
- **硬编码文件名兜底**：正则自动替换 LLM 偶尔硬编码的文件名为 `DATA_PATH` 变量，避免沙箱找不到文件。
- **自然语言统计**：中文描述统计需求，LLM 按模板生成 Python 代码，在预热进程池中执行并返回 JSON 结果。
- **多文件合并分析**：逗号分隔多个文件路径，自动注入 `_source_file` 列标记来源，合并后统一统计。
- **批量执行优化**：优先使用 `/execute_batch` 端点（多代码块共享预热进程），失败回退 `/execute`。
- **HTTP 连接复用**：`requests.Session()` 单例复用 TCP 连接，消除重复建连开销。
- **代码安全校验**：规则引擎仅拦截 `os.system / eval / subprocess` 等 CRITICAL 危险调用，安全操作不阻断。

## 七、文档编写功能

- **三步式向导 UI**：嵌入 `home-page.html` 的仿写模式，流程步骤指示器（输入需求 → 确认目录 → 生成文档），切换模式即进入流程，无需跳转页面。
- **参考附件上传**：支持 `.txt/.md/.docx/.pdf/.xlsx/.csv` 等多格式文件上传，提取文本内容作为撰写参考。
- **知识库检索参考**：`doc_agent` 自动从 Dify 知识库检索相关制度文档片段，标注来源后注入文档生成上下文。
- **目录智能生成**：LLM 根据需求描述和参考上下文生成多级编号目录（含章节说明），支持回退修改。
- **目录交互编辑**：生成目录放入可编辑文本区，用户可自由修改、增删章节后确认。
- **逐章节分段生成**：解析目录提取一级章节及其下属二级标题，逐个调用 LLM 生成，降低单次请求压力并支持长文档。
- **前后文衔接**：每章生成时传入前两章已生成内容，确保文档逻辑连贯、前后呼应。
- **自动保存与对话同步**：文档生成后自动存入数据库，同时创建侧边栏对话记录便于回溯。
- **一键复制与源码查看**：文档展示区嵌入复制按钮（Clipboard API + `execCommand` 双重兜底），支持展开查看 Markdown 源码。
- **多轮迭代**：支持重新生成、修改目录重来、返回修改需求重新开始。

## 八、代码沙箱

- **进程池预热**：启动时通过 `multiprocessing.Pool` 创建 N 个 Worker，每个 Worker 初始化时预加载 pandas，消除冷启动开销。
- **安全隔离执行**：代码在独立子进程中 `exec`，namespace 隔离（仅暴露 `pd / json / os / DATA_PATH`），stdout 捕获。
- **超时保护**：`apply_async().get(timeout=30)`，超时即返回错误，防止死循环阻塞系统。
- **批量执行**：`/execute_batch` 端点接受多个代码块，用分隔符合并后在共享进程中执行，输出按分隔符拆分回传。
- **生命周期管理**：FastAPI `lifespan` 上下文管理进程池的创建与销毁，优雅关闭。

## 九、规则引擎

- **YAML 配置驱动**：规则集通过 `rule_config.yaml` 定义，支持规则启用/禁用、分类、严重级别（CRITICAL / WARNING / INFO）。
- **多阶段检查**：输入阶段（`pre_generate`）防提示词注入，代码阶段（`pre_execute`）拦截危险操作，答案阶段（`post_retrieve`）做质量校验。
- **LLM_CHECK 规则**：支持将自然语言规则交由 LLM 判定合规性，引擎对检查异常容错（默认通过）保证主流程不中断。
- **柔性拦截策略**：仅 CRITICAL 级别违规阻断流程，WARNING / INFO 级别仅日志记录不阻断。
- **全局单例管理**：规则引擎懒加载初始化，`agent.py` 启动时注入 LLM 检查器，全系统复用同一实例。

## 十、管理员功能

- **用户管理**：管理员可新建用户、修改角色（visitor / user / admin）、启用/禁用账号。
- **审计日志查询**：按用户名、操作类型、日期范围筛选日志，展示登录、对话、管理操作记录。
- **统计摘要**：仪表盘展示用户总数、今日活跃用户数、今日对话数。
- **知识库管理**：分页浏览 Dify 知识库列表及文档列表，显示文档数量、索引状态、命中次数等信息。

## 十一、审计与日志

- **操作记录**：所有登录、登出、对话、文档编写、管理操作均写入 `audit_logs` 表，包含用户名、操作类型、使用的 Agent、问题内容、状态。
- **对话失败记录**：Agent 执行出错时审计日志标记 `status=error`，便于排查问题。
- **细粒度操作类型**：区分 `chat / doc_outline_generate / doc_generate / update_password / update_display_name` 等多种操作类型。

## 十二、LLM 与可观测性

- **主模型配置**：阿里千问 `qwen-plus`，temperature=0，max_tokens=8192，timeout=300s，max_retries=2。
- **本地 Ollama 备选**：代码保留 Ollama 本地模型接入配置，注释切换即可启用。
- **LLM 调用重试**：`doc_agent` 对 `APIConnectionError` 做指数退避重试（最多 3 次），提升生成稳定性。
- **LangSmith Tracing**：Router 和 `chat_direct` 均注入 `user_id` 和 `conversation_id` 元数据，支持按用户/对话筛选 Trace。
- **recursion_limit 控制**：Agent 图谱递归上限设为 50，防止无限循环。

## 十三、Agent 注册与权限

- **Agent 注册表**：`AGENT_REGISTRY` 集中管理所有 Agent 的名称、描述、所需角色、启用状态，便于扩展。
- **角色级访问控制**：`can_use_agent()` 运行时校验用户角色是否有权使用指定 Agent，visitor 完全拦截。
- **预留扩展点**：注册表支持注释扩展示例，未来添加新 Agent 无需修改 `agent.py`。

## 十四、文件解析

- **多格式支持**：统一入口 `extract_file_content()` 根据扩展名自动分派解析器，支持 `.txt / .md / .py / .csv / .json / .yaml / .log / .docx / .pdf / .xlsx`。
- **编码兼容**：文本类文件优先 UTF-8 解码，失败回退 GBK。
- **长度截断**：提取内容超过 8000 字符时自动截断并标注原始总字符数。
- **友好错误提示**：解析失败时返回具体错误原因，不阻塞主流程。
