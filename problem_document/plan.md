# Plan：对话任务可取消 + 并发闸门 + 资源回收硬保证

**关联问题**：`problem_record_5.md`（幽灵任务拖垮单卡 Ollama）
**目标**：在 `-np 1`（全系统一次只能生成 1 条）的硬件现实下，让会话从发起到结束**串行排队、可取消、有序、资源不泄漏**。
**总原则**：不影响任何现有功能。新逻辑全部由 env 开关包裹，`cancel_event=None` 默认值保证所有现有调用点行为不变。

---

## 一、设计决策（已与需求方确认）

| 决策点 | 选择 |
|---|---|
| 切页行为 | **切页即取消**。回到对话页只能看到部分内容或无回复，是为防资源耗尽的有意取舍 |
| 排队提示 | **精确数字**。显示"排队中（前方 N 人）"，需后端维护等待队列计数 |
| 并发上限 | `CHAT_MAX_CONCURRENCY=1`，严格对齐 `-np 1` |
| 断开自动取消 | 默认开启 |

---

## 二、实施阶段

### 阶段 1 — 统一配置（`core/config.py`）

在已有统一配置文件中新增（不得散落 `os.getenv`）：

```python
# ── 会话并发控制 ──
CHAT_MAX_CONCURRENCY      = int(os.environ.get("CHAT_MAX_CONCURRENCY", "1"))
CHAT_CANCEL_ON_DISCONNECT = os.environ.get("CHAT_CANCEL_ON_DISCONNECT", "true").lower() == "true"
CHAT_THREAD_POOL_SIZE     = int(os.environ.get("CHAT_THREAD_POOL_SIZE", "32"))
CHAT_DISCONNECT_POLL_SEC  = float(os.environ.get("CHAT_DISCONNECT_POLL_SEC", "0.5"))
```

**verify**：`import core.config` 无报错，默认值符合 `-np 1`。

---

### 阶段 2 — 取消注册中心（新建 `core/chat_registry.py`）

维护 `dict[user_id -> threading.Event]`，加一把 `threading.Lock`。

- `register(user_id) -> Event`：若旧 event 存在先 `.set()`（**单飞**：挤掉该用户旧任务），写入并返回新 event。
- `unregister(user_id, event)`：**仅当当前存储的 event is 本 event 时**才移除（避免误删已被单飞替换的新任务）。
- `cancel(user_id)`：set 该用户当前 event（供 `/stop` 调用）。
- `waiting_count()`：返回当前在排队/运行的任务数，供精确位次计算。

**verify**：register 两次后第一个 `event.is_set() == True`；unregister 旧 event 不影响新 event。

---

### 阶段 3 — agent.py 协作式取消（向后兼容）

1. `chat()` 与 `chat_direct()` 各加形参 `cancel_event=None`（默认 None → 行为完全不变）。
2. 两处 stream 循环顶部插入中断点：
   - `agent.py:212`（`chat_direct` 的 `agent.stream`）
   - `agent.py:324`（`chat` 的 `router.stream`）
   ```python
   for chunk in ...:
       if cancel_event is not None and cancel_event.is_set():
           break
       ...
   ```
3. `break` 后复用已有"提取 final_answer"逻辑（line 245 / 356 已存在）。被取消时返回已收集的部分答案。

**取消粒度说明**：取消只在 **chunk 边界**生效。若卡在单个 LLM 长请求内部（35B 满上下文一条数十秒），这段无法中断，槽仍被占住直到该 chunk 返回。这是 Ollama + LangGraph 架构的固有限制，本 plan 不解决。

**verify**：不传 `cancel_event` 时 CLI / doc 页 / Streamlit / embed_chat 全部行为不变。

---

### 阶段 4 — api.py 闸门 + 断开检测（仅改 `/api/chat/stream`）

1. **模块级**：`_chat_semaphore = asyncio.Semaphore(CHAT_MAX_CONCURRENCY)`；启动时设置默认线程池上限为 `CHAT_THREAD_POOL_SIZE`。
2. `chat_stream` 签名加 `request: Request`（当前缺失，断开检测必需）。
3. `event_gen` 内部流程：
   ```
   a. event = register(user_id)                      # 单飞
   b. 进信号量前若已被占用：
        yield {"type":"queued","position": waiting_count()}
   c. async with _chat_semaphore:
        task = asyncio.create_task(
            asyncio.to_thread(call_fn, cancel_event=event))
        若 CHAT_CANCEL_ON_DISCONNECT:
            循环每 CHAT_DISCONNECT_POLL_SEC 秒检查 await request.is_disconnected()
            断开 → event.set() → await task 收尾 → 标记 aborted
        response, steps, agent_used = await task
   d. 落库策略见阶段 5
   ```
