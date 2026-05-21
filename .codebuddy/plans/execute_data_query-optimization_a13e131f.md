---
name: execute_data_query-optimization
overview: 针对 execute_data_query 耗时 125s（占总量 54%）的瓶颈，通过合并查询、修复代码生成模板、精简 prompt、子进程预热四种手段，将 5 次调用降至 1-2 次，目标耗时降至 30-50s。
todos:
  - id: fix-code-prompt
    content: "R1: 修复 data_agent.py 的 code_prompt — 新增日期列转字符串规则 + default=str 兜底 + 精简冗余"
    status: completed
  - id: optimize-agent-prompt
    content: "R2: 优化 data_agent.py 的 agent prompt — 添加合并统计与禁止拆句的效率引导规则"
    status: completed
  - id: add-code-cache
    content: "R3: 在 data_agent.py 的 execute_data_query 中添加代码生成缓存 (_code_cache)"
    status: completed
    dependencies:
      - fix-code-prompt
  - id: batch-executor
    content: "R4: 修改 code_executor.py 新增 /execute_batch 端点；修改 data_agent.py 支持批量提交"
    status: completed
    dependencies:
      - optimize-agent-prompt
  - id: update-dev-log
    content: 更新 Dev_log.md 记录 execute_data_query 四层优化内容
    status: completed
    dependencies:
      - fix-code-prompt
      - optimize-agent-prompt
      - add-code-cache
      - batch-executor
---

## 问题聚焦

针对 `problem_record.md` 中记录的 **execute_data_query 性能瓶颈** 进行专项根因分析与改进计划。当前痛点：

- 4 次 execute_data_query 调用共耗时 **125s**，占总耗时 232.3s 的 54%
- 每次调用包含 LLM 代码生成（~7-10s）+ subprocess 冷启动执行（~15-18s）
- 第 1 次调用因 Timestamp JSON 序列化失败，Agent 主动拆分为三项查询导致调用次数膨胀

## 改进目标

将 execute_data_query 总耗时从 **125s 降至 30-50s**（减少 60-75%），同时保持答案准确度不降低。分四层递进优化，逐层可独立验证。

## 核心改进点

1. **代码 prompt 硬伤修复**：消除 Timestamp 序列化失败导致的重试（节省 ~25s）
2. **Agent 拆句抑制**：引导 Agent 合并同类统计为一次调用（节省 ~50s）
3. **代码生成缓存**：同文件同参数跳过重复 LLM 调用（节省 ~14-21s）
4. **Subprocess 复用**：executor 保持热身进程或批量执行（节省 ~24-30s）

## 根因深析（基于 trace_export.json 实际数据）

### 四个根因层级

| 层级 | 根因 | 涉及代码 | 损失 |
| --- | --- | --- | --- |
| **R1** | code_prompt 未告知日期列需转字符串，LLM 生成 `df.to_dict(orient='records')` 直接序列化 Timestamp 报错 | `data_agent.py` line 103-119 | 失败重试 +25s |
| **R2** | Agent 在 Call1 失败后主动表态"为提高鲁棒性，分别执行三项查询"（line 7900），将硬件+软件同类型查询拆为独立调用 | `data_agent.py` line 140-153 (agent prompt) | 额外 +50s |
| **R3** | Call1 和 Call2 对同一文件、同一 skiprows 生成两版高度相似代码，无缓存 | `data_agent.py` line 120 | 重复 LLM 调用 +21s |
| **R4** | `code_executor.py` line 33 每次 `subprocess.run(["python", tmp])` 冷启动新进程，pandas 导入（~2-3s）+ Excel 读取（~3-5s）均从零开始 | `code_executor.py` line 12-45 | 固定开销 ×4 = ~48s |


### Token 膨胀轨迹（Call1→Call4 的 prompt tokens 增长）

```
Call1 (硬件-失败): 5,036 prompt tokens
Call2 (硬件-重试): 6,386 prompt tokens (+27%)
Call3 (软件):     8,914 prompt tokens (+40%)
Call4 (CSMP):    10,471 prompt tokens (+17%)
```

每次后续调用都带着完整历史消息，代码生成耗时逐次递增。

### 每次调用耗时结构

```
execute_data_query 单次调用 (~25s)
├── LLM 代码生成 (llm.invoke)    7-10s  ← R3 可优化
└── HTTP POST → executor        15-18s  ← R4 可优化
    ├── subprocess 冷启动        0.5-1s
    ├── import pandas           2-3s
    ├── pd.read_excel()         3-5s
    └── 实际计算                 1-2s
```

---

## 优化策略

### 1. 代码 prompt 硬伤修复（省 25s，消除失败重试）

**问题**：code_prompt 缺少日期列防护规则，LLM 生成的 `df.to_dict(orient='records')` 遇到 pandas Timestamp 直接报错。

**修改**：在 `code_prompt` 中新增两条规则：

