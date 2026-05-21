# 问题分析记录

---

## 2026-05-20 (LangSmith Trace 性能分析)

**问题**：trace_export.json（45922 行）记录了用户提问"研发中心3月份硬件采购和软件采购详情，以及总结CSMP项目节点安排"的完整执行过程，总耗时 232.3 秒，需分析性能瓶颈。

**Trace 基本信息**：

| 项目 | 内容 |
|------|------|
| Trace ID | `019e3f9f-d273-7f32-962d-8e5c6cf5a234` |
| 用户问题 | 研发中心3月份硬件采购和软件采购详情，以及总结CSMP项目节点安排 |
| 执行时间 | 2026-05-19 09:44:59 → 09:48:51 |
| 总耗时 | 232.3 秒（3 分 52 秒） |
| 最终状态 | success |
| 模型 | qwen-plus |
| Prompt Tokens | 61,784 |
| Completion Tokens | 7,986 |
| Total Tokens | 69,770 |
| Cache Hit | 0（无缓存命中） |

**执行时间线**：

```
09:44:59 ████ Supervisor (Router) — 1.2s
         │     └─ 决策：transfer_to_data_agent
         │
09:45:00 ████████████████████████████████ data_agent — 206.3s (占 89%) ⚠️
         │     │
         │     ├─ 多轮 Agent-Tools 循环 (17+ langgraph_steps)
         │     │   ├─ list_files       (4次)
         │     │   ├─ inspect_file     (多次)
         │     │   └─ execute_data_query (至少5次，每次 ~25s) ⚠️ 最大瓶颈
         │     │       └─ 内部含 LLM 代码生成 + subprocess 执行
         │     │
         │     └─ 最终汇总：硬件20项 + 软件20项 + CSMP 8个里程碑
         │
09:48:26 ████████ Supervisor 最终输出 — 24.9s
         │     └─ 将 data_agent 结果包装为最终回答
09:48:51 ██ 结束
```

**关键发现**：

1. **最大耗时点：execute_data_query**：每次调用约 25 秒（包含 LLM 代码生成 + subprocess 启动新 Python 进程执行），共调用了至少 5 次，约 125 秒（占总时间的 54%）。

2. **大量重复 LLM 往返**：data_agent 内部走了 17+ 个 langgraph 步骤，每次 agent 决策约 7 秒，每次 tools 执行约 25 秒。

2. **token 浪费严重**：61,784 prompt tokens 中大部分是重复传递的长历史消息（每轮都带上完整的对话历史），没有使用缓存（cache_read: 0）。


**优化方向（按优先级）**：

| 优先级 | 方向 | 预期节省 | 依据 |
|--------|------|----------|------|
| P0 | 减少 execute_data_query 调用次数（合并查询） | -50~75s | 5次×25s → 可合并为 1-2 次 |
| P1 | 文件内容缓存（避免重复 inspect_file） | -20s | 同文件被多次读取 |
| P2 | Prompt 精简（减少历史消息膨胀） | -30s | 61K prompt tokens 大量冗余 |
| P3 | LLM 调用缓存（相同前缀复用） | -15s | cache_read 目前为 0 |

**时间**：2026-05-20 09:22

---

## 2026-05-20 (execute_data_query 专项深度分析)

**分析对象**：Trace 中 5 次 execute_data_query 调用，总 125s（占 54%）。

**根因链**：
```
第1次调用因 code_prompt 缺 Timestamp→字符串规则而失败 (TypeError: Timestamp is not JSON serializable)
  → Agent 诊断后主动拆分：3项独立查询 + 1次重试 = 4次额外调用
    → 每次调用 = LLM代码生成(7-10s) + subprocess冷启动(15-18s) = 25s
      → 5 × 25s = 125s
```

**每次调用耗时结构**：
- LLM 代码生成 (`llm.invoke`)：7-10s（prompt tokens 从 5K 递增至 10K）
- Subprocess 冷启动：15-18s（启动Python+pandas导入+Excel读取）

**优化措施（已实施 2026-05-20）**：
| 层 | 措施 | 文件 | 省时 |
|----|------|------|------|
| R1 | code_prompt 增加日期列转字符串 + default=str 兜底 | data_agent.py | -25s |
| R2 | agent prompt 增加合并统计/禁止拆句/失败先修代码 | data_agent.py | -50s |
| R3 | execute_data_query 内增 _code_cache 闭包缓存 | data_agent.py | -14~21s |
| R4 | code_executor 新增 /execute_batch 批量端点 | code_executor.py | -24~30s |

**目标**：5次→1-2次调用，125s→30-50s。

**时间**：2026-05-20 09:49

---
