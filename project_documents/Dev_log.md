# 开发日志列表
:

## 2026-07-23 (RAG Agent Q&A 缓存优化)

**背景**：用户每次相同或相似问题都要走完整 RAG 链路（检索 + LLM 生成），耗时约 26s，相同问题无缓存复用，token 和响应时间浪费严重。

**功能**：

1. **新增 Q&A 向量缓存机制**（`data/cache_service.py`）：
   - 新建 `qa_cache` SQLite 表（id, question, question_vec, answer, kb_version, hit_count, created_at, last_hit_at）
   - 每次回答后自动写入缓存，后续相同/相似问题走向量相似度匹配，三级置信度决策：
     - **High (≥0.90)**：直接短路，跳过 RAG + LLM，0.5s 返回缓存答案
     - **Med [0.85, 0.90)**：参考骨架（保留）
     - **Min [0.80, 0.85)**：候选参考
   - 千问 API 做文本向量化（1024 维）
   - 新增 `cache_debug.log` 详细记录每次检查的相似度分数和决策过程

2. **缓存清理策略**（`data/cache_service.py`）：
   - 数量上限：维持 **1000 条**，超出删除最久未命中的
   - 时间上限：超过 7 天未命中自动清理
   - 写入后 20% 概率触发清理，避免每次全表扫描

3. **KB 指纹变化自动清理**（`data/kb_version.py`）：
   - `compute_kb_fingerprint` 检测到 RAGFlow 文档变化时，自动 `DELETE FROM qa_cache WHERE kb_version != '新指纹'`
   - 同指纹去重，避免反复清理

4. **检索性能优化**（`core/database.py`）：
   - `qa_cache` 表新增 `last_hit_at` 索引，加速时间维度清理查询

5. **LangSmith 观测精简**：
   - 移除 `compute_kb_fingerprint`、`embed_text`、`save_qa_cache_entry` 三个函数的 `@traceable` 装饰器，减少 trace 中非必要 span

6. **缓存命中率优化**：
   - High 短路阈值从 **0.95 → 0.90**

**效果验证**（trace 对比）：

| 指标 | 第一次（无缓存） | 第二次（缓存命中） | 变化 |
|---|---|---|---|
| 总耗时 | ~26.47s | **~0.55s** | **↓ 98%** |
| short_circuit | false | **true** | — |
| LLM tokens | 3820 | **0** | **↓ 100%** |
| 执行链路 | cache_check→rewrite→retrieve→generate→post_check（5 节点） | **cache_check→post_check（2 节点）** | 跳过 3 个节点 |

**修改文件**：`data/cache_service.py`、`data/kb_version.py`、`core/config.py`、`core/database.py`、`api.py`、`agents/rag_agent.py`、`pages/chat_page.py`、`get-think-chain.py`、`data/cache_debug.log`（新建）、`view_qa_cache.py`（新建、临时观测用）

**时间**：2026-07-23

---

## 2026-07-21 (数据文件管理功能 + 修复多处 BUG)

**背景**：管理员在服务器上放置 Excel/CSV 数据文件供 data_agent 使用非常不便（需手动连接服务器将文件放到 DATA_DIR 目录）。希望在前端提供可视化上传/删除功能，且仅管理员可用。

**功能**：

1. **后端新增 2 个 API 端点**（`api.py`）：
   - `POST /api/admin/data-files/upload` — 上传 Excel/CSV，限制类型(.xlsx/.xls/.csv) + 大小 100MB + 路径穿越防护；`overwrite=false` 时同名返回 409（前端弹窗询问覆盖），`overwrite=true` 直接覆盖。
   - `DELETE /api/admin/data-files/{filename}` — 删除指定文件。
   - 辅助函数：`_resolve_data_dir()`（自动创建目录）、`_sanitize_data_filename()`（防路径穿越）。

2. **新建独立页面 `data-files-page.html`**：
   - 完整侧边栏 + 工具栏（上传/刷新按钮 + 路径显示 + 提示文字）。
   - 文件列表表格（类型标签 + 文件名 + 大小 + 操作列）。
   - 上传流程：点击上传 → 文件选择器 → 检测同名（弹窗询问覆盖/取消）→ 上传 → 自动刷新列表。
   - 删除流程：点击删除 → 确认弹窗 → DELETE 请求 → 刷新列表。
   - 权限：仅管理员可见上传/删除按钮、侧边栏「数据文件」菜单项；普通用户直接 403 跳转首页。

3. **侧边栏权限控制**（8 个 HTML 页面）：
   - 所有页面新增「数据文件」菜单项，默认 `display:none`，`initPage()` 中 `role === 'admin'` 时才显示。
   - `admin-page.html` 中「本地数据文件」子 section 改为跳转卡片，跳转到新独立页面。

**修复**：

1. `EXECUTOR_URL` 配置错误：`.env` 中 `EXECUTOR_URL=http://localhost:28001/execute` 末尾多 `/execute`，导致 data_agent 拼出 `/execute/execute_batch` 404；已改为 `http://localhost:28001`。
2. `home-page.html` 管理员菜单项重复：之前的批量替换导致多出一组 admin-item，已清理。
3. 各页面 HNGD logo SVG 无显式 width/height，依赖 CSS 约束，渲染异常时出现巨大默认图标（300×150px）；已给全部 SVG 加上 `width="20" height="20"`。
4. 移除之前误插入的 inline `<script>`（在 `</nav>` 后紧贴放置，破坏 flex 布局）。