- 规则 N：日期/时间列在输出前用 `.dt.strftime('%Y-%m-%d')` 转为字符串
- 规则 N+1：`print(json.dumps(result, ensure_ascii=False, default=str))` 加上 `default=str` 兜底

同时精简冗余规则（扩展名选择规则在 code_prompt 和 multi_file_rules 中出现两次）。

**影响范围**：`data_agent.py` line 103-119 的 `code_prompt` 模板。

---

### 2. Agent prompt 拆句抑制（省 50s，4 次→2 次）

**问题**：Agent prompt 只说工具功能，未引导效率策略。Agent 在首次失败后主动拆分为三项查询。

**修改**：在 Agent prompt（`data_agent.py` line 140-153）新增效率引导规则：

- "对同一文件的不同统计需求应合并为一次 `execute_data_query` 调用，生成一个代码块包含多个 `result` 输出"
- "同类型文件（如硬件采购清单 + 软件采购清单）合并统计，使用多文件模式一次性传入"
- "执行失败时先检查代码中是否有日期列未处理，优先修复代码而非拆分查询"

**影响范围**：`data_agent.py` line 140-153 的 agent system prompt。

---

### 3. 代码生成缓存（省 14-21s）

**问题**：同一文件同一 skiprows 被多次调用，每次重新调用 LLM 生成代码。

**方案**：在 `create_data_agent` 闭包内新增 `_code_cache: dict`，以 `(file_path, skiprows, query)` 的哈希为 key。同一组合命中缓存时直接跳过 LLM 调用。

```python
_code_cache: dict[tuple, str] = {}

@tool
def execute_data_query(query, file_path, skiprows=0):
    cache_key = (file_path, skiprows, query)
    if cache_key in _code_cache:
        code = _code_cache[cache_key]
    else:
        code = llm.invoke(code_prompt).content
        code = code.replace("```python", "").replace("```", "").strip()
        _code_cache[cache_key] = code
    # ... 后续执行不变
```

**影响范围**：`data_agent.py` line 73-134 的 `execute_data_query` 函数体。

**注意事项**：

- 缓存生命周期与 agent 实例相同（应用启动期间有效）
- 缓存 key 包含 query 而不是仅 file_path，因为不同 query 生成不同代码
- 对同一文件执行不同统计需求时不会误缓存——因为 query 不同
- 必要时可在 inspect_file 中增加 `force_refresh` 参数预留扩展点

---

### 4. Subprocess 复用（省 24-30s）

**问题**：`code_executor.py` 每次 `subprocess.run(["python", tmp])` 冷启动新进程。

**最优方案**：将一次性临时文件写入改为持久脚本 + stdin JSON 传参模式。

**实现方法**：

- `code_executor.py` 新增 `/execute_batch` 端点，接受 `codes: list[str]` 和公共 `data_path`
- 一次请求中合并所有代码块：`wrapped = "import pandas as pd, json, warnings\nwarnings.filterwarnings('ignore')\nDATA_PATH = ...\n" + "\n".join(codes)`
- 所有统计在一个 Python 进程中完成，共享一次 pandas 导入和文件读取

**修改**：

1. `code_executor.py`：新增 `CodeBatchRequest` 模型和 `/execute_batch` 端点
2. `data_agent.py`：当 Agent 在同一轮中连续调用 execute_data_query 时，缓存待执行代码块，最后批量提交

**影响范围**：

- `code_executor.py` line 8-46（新增批量端点）
- `data_agent.py` line 72-134（execute_data_query 增加批量提交逻辑）

**复杂度权衡**：如果 `/execute_batch` 改动过大，可退而求其次——在 wrapped 模板中预 import pandas 并保持进程热身（更简单但收益略低）。

---

## 实施路线

```
Phase 1 (最低风险，独立部署)：
  任务1 → 代码 prompt 硬伤修复（消除重试，省 25s）
  任务2 → Agent prompt 效率引导（抑制拆分，省 50s）
  
Phase 2 (依赖 Phase 1，独立验证)：
  任务3 → 代码生成缓存（省 14-21s）

Phase 3 (架构变更，需测试)：
  任务4 → Subprocess 批量复用（省 24-30s）
```

## 目录结构

```
d:\App_data\HNGD-Agent\HNGD-backend\
├── agents\
│   └── data_agent.py         # [MODIFY] R1+R2+R3: 修改 code_prompt、agent prompt、execute_data_query 函数体
├── code_executor.py          # [MODIFY] R4: 新增 /execute_batch 批量执行端点
└── project_documents\
    └── Dev_log.md            # [MODIFY] 记录本次优化
```

## Agent Extensions

### SubAgent

- **code-explorer**
- Purpose：在实施前验证 `data_agent.py` 和 `code_executor.py` 的完整代码结构，确认所有修改点准确。
- Expected outcome：获得完整的函数边界、变量作用域、现有缓存模式，确保修改不破坏现有逻辑。