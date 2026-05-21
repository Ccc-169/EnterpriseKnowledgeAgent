---
name: 动态识别Excel表头行位置
overview: 移除 data_agent.py 中 inspect_file 和 execute_data_query 对 skiprows=2 的硬编码，改为动态检测 Excel 表头行位置。inspect_file 读取前10行内容，由 LLM 判断表头所在行，并将 skiprows 值传递给后续代码生成环节。
todos:
  - id: modify-inspect-file
    content: 修改 inspect_file 函数：读取原始前10行返回给 LLM 判断表头行位置，同时返回 skiprows=0 的列名作为参考
    status: completed
  - id: modify-react-prompt
    content: 修改 ReAct agent 的 system prompt：新增规则要求 LLM 根据 inspect_file 结果判断 skiprows 值
    status: completed
    dependencies:
      - modify-inspect-file
  - id: modify-code-prompt
    content: 修改 execute_data_query 的 code_prompt：删除硬编码 skiprows=2，改为动态提示 LLM 根据表头位置确定 skiprows
    status: completed
    dependencies:
      - modify-inspect-file
  - id: modify-multi-file-rules
    content: 修改 multi_file_rules：删除硬编码 skiprows=2，改为动态提示
    status: completed
    dependencies:
      - modify-inspect-file
  - id: update-dev-log
    content: 更新 Dev_log.md 记录本次修改
    status: in_progress
    dependencies:
      - modify-multi-file-rules
---

## 用户需求

`agents/data_agent.py` 中 `inspect_file` 和 `execute_data_query` 硬编码了 `skiprows=2`（假设 Excel 表头在第三行），但实际文件的表头行位置不固定（可能在第一行、第二行等），需要让 agent 动态识别表头行位置。

## 修改范围

- `agents/data_agent.py` 中的 `inspect_file` 函数
- `agents/data_agent.py` 中的 `execute_data_query` 函数的 `code_prompt`
- `agents/data_agent.py` 中的多文件规则 `multi_file_rules`
- `agents/data_agent.py` 中 ReAct agent 的 system prompt

## 技术方案

### 核心思路

让 `inspect_file` 返回 Excel 原始前10行内容（不指定 `header`），由 LLM 自行判断表头行位置；后续代码生成时从上下文提取 `skiprows` 值，不再硬编码。

### 修改点

**1. `inspect_file` 函数（第37-54行）**

- 改用 `pd.read_excel(file_path, header=None, nrows=10)` 读取原始内容
- 返回值中附带原始前10行文本，并提示 LLM 判断表头行位置（行号从0开始）
- 同时保留用 `skiprows=0` 读取的列名作为参考信息

**2. ReAct agent system prompt（第112-127行）**

- 新增规则：调用 `inspect_file` 后，根据返回的原始内容判断表头行位置
- 明确告知：表头在第 N 行则代码中使用 `skiprows=N`

**3. `execute_data_query` 的 `code_prompt`（第80-91行）**

- 删除第84行硬编码的 `skiprows=2`
- 改为提示：根据 `inspect_file` 检测到的表头行位置动态确定 `skiprows`

**4. 多文件规则 `multi_file_rules`（第73-78行）**

- 删除硬编码的 `skiprows=2`
- 改为提示：使用与 `inspect_file` 一致的 `skiprows` 值

### 关键设计决策

- **不引入启发式检测**：让 LLM 判断比手写规则更鲁棒，且避免了误判
- **不新增 State 字段**：ReAct agent 的工具调用是顺序的，`inspect_file` 的返回内容留在对话上下文中，`execute_data_query` 生成代码时 LLM 可以直接参考
- **`inspect_file` 返回值设计**：同时返回原始内容和 `skiprows=0` 的列名，兼顾判断依据和即时可用性