**性能分析**：分析 `trace_export.json`（data_agent 88.6s），`execute_data_query` 工具占 66.53s（75%），首次 LLM OLLAMA 冷启动 14.57s。

**修改文件**：
- `api.py`、`html_files/data-files-page.html`（新建）、`html_files/admin-page.html`、`html_files/home-page.html`、`html_files/knowledge-base-page.html`、`html_files/data-analysis-page.html`、`html_files/more-features-page.html`、`html_files/interface_config.html`、`html_files/setting-page.html`、`.env`
- `project_documents/Dev_log.md`（本日志）

**时间**：2026-07-21

---

## 2026-07-16 (api_agent 接口导入热重载改造)

**背景**：前端在前端"接口配置"页面导入近 50 个真实数据接口后，api_agent 提问时只能识别到 22 个（来自 trace 实际返回数），必须重启后端服务才能让新接口生效，影响使用体验。

**根因**：
- `agents/api_agent.py` 原本在 `create_api_agent()` 时一次性扫描 `data_interface/` 目录，把 `apis` / `api_map` 闭包到 `list_available_apis` 和 `call_real_api` 两个工具里——**进程启动后再修改磁盘 JSON 文件，agent 不会重新读取**。
- 前端"接口配置"走 `data/interface_service.py` 的 `import_*` / `delete_*` 写入流程，仅修改磁盘文件 + SQLite `data_interfaces` 索引表，没有任何机制通知 api_agent 刷新缓存。
- 架构上的"双数据源不一致"——前端展示来自数据库 `data_interfaces` 表，api_agent 工具来自文件系统 `data_interface/*.json`，两者同写不同读。

**方案**（2 个文件，无新增/删除文件）：

1. **`agents/api_agent.py` — 缓存机制 + 工具改用惰性加载**
   - 顶部新增模块级缓存 `_api_cache = {"specs", "apis", "api_map", "loaded_at"}` + 线程锁 `_cache_lock`，TTL `_API_CACHE_TTL = 30.0` 秒。
   - 新增 `invalidate_api_cache()` 公开失效函数（清空缓存 + 重置 `loaded_at`，下次工具调用时自动重读磁盘）。
   - 新增 `_get_apis()` 内部加载函数：先检查 TTL，未过期复用缓存；过期或缓存为空时调用 `_load_all_specs()` + `_parse_apis_from_specs()` 重建。
   - `create_api_agent()` 改为不再闭包 `apis`/`api_map`，仅启动时调一次 `_get_apis()` 预热（让启动日志可见 `[api_agent] 已加载 N 个规范，共 M 个接口`）。
   - `list_available_apis` 工具开头加 `apis, _ = _get_apis()`；`call_real_api` 工具开头加 `_, api_map = _get_apis()`——两者不再捕获闭包，每次调用前实时拿最新数据。

2. **`data/interface_service.py` — 写入/删除入口加失效钩子**
   - 顶部新增内部辅助函数 `_invalidate_api_cache()`，内部 `try: from agents.api_agent import invalidate_api_cache; invalidate_api_cache(); except Exception: pass`——`try` 包裹：纯管理脚本（如 `scripts/import_swagger_specs.py`）即便 api_agent 因依赖未就绪 import 失败也不应阻断主流程。
   - 在 7 个函数末尾加调用：`sync_data_interfaces_index`、`import_selected_tags`、`import_from_swagger_url`、`import_from_json_content`、`delete_single_interface`、`delete_interface_file`、`delete_service_directory`。每个早 return 路径（"未找到"/"参数校验失败"等不修改磁盘的路径）正确跳过失效调用——只对真正改了文件或索引的路径生效。

**关键取舍**：
- `invalidate_api_cache()` 只清**当前 Python 进程**内的缓存；跨进程场景（如 `scripts/import_swagger_specs.py` 命令行导入后 Streamlit 没重启）→ 靠 30s TTL 兜底自动刷新。如果部署了多 uvicorn worker，每个 worker 各自维护缓存，最迟 30s 内也会自刷新。
- 端到端验证：写了 5 项测试覆盖"首次加载 / 新增文件+invalidate / TTL 内复用 / TTL 过期自动重读 / 删除文件+invalidate"，全部通过后已清理测试脚本，磁盘 `data_interface/` 保持原状。

**后续建议**（不在本次改动范围）：
- 重启当前 Linux 后端的 Streamlit 服务，让进程首次加载到 109 个接口（热重载只对"导入后的新调用"生效，老进程内存里仍是 22 个）。
- 删除 `data_interface/test/Message.json`（与 `消息中心/消息控制器.json` 内容完全重复，浪费 6 个槽位）。
- 关键词细化检索优化（已讨论设计，待确认后实施）：把 `list_available_apis` 改为"概览+关键词检索"双模式，解决 LLM token 爆炸问题。

