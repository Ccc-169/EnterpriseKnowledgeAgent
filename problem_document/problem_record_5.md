# 问题记录 #5：对话任务无法取消，幽灵任务拖垮单卡 Ollama

**日期**：2026-06-13
**来源**：代码审查 + 生产环境（部门内部试用，约 20 人，目标 50 人并发）
**部署环境**：本地 Ollama，`qwen3.6:35b`（Q4_K_M，上下文 262144，4 卡 SCHED_SPREAD 铺满），嵌入模型 `bge-m3` 独立进程
**关键约束**：Ollama 启动参数 `-np 1` —— **全系统任意时刻只能生成 1 条回复**，其余请求在 Ollama 内部排队

---

## 一、问题描述

用户发起对话后，若 agent 还在思考时：
1. **从历史记录删除该对话**
2. **切换到网站其他页面**
3. **反复新建对话**

体感上以为对话停止了，但后台任务仍在继续运行。

---

## 二、根因诊断

### 根因 1：agent 执行不可取消
- `chat()` / `chat_direct()`（`agent.py`）是同步阻塞函数，通过 `asyncio.to_thread`（`api.py:330`）放入线程池运行
- 核心是 `for chunk in agent.stream(...)` 迭代循环（`agent.py:212`、`agent.py:324`），**循环内无任何中断点**
- 删除对话、切页、新建对话都只改前端/数据库状态，**对后台线程毫无影响**，任务会一直跑到 LLM 返回

### 根因 2：前端 SSE 连接随页面销毁而断开，但服务端不感知
- `home-page.html` 用 `fetch + ReadableStream` 读 SSE，连接绑定在当前页面 JS 上下文
- 切页 → 连接断开 → 流式回复永久丢失；但服务端 `to_thread` 任务**不会被取消**，跑完后写库（可能写入已删除的孤儿 `conv_id`）

### 根因 3（最致命）：无并发控制，幽灵任务独占唯一生成槽
- `api.py` 对每个请求无条件 `asyncio.to_thread`，无并发上限、无单飞、无断开检测
- 在 `-np 1` 的硬件现实下：**一个幽灵任务就独占了全系统唯一的生成槽，后面所有真实用户全部卡死**，直到幽灵任务自己跑完（35B 满上下文可能数十秒一条）
- 前端 `isSending` 标志只在单页面内防连点，**跨页面跳转后失效**

### 硬件现实（决定所有参数）
- `journalctl` 确认每个 llama-server 均以 `-np 1` 启动
- `OLLAMA_SCHED_SPREAD=true` 把单个 35B 模型铺满 4 卡换单条速度，**不提供并行槽**
- 所谓"50 人并发"在此配置下只能是"50 人在线、LLM 请求严格串行排队"
- 嵌入模型 bge-m3 是独立 llama-server，检索向量化不抢生成槽

---

## 三、解决方案（应用层接管队列 + 协作式取消）

利用 `agent.stream()` 是迭代循环这一天然取消点：每取到一个 chunk 检查取消标志，可真正停止向 LLM 继续请求。

```
用户请求 → FastAPI
            ↓
   注册 cancel_event（单飞：挤掉该用户的旧请求）
            ↓
   asyncio.Semaphore(1).acquire()   ← 唯一生成槽的应用层闸门
     │ 等待中 → yield {"type":"queued","position":N}  （前端显示"前方 N 人"）
     │ 等待中 → 用户切页/点停止 → cancel_event.set() → 直接退出，不占槽
            ↓
   拿到槽 → asyncio.to_thread(call_fn, cancel_event)
            ↓ agent.stream 循环每个 chunk 检查 cancel_event，可中断
   生成 → 流式返回 → 释放槽给下一个排队者
```

### 后端改动
| 项 | 内容 |
|----|------|
| 新建 `core/chat_registry.py` | 取消注册中心，`dict[user_id, threading.Event]`，注册时自动取消旧任务（单飞） |
| `agent.py` | `chat` / `chat_direct` 新增 `cancel_event=None` 参数；两处 stream 循环顶部插入 `if cancel_event and cancel_event.is_set(): break`，break 后复用已有"提取已收集答案"逻辑 |
| `api.py` `/api/chat/stream` | 注入 `Request`；全局 `asyncio.Semaphore(CHAT_MAX_CONCURRENCY)`；并发轮询 `await request.is_disconnected()`，断开则 `cancel_event.set()`；进信号量前 yield 排队位次 |
| 新增 `POST /api/chat/stop` | 设置当前用户 cancel_event |

### 前端改动（`home-page.html`）
- `.send-btn` 增加 `id` + 停止图标 svg + `.is-stopping` 状态类（红灰渐变 `linear-gradient(135deg,#c0506a,#a8425a)`，尺寸/圆角/阴影与发送态一致，**布局零位移**）
- `sendChat()` 加 `AbortController`；发送态切换为停止按钮、`onclick=stopChat()`
- 新增 `stopChat()`：`POST /api/chat/stop` + `controller.abort()`，保留已显示的部分内容
- 新增排队提示：收到 `queued` 事件显示"排队中（前方 N 人）"，减少用户切页/重发冲动

### 关键参数
| 参数 | 值 | 理由 |
|------|----|----|
| `CHAT_MAX_CONCURRENCY` | **1**（= `-np 1`），env 可调 | 设大于 1 只会让请求堆在 Ollama 内部队列、拿不到排队位次 |
| 断开自动取消 | **默认开启** | `-np 1` 下幽灵任务独占唯一槽，关掉等于自杀 |
| 线程池上限 | 显式设 32 | 线程在等 Ollama 不耗 CPU，真正闸门是信号量 |

### 兼容性
- `cancel_event=None` 默认值保证所有现有调用点（文档生成、embed_chat、CLI、Streamlit 页面）行为不变
- 仅 `/api/chat/stream` 实际改动；`/stop` 与前端按钮为纯增量
- 全部新逻辑用 env 开关包裹，出问题改 env 重启即可回滚

---

## 四、超出本次代码改动的基建建议

本次改动解决"队列有序 + 不被幽灵任务拖垮"，**解决不了"单卡一次只能生成一条"的物理瓶颈**。若要 50 人流畅，需运维层调整：
1. **降上下文换并发槽**：262144 是 KV cache 黑洞，多数企业问答用不到，降至 32768 可省显存把 `-np` 提到 4~8
2. **或上 vLLM**：连续批处理，并发效率远高于 Ollama

---

## 五、行为变化提醒

修复后：用户发起对话后切页，任务会在切走时被主动取消。回到对话页只能看到部分内容或无回复（此前是"运气好能看到已写库的完整回复"）。这是为防资源耗尽的有意取舍。
