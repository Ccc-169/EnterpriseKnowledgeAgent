# 开发日志列表
:

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

**时间**：2026-05-20 20:42:

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