**修改文件**：`agents/api_agent.py`、`data/interface_service.py`

**时间**：2026-07-16

---

## 2026-06-18 (Agent 回复气泡增加白色卡片效果)

**问题**：Agent（AI）回复消息气泡使用 `background: #f4f7fc` 极浅蓝灰背景，在页面灰色背景下视觉上几乎透明，与用户深蓝色消息缺乏明显对比。

**方案**（仅改 `html_files/home-page.html` 的 `.msg-row.ai .msg-bubble` CSS，5 处属性调整）：
- `background: #f4f7fc` → `background: #ffffff`（纯白背景）
- `border: 1px solid #e4ecf5` → `border: 1px solid #dce4ee`（边框略深增强轮廓）
- 新增 `box-shadow: 0 1px 6px rgba(26,58,110,0.08)`（轻微阴影提升层次感）
- `padding: 9px 13px` → `padding: 12px 16px`（稍增内边距让卡片更舒展）

**效果**：Agent 回复呈现为明显的浅白色卡片，与用户发送的深蓝色渐变消息形成清晰的"白 vs 蓝"视觉对比。

**修改文件**：`html_files/home-page.html`

**时间**：2026-06-18

---

## 2026-06-18 (聊天消息区域去除边框卡片效果)

**问题**：`.chat-messages` 区域有白色背景 + 1.5px 蓝灰边框 + 12px 圆角，在灰色页面背景上形成明显的"白卡片框"视觉效果，非常突兀。

**方案**（仅改 `html_files/home-page.html` 的 `.chat-messages` CSS，4 处属性调整）：
- `background: white` → `background: transparent`
- `border-radius: 12px` → `border-radius: 0`
- `border: 1.5px solid #d8e4f0` → `border: none`
- `padding: 16px` → `padding: 20px 32px`（与 `.home-body` 水平 padding 对齐）

**效果**：聊天消息区域不再显示为浮于页面上的独立卡片，而是与页面背景自然融合，消息气泡自身背景色足以区分内容。

**修改文件**：`html_files/home-page.html`

**时间**：2026-06-18

---

## 2026-06-18 (首页聊天区扩展——对话开始时隐藏欢迎区)

**问题**：首页聊天区域被顶部问候语（"上午好 XX"）+ 4 张功能卡片（知识问答/数据分析/仿写创作/更多功能）占据约 40% 空间，`.chat-messages` 还硬编码了 `max-height: 320px`，导致聊天区被严重截断。

**方案**（仅改 `html_files/home-page.html`，2 处修改）：
1. **CSS**：新增 `.home-body.chat-active` 状态类——激活时 `.greeting-section` 和 `.feature-cards` 设为 `display: none`，`.chat-messages.visible` 去掉 `max-height` 限制改为 `flex: 1; min-height: 0` 撑满剩余空间。
2. **JS**：在 `updateChatMessagesVisibility()` 末尾追加一行 `document.querySelector('.home-body').classList.toggle('chat-active', hasContent)`，复用已有调用链（appendMessage / appendAiShell / appendTyping / removeTyping / sendChat），无需额外改动调用方。

**效果**：
- 有对话内容时：问候语+卡片自动隐藏，聊天区填满整个上半部分。
- 新建/清空对话时：欢迎区自动恢复。
- 文档模式不受影响（由 `switchMode` 独立控制 `doc-panel`）。

**修改文件**：`html_files/home-page.html`

**时间**：2026-06-18

---

## 2026-06-14 (修复 rag_search 重复调用 28 次)

**背景**：上一轮 Router 循环修复后，trace 显示同一问题 rag_search 仍被调用 28 次（同一查询词、同一 tool_call id `call_ohykswt4` 出现 15 次），耗时 66 秒、消耗 246k token。

**根因**：双层叠加导致 ReAct 反复重放历史工具调用。
1. `chat_direct` 的 `config["configurable"]["thread_id"]` 用的是业务 `thread_id`（如 `conversation-13`），SqliteSaver 每次调用都会加载该 thread 上一轮留下的 checkpoint（含带 `tool_calls` 的 AIMessage + ToolMessage），然后与 `_build_messages_with_history` 手动注入的历史**叠加合并**。
2. LangGraph ReAct 循环看到 checkpoint 里"未处理完"的 tool_call → 重新执行 rag_search → 得到相同结果 → 再次认为未完成 → 循环 28 次。
3. `parallel_tool_calls=False` 和 `recursion_limit=18` 均无法拦截（前者只管单轮并发，后者每次重放也算正常步骤）。

**方案**（`agent.py` 两处修改，合计 ~10 行）：
- `_build_messages_with_history`：历史 AIMessage 注入时显式加 `tool_calls=[]`，防止被 ReAct 识别为未完成调用（防御层）。
- `chat_direct` 的 checkpoint thread_id 改为每次请求唯一（`thread_id:uuid8`），SqliteSaver 无旧状态可加载，彻底切断重放来源（隔离层）。多轮记忆职责完全归 `_build_messages_with_history` + 业务 DB，两者职责清晰分离，不再双轨叠加。