4. 新增 `POST /api/chat/stop`：`cancel(user_id)` → `{"ok": True}`。

---

### 阶段 5 — 取消后落库策略

| 场景 | 行为 |
|---|---|
| 正常完成 | 照旧 `save_message` + `log_event` |
| 用户停止 / 切页取消 | **不写库**（避免半截回复污染历史），或写入带 `[已取消]` 标记——二选一，实现时取"不写库"，前端保留已显示部分仅作即时展示 |
| 写库前校验 conv 仍存在 | `save_message` 前用 `get_conversation` 确认 conv_id 未被删除，**孤儿 conv_id 直接丢弃**，不写入已删除对话 |

---

### 阶段 6 — 前端 `home-page.html`（纯增量）

1. `.send-btn` 加 `id`；新增停止态 `.is-stopping`（红灰渐变 `linear-gradient(135deg,#c0506a,#a8425a)`，尺寸/圆角/阴影与发送态一致，**布局零位移**）。
2. `sendChat()` 加 `AbortController`；发送中按钮切为停止图标 + `onclick=stopChat()`。
3. `stopChat()`：`POST /api/chat/stop` + `controller.abort()`，保留已显示的部分内容。
4. 处理新 `queued` 事件：显示"排队中（前方 N 人）"，减少用户切页/重发冲动。
5. **切页主动取消**：`beforeunload` + 路由/对话切换钩子内触发 `stopChat()`（落实"切页即取消"）。

**verify**：双浏览器，A 占槽、B 收到 `queued{position:1}`；A 切页 → 后端日志 cancel → B 立即开始。

---

## 三、资源回收硬保证（命门，不可妥协）

> 信号量 / registry / 线程必须在**所有**退出路径释放。漏一个 = 信号量泄漏 = 全系统永久卡死，比原 bug 更严重。

### 硬约束

1. **信号量必须用 `async with`**，禁止手动 acquire/release。即便 `event_gen` 中途 return / 抛异常 / 被 `GeneratorExit`，`async with` 也保证释放。
2. **registry 必须 `try/finally` 中 `unregister`**：
   ```python
   event = register(user_id)
   try:
       async with _chat_semaphore:
           ...
   finally:
       unregister(user_id, event)   # 任何路径都执行
   ```
3. **断开轮询任务必须可靠取消**：监控 `is_disconnected` 的辅助 task 在主任务结束后必须 `cancel()` 并 `await`，禁止泄漏后台轮询协程。
4. **线程不强杀**：`cancel_event` 是协作式，被取消的 `to_thread` 线程会自然跑完当前 chunk 后退出；必须 `await task` 等它收尾再释放信号量，**严禁不等线程就释放槽**（否则两个线程同时打 Ollama，违背 `-np 1`）。
5. **`GeneratorExit` 处理**：SSE 生成器被客户端断开时会收到 `GeneratorExit`，确保 `finally` 块在此情况下仍触发清理（FastAPI StreamingResponse 会触发）。

### 自检清单（实现后逐条验证）

- [ ] 正常完成：信号量计数回到初始值
- [ ] 用户点停止：信号量释放、registry 移除、线程退出
- [ ] 切页断开：同上
- [ ] 后端抛异常（沙箱挂 / Ollama 断连）：`finally` 仍释放
- [ ] 单飞挤掉旧任务：旧 event set、旧线程退出、新任务正常占槽
- [ ] 连续压测 100 次取消后，信号量仍能正常 acquire（无泄漏）

**verify 命令**：在 `event_gen` 关键节点打日志（register / acquire / release / unregister），压测脚本反复发起+取消，断言日志中 acquire 次数 == release 次数。

---

## 四、回滚方案

- `CHAT_CANCEL_ON_DISCONNECT=false` → 关闭断开自动取消
- `CHAT_MAX_CONCURRENCY` 调大 → 放开闸门（退回 Ollama 内部排队）
- 全部新逻辑 env 包裹，出问题改 env 重启即可，无需回退代码

---

## 五、不在本 plan 范围内（已知边界）

1. **会话显式状态机**（idle/queued/running/cancelled/done/error 状态字段）——本 plan 靠信号量 + registry 隐式控制，未引入状态列。
2. **空壳对话清理**（反复新建产生的无消息对话）。
3. **物理并发瓶颈**：`-np 1` 决定一次只能生成一条，应用层只能让它有序、不能让它变快。50 人流畅需运维降上下文换槽或上 vLLM（见 `problem_record_5.md` 第四节）。