**预期效果**：同一问题 rag_search 从 28 次降至 1 次，耗时从 66 秒降至约 10 秒，token 消耗大幅下降。

**修改文件**：`agent.py`

**时间**：2026-06-14

---

## 2026-06-14 (修复 Router 路由失控死循环)

**背景**：生产 trace（问题"HN-CSMP 智能体需求一期内容分类总结"）显示一次提问触发 98 次 LLM 调用、28 次重复检索、supervisor↔rag_agent 互相交接 106/86 次、耗时 114 秒、消耗 70 万 token，最终用户只收到报错 `执行失败：'NoneType' object has no attribute 'get'`。第一次 rag_search 其实已返回完整正确答案，但系统未收口。

**根因**：
1. 主因——rag 模式走 `create_supervisor` 的循环编排：每次子智能体交回控制权后都重新唤起 supervisor 的 LLM 决策，是否终止完全托付给模型自觉。qwen3.6:35b（本地中等模型）无视 prompt 的"最多两次转发"约束，无限横跳，且单轮一次吐出多个 transfer（`Send` 并行派发）放大失控。
2. `node_data` 可能为 None（纯路由帧无 state 更新），消费代码 `node_data.get("messages")` 崩溃 → 即前端那句报错。
3. `recursion_limit=50` 唯一硬兜底，过高，单卡下放任跑近 2 分钟。

**方案**（前端模式直派 + 多层熔断/防御，仅改 `api.py`、`agent.py`）：
- 前端"知识库检索"(rag) 模式从 `chat()`（走 supervisor）改为 `chat_direct("rag_agent")`。改后前端四模式（rag/data/write/api）全部直派 `chat_direct`，"前端选哪个、后端调哪个"，前端路径不再调用 supervisor，横跳从根上消除。
- `recursion_limit` 50 → 18（`agent.py` 两处），子 agent 内部 ReAct 失控时 18 步内熔断。
- llm 构造加 `model_kwargs={"parallel_tool_calls": False}`（已实测 Ollama 返回 200 兼容），禁止单轮并行工具调用，堵住"重复检索/多重交接"放大器。
- 两处 stream 消费循环 `node_data.get(...)` → `(node_data or {}).get(...)`，防御 None chunk。

**取舍**：CLI(`main.py`)、Streamlit(`pages/chat_page.py`) 仍走 `chat()`/supervisor（选项 A，本次不改其调用方式），但 recursion_limit=18、parallel_tool_calls=False、None 防御对其同样生效，失控时 18 步内熔断、不会再拖 2 分钟。supervisor `router` 对象保留不删，仅前端不再调用，改动面最小、可回退。

**修改文件**：`api.py`、`agent.py`

**时间**：2026-06-14

---

## 2026-06-14 (对话任务可取消 + 并发闸门 + 等待计时)

**背景**：本地 Ollama 以 `-np 1` 启动，全系统任意时刻只能生成 1 条回复。原实现下用户切页/删对话/反复新建后，后台 agent 任务仍在跑且无并发控制，一个"幽灵任务"即独占唯一生成槽，拖垮所有真实用户（详见 `problem_document/problem_record_5.md`、`plan.md`）。

**功能**：
1. 对话生成可协作式取消（切页、点停止、删除正在生成的对话均真正中断后台任务）。
2. 应用层唯一生成槽信号量闸门，对齐 `-np 1`，排队有序并显示"前方 N 人"。
3. 客户端断开自动取消，资源（信号量/注册项/线程/定时器）全路径回收，无泄漏。
4. 等待计时：思考中实时显示"已等待 X.X 秒"，回复结束在该条消息底部定格"用时 X.X 秒"徽章，减少干等待体感。

**方案**：
- 配置：`core/config.py` 新增 `CHAT_MAX_CONCURRENCY`（默认 1）、`CHAT_CANCEL_ON_DISCONNECT`、`CHAT_THREAD_POOL_SIZE`、`CHAT_DISCONNECT_POLL_SEC`，全部 env 可调，便于回滚。
- 取消注册中心：新建 `core/chat_registry.py`，维护 `dict[user_id -> threading.Event]`，`register` 自动 set 旧事件实现单飞，`unregister` 仅删本事件避免误删新任务，提供 `cancel`/`waiting_count`。
- 协作式取消：`agent.py` 的 `chat` / `chat_direct` 新增 `cancel_event=None` 参数（默认值保证文档/CLI/Streamlit 等现有调用零影响），两处 `stream` 循环顶部插 `if cancel_event and cancel_event.is_set(): break`，复用已有"提取已收集答案"逻辑。
- 闸门与断开检测：`api.py` `/api/chat/stream` 注入 `Request`，模块级 `asyncio.Semaphore(CHAT_MAX_CONCURRENCY)`；进槽前推送 `queued` 位次；进槽后 `create_task` 跑线程并按 `CHAT_DISCONNECT_POLL_SEC` 轮询 `request.is_disconnected()`，断开则 set 事件、`await task` 等线程在 chunk 边界收尾再释放槽；`try/finally` 中 `unregister`。新增 `POST /api/chat/stop`。落库前 `get_conversation` 校验，孤儿对话不写库，取消任务不写库。启动时设置线程池上限。
- 前端：`home-page.html` 发送按钮加 `id` + 停止态 `.is-stopping`（红灰渐变，布局零位移），`sendChat` 加 `AbortController`，新增 `stopChat()`；处理 `queued` 事件显示排队提示；`beforeunload`(keepalive) + 切对话/新建/删对话钩子触发 `stopChat`，落实"切页即取消"。等待计时：`startWaitTimer`/`stopWaitTimer`/`renderWaiting`/`elapsedStr` 每 200ms 刷新，`appendAiShell` 新增 `usedSec` 参数渲染"用时"徽章，`finally` 无条件停表防泄漏。

**关键取舍**：
- 切页即取消是有意取舍——回到对话页只能看到部分内容或无回复，换取不被幽灵任务拖垮。
- 取消只在 chunk 边界生效，单个 LLM 长请求内部仍不可中断（架构固有限制）。
- 等待计时为前端端到端耗时，仅实时会话显示，历史重载不显示（DB 未存耗时字段）。
- 本改动解决"队列有序、不被拖垮"，解决不了"单卡一次只能生成一条"的物理瓶颈，50 人流畅需运维降上下文换槽或上 vLLM。

**修改文件**：`core/config.py`、`core/chat_registry.py`（新建）、`agent.py`、`api.py`、`html_files/home-page.html`、`problem_document/plan.md`（新建）

**时间**：2026-06-14

---

## 2026-06-12 (服务地址统一配置)

**功能**：消除项目中所有硬编码服务地址，实现换部署环境只需修改两个文件。

**方案**：
- 后端：`core/config.py` 新增 `RAGFLOW_API_BASE`、`RAGFLOW_API_KEY`、`RAGFLOW_DATASET_ID`、`DIFY_API_BASE` 统一导出，消除 `rag_agent.py`、`doc_agent.py`、`kb_search.py`、`ragflow_service.py`、`dify_service.py` 中各自散落的 `os.environ.get()` 调用。
- 前端：新建 `html_files/config.js`，声明 `window.APP_CONFIG = { api_base, alarm_base }`，作为前端唯一配置文件。9 个 HTML/JS 文件引入该文件并替换硬编码常量。
- `more-features-page.html` 的嵌入代码示例改为函数 `_eCodes()` 动态拼接，展示给用户的复制代码随配置自动更新。
- `.env` 顶部新增服务地址区块；`.env.example` 重构，将服务地址配置提到最前并注明前端配置入口。

**换环境操作**：修改 `.env` 中的 `RAGFLOW_API_BASE`、`EXECUTOR_URL`，以及 `html_files/config.js` 中的 `api_base`、`alarm_base`，其余文件无需改动。

**修改文件**：`core/config.py`、`agents/rag_agent.py`、`agents/doc_agent.py`、`data/kb_search.py`、`data/ragflow_service.py`、`data/dify_service.py`、`html_files/config.js`（新建）、`html_files/login-page.html`、`html_files/home-page.html`、`html_files/admin-page.html`、`html_files/setting-page.html`、`html_files/interface_config.html`、`html_files/more-features-page.html`、`html_files/chat-embed.html`、`html_files/chat-ball.js`、`html_files/implant_test.html`、`.env`、`.env.example`

**时间**：2026-06-12

---
---

## 2026-06-15 (接口导入支持自定义 openapi-ui 智能探测 + 按标签选择导入)

**背景**：此前"从 Swagger URL 导入"仅支持标准 Swagger 端点（`/v3/api-docs`、`/v2/api-docs`、`/swagger.json`、`/api-docs`），无法适配公司内部基于自定义 openapi-ui（`/api/document`）的服务。这类系统以"服务→标签→接口"三层结构组织，一个地址下可能有数十个标签，此前用户无法导入。

**功能**：
1. 智能端点探测：自动识别标准 Swagger 和自定义 openapi-ui 两种模式。
2. 服务-标签选择弹窗：自定义模式下弹窗展示所有服务及其标签，支持全选/取消全选/按需勾选。
3. 按标签精确导入：用户选中标签后，逐标签下载 OpenAPI 规范并索引入库。

**方案**（`data/interface_service.py` 新增 2 个函数、改造 1 个函数；`api.py` 新增 2 个端点；`html_files/interface_config.html` 新增弹窗 UI）：
- **`discover_swagger_services()`**：两阶段探测——先依次拼标准路径（`/v3/api-docs` 等）；全部失败则 `GET /api/document`，若返回 `{"data": [{"title": ..., "tags": [...]}]}` 则为自定义模式，直接拿到全量服务-标签元数据的目录。
- **`import_from_swagger_url()` 改造**：三路分支——标准命中→全量导入（行为不变）；自定义命中→返回 `type="custom_select"` + `services` 列表，由前端接管；都失败→报错。
- **`import_selected_tags()`**：接收用户勾选的 `[{query, tag_name, tag_desc}]`，对每个标签请求 `GET /api/document/content/{query}` 下载完整 OpenAPI JSON，验证后保存到 `data_interface/{service_name}/{tag_name}.json`，解析 endpoints 写入 SQLite 索引。
- **前端弹窗**：`modal-service-select` 按服务分组渲染标签行、自定义 checkbox 交互；`tagLookupMap` 查找表避免 onclick 传参被特殊字符破坏；`selectAllTags`/`deselectAllTags` 一键全选/取消；`submitSelectedTags` 调用新端点 `/api/admin/interfaces/import-selected-tags`。
- **API 端点**：新增 `POST /api/admin/interfaces/discover-services`（公开探测）、`POST /api/admin/interfaces/import-selected-tags`（按标签导入）。

**关键取舍**：
- 自定义模式不自动全量导入——一个服务可能有几十个标签、数百个接口，用户按需选择避免信息过载。
- 标签导入时分文件独立保存，而非合并为一个文件——每个标签对应一个 `.json`，便于后续按标签管理/删除。
- `tagLookupMap` 用 `data-tag-key` 属性传 key 而非直接写在 onclick 参数中，防御标签名含引号/尖括号导致的 HTML 注入风险。

**修改文件**：`data/interface_service.py`、`api.py`、`html_files/interface_config.html`

**时间**：2026-06-15


## 2026-06-10 (接口配置页参数类型列)

**功能**：接口配置页 Params 面板新增"类型"列，支持为每个参数指定数据类型；已配置接口的参数加载时自动显示类型。

**方案**：
- Params 行从 5 列扩为 6 列（checkbox | 参数名 | **类型** | 参数值 | 说明 | 删除），grid 更新为 `18px 1fr 90px 1fr 1.4fr 26px`。
- 类型下拉选项：`string`、`int`、`float`、`bool`、`list`、`object`、`any`，蓝色 monospace 样式与系统统一。
- 旧数据兼容：无 `type` 字段时自动 fallback 为 `string`，打开旧接口不报错，保存一次后自动补全。
- 数据模型扩展：`params` 数组每项新增 `type` 字段，随整体 JSON blob 持久化，无需后端改动。
- 导入格式示例同步更新，展示带 `type` 字段的参数写法。

**修改文件**：`html_files/interface_config.html`

**时间**：2026-06-10

---

## 2026-06-10 (管理员界面删除用户功能)

**功能**：管理员界面"用户管理"新增删除用户，级联清除该用户的全部历史数据，需二次确认。

**方案**：
- 删除入口置于"编辑用户"弹窗底部的危险操作区（非表格行内），减少误触风险。
- 当前登录账户自动隐藏删除入口，防止管理员自删。
- 删除确认弹窗要求管理员手动键入目标用户名后"确认删除"按钮才激活，为最强防误触机制。
- 级联删除顺序：messages → conversations → audit_logs → document_history → users，单事务保证原子性。
- 配色与风格沿用系统现有设计，危险按钮使用深红色（`#c0392b`）。

**后端** (`auth/auth_service.py`, `api.py`)：
- `auth_service.py`：新增 `delete_user(user_id)` 函数，事务内按顺序级联删除，用户不存在返回 `False`。
- `api.py`：导入 `delete_user`，新增 `DELETE /api/admin/users/{target_id}` 端点；禁止删除自身账户（400），用户不存在（404），成功写入 admin_op 审计日志。

**前端** (`html_files/admin-page.html`)：
- 新增 CSS：`btn-danger-modal`、`danger-zone`、`btn-open-delete`、`delete-warning-box`。
- 编辑弹窗底部加"危险操作"分区 + "删除此用户"入口按钮。
- 新增删除确认弹窗（`modal-delete-user`）：展示将删除的数据范围 → 手动输入用户名验证 → 确认删除。

**修改文件**：`auth/auth_service.py`、`api.py`、`html_files/admin-page.html`

**时间**：2026-06-10

---

## 2026-06-05 (对话嵌入功能)

**功能**：新增"对话嵌入"，支持将智能对话以聊天球或网页 iframe 两种方式嵌入到外部前端项目。

**方案**：
- 聊天球（`chat-ball.js`）：单轮对话，每次发送生成新 thread_id；Shadow DOM 隔离样式；3 层动画（渐变旋转 + 脉冲环 + 悬浮抖动）；支持拖拽，默认右下角。
- 网页嵌入（`chat-embed.html`）：多轮对话，thread_id 存 sessionStorage，刷新重置。
- 两者均通过 `POST /api/embed/chat` 接口通信，`embed_token` 鉴权，底层复用 `agent.chat()`（Router 自动分发 rag_agent / data_agent）。

**后端** (`api.py`)：
- 新增 `POST /api/embed/chat`：embed_token 校验，无 thread_id → 单轮，有 thread_id → 多轮。
- 新增 `GET /embed/chat`：返回 `chat-embed.html`。
- 新增 `GET /static/chat-ball.js`：返回聊天球脚本，外部只需对接 8000 端口。

**新增文件**：`html_files/chat-ball.js`、`html_files/chat-embed.html`、`html_files/implant_test.html`（测试页）

**修改文件**：`api.py`、`.env`（新增 `EMBED_TOKEN`）、`html_files/more-features-page.html`（新增对话嵌入功能卡片及弹窗）

**时间**：2026-06-05

---

## 2026-06-03 (data_agent 多轮对话幻觉修复)

## 2026-06-03 (用户头像功能)

**功能**：用户设置页新增"更换头像"弹窗，支持上传图片或选择预置色块头像，保存后侧边栏实时同步。

**方案**：头像以 base64 data URL 存入 SQLite `users.avatar` 列，不引入文件系统依赖。

**后端**：
- `core/database.py`：`init_db` 新增 `ALTER TABLE users ADD COLUMN avatar TEXT` 幂等迁移。
- `auth/auth_service.py`：`authenticate_user` 返回值补充 `avatar` 字段；新增 `update_avatar(user_id, avatar_data)` 函数（限 400KB，校验 data URL 前缀）。
- `api.py`：`LoginResponse` 加 `avatar: str | None`；登录接口返回 avatar；新增 `PUT /api/user/avatar` 端点（校验 `data:` 前缀，写审计日志）；导入 `update_avatar`。

**前端**：
- `setting-page.html`：新增 avatar modal —— 上传区（Canvas 压缩到 200×200 JPEG 0.82）、6 个预置渐变色块（对应系统配色）、实时预览环；`initPage` 调用 `renderBigAvatar` / `renderSidebarAvatar` 初始化头像显示；保存后同步 localStorage + 所有头像 DOM。
- `home-page.html`：侧边栏 `.user-avatar` 加 `id`、`overflow:hidden`；新增 `renderSidebarAvatar()`；登录初始化和 `visibilitychange`（从 setting 页返回时）双触发同步。
- `login-page.html`：登录成功写 localStorage 时补存 `avatar` 字段。

**修改文件**：`core/database.py`、`auth/auth_service.py`、`api.py`、`html_files/setting-page.html`、`html_files/home-page.html`、`html_files/login-page.html`

**时间**：2026-06-03

---

## 2026-06-03 (api_agent：HTTP 接口查询智能体)

**功能**：新增 `api_agent`，通过调用已配置的 HTTP 接口获取实时数据并回答用户问题，对接 `interface_config.html` 中管理的接口配置。

**方案**：
- `agents/api_agent.py`（新建）：ReAct Agent，包含两个工具：
  - `list_interfaces`：读取 `project_documents/interface_configs.json`，列出所有已启用接口的 ID、名称、HTTP 方法、URL 及参数（区分默认/可选）。
  - `call_interface`：按接口 ID 发起 HTTP 请求（支持 GET/POST/PUT/PATCH/DELETE），自动携带配置中已启用的默认参数，支持通过 `extra_params`（JSON 字符串）覆盖或追加参数；处理 Bearer/API Key 认证、自定义请求头、JSON/Form body；超时 15s，错误信息直接返回给 LLM。
  - 使用 `requests.Session` 复用连接，配置文件每次工具调用时实时读取（支持热更新）。
- `agents/registry.py`：AGENT_REGISTRY 新增 `api_agent` 条目（`required_role: [user, admin]`）。
- `agent.py`：导入并实例化 `api_agent`；`chat_direct()` 的 `agent_map` 新增 `"api_agent"` 键。
- `api.py`：`ChatRequest.mode` 注释补充 `"api"` 选项；`chat_stream` 的 `mode_calls` 新增 `"api"` → `chat_direct("api_agent", ...)`。

**修改文件**：`agents/api_agent.py`（新建）、`agents/registry.py`、`agent.py`、`api.py`

**时间**：2026-06-03

---

## 2026-06-02 (记忆系统博客优化)
>>>>>>> 8c7a45c6e18c5575b2ea81327870b9bdb49a1507

**问题**：data_agent 在多轮对话中出现数据幻觉——用户追问具体数据时 LLM 不调用工具，直接基于历史回复编造答案。

**根因**：
- `agent.py` 的 `_build_messages_with_history` 把 SQLite `messages` 表中**全部历史消息**一次性注入 LLM 上下文
- 历史 AI 回复中的数值和结论（如"全月无异常记录"）被 LLM 当作**已验证事实**，跳过工具调用直接推理
- `create_react_agent` 的 `tool_choice: "auto"` 在上下文被污染后失效，`should_continue` 节点因无 `tool_calls` 直接结束
- 形成了**幻觉传播链**：Turn N 的编造内容 → Turn N+1 的上下文 → Turn N+1 基于旧编造内容继续编造

**方案**：

1. `agent.py` — 历史 AI 回复语义降权标签：
   - 旧：`[历史回答，仅供参考上下文，回答新问题必须重新调用工具获取数据]`（硬性命令，会让纯对话问题被迫调工具）
   - 新：`[历史回复，其中的数据和结论为当时查询结果，不代表当前真实状态]`（事实声明，LLM 自行判断是否需要工具）

2. `agents/data_agent.py` — System Prompt 约束精细化：
   - 旧：一刀切 "任何涉及数据值的问题必须先调工具"（过于刚性）
   - 新：分 a/b/c 三级——数据问题调工具 / 纯对话问题无需 / 不确定优先调（参考 OpenAI/Anthropic 的 Guardrails 分层思想）
   - 新增约束 5：明确"历史数据值为**当时**查询结果，新问题必须重新获取"

**设计理念**：不给 LLM 下硬性"必须调工具"的命令，而是通过**语义降权标签**和**分层约束**让 LLM 的 `tool_choice: auto` 机制正确工作——旧回复中的结论被标记为"非事实"，涉及数据时自然倾向调工具，纯对话问题自然跳过。

**修改文件**：`agent.py`（`_build_messages_with_history` 历史标记语义）、`agents/data_agent.py`（硬性约束细化为分层判断标准）

**时间**：2026-06-03

---

<<<<<<< HEAD

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

---

## 2026-06-11 (知识库后端从 Dify 迁移至 RAGFlow)

**功能**：将 rag_agent、doc_agent 及管理员知识库页面的检索后端从 Dify 切换为自建 RAGFlow 实例（192.168.1.155）。

**方案**：
- **检索接口**：`POST /datasets/{id}/retrieve`（Dify）→ `POST /retrieval`（RAGFlow）；请求体 `query` → `question`，`top_k` 嵌套对象 → 平铺 `page_size`，`dataset_ids` 数组传参；响应 `records[]` → `data.chunks[]` + `data.doc_aggs[]` 合并重组为内部统一格式，业务层无感知。
- **文档列表接口**：路径不变，响应从 `data[]` 改为 `data.docs[]`，翻页终止条件改为与 `total` 对比；状态字段 `indexing_status=="completed"` → `run=="DONE"`。
- **知识库列表接口**：路径不变，分页参数 `limit` → `page_size`。
- **新增** `data/ragflow_service.py`，替代 `data/dify_service.py`；函数签名保持不变，调用方 `api.py`、`admin_page.py` 仅改 import。
- **环境变量**：`DIFY_DATASET_KEY`/`DIFY_KB_ID`/`DIFY_API_BASE` → `RAGFLOW_API_KEY`/`RAGFLOW_DATASET_ID`/`RAGFLOW_API_BASE`；`.env.example` 注释旧 Dify 变量，补充 RAGFlow 变量。

**修改文件**：`agents/rag_agent.py`、`agents/doc_agent.py`、`data/kb_search.py`、`data/ragflow_service.py`（新建）、`api.py`、`pages/admin_page.py`、`.env.example`

**时间**：2026-06-11

---

## 2026-06-11 (对接真实数据接口)

**功能**：实现从 Swagger 服务导入真实 API 规范、在线测试、接口查询与必填校验。

**方案**：
- **导入引擎**：支持 Swagger URL 自动探测（`/v3/api-docs`、`/v2/api-docs`、`/swagger.json`、`/api-docs`），也支持直接粘贴 JSON 规范；解析后按服务名归类保存到 `data_interface/`。
- **混合存储**：`data_interface/` JSON 文件为 Source of Truth，启动时自动扫描并同步到 SQLite `data_interfaces` 索引表，支持按用户权限过滤可见接口。
- **在线测试**：前端"接口查询"页面选择接口 → 填参 → 发送请求，后端通过 `requests` 真实调用目标服务并展示响应（状态码、耗时、响应体）。
- **必填校验**：前后端双重校验 `parameters[].required`，不填则拦截提示，不再静默发送缺失参数的请求。
- **安全隔离**：`data_interface/` 纳入 `.gitignore`，不随代码推送；他人部署后通过"从 Swagger URL 导入"即可重建。

**修改/新增文件**：`data/interface_service.py`、`html_files/interface_config.html`、`scripts/import_swagger_specs.py`、`.gitignore`

**时间**：2026-06-11

---

## 2026-06-15 (更多功能页前端动效升级)

**功能**：依据 `html_files/style.md` 动效规范，对"更多功能"页 (`more-features-page.html`) 进行动画升级，仅改前端、不动后端及业务逻辑。

**方案**：
- **关键帧库**：注入 `fadeInUp / fadeInX / cardPop / iconBounce / rippleAnim` 及 `.ripple` 基础样式，全部动画仅用 `transform`/`opacity`，零布局位移。
- **入场错峰 (stagger)**：侧边栏 6 个导航项 `fadeInX`（延迟 50→350ms）；页面标题 `fadeInUp`；6 张功能卡片 `cardPop` 回弹（延迟 100→450ms）；coming-soon 横幅与底注 `fadeInUp` 收尾（500/580ms）。
- **卡片 hover 增强**：图标 `iconBounce` 弹跳 + `::after` 斜向高光扫过 (`left: -75% → 135%`)。
- **点击反馈**：`.use-btn`、`.embed-footer-btn` 加 `:active` 缩放；JS 事件委托在点击坐标注入 ripple 水波纹，0.6s 后移除（不触碰现有 onclick）。
- **模态框入场**：`embedIn` 改用回弹曲线 `cubic-bezier(0.34,1.15,0.64,1)`。
- **无障碍降级**：`@media (prefers-reduced-motion: reduce)` 关闭全部动画并强制 `opacity:1` 防止入场元素卡在隐藏态；ripple JS 同步检测该偏好后跳过。

**修改文件**：`html_files/more-features-page.html`

**时间**：2026-06-15

