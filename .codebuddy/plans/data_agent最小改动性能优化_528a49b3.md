---
name: data_agent最小改动性能优化
overview: 基于 problem_record_2.md 的性能瓶颈分析，以最小改动解决两个 P0 级问题：多文件查询月份标签丢失 + 规则7日期列误杀，预计消除约140s无效耗时。
todos:
  - id: fix-multi-file-template
    content: 修改 data_agent.py 多文件代码模板，concat 前注入 _source_file 来源列
    status: completed
  - id: fix-rule7-datetime
    content: 修改 data_agent.py 规则7，从强制转换改为条件判断
    status: completed
  - id: add-os-import
    content: code_executor.py 模板添加 import os
    status: completed
  - id: update-agent-prompt
    content: data_agent.py prompt 补充多文件分组提示
    status: completed
  - id: sync-dev-log
    content: 同步更新 Dev_log.md 开发日志
    status: completed
    dependencies:
      - fix-multi-file-template
      - fix-rule7-datetime
      - add-os-import
      - update-agent-prompt
---

## 用户需求

针对 problem_record_2.md 中分析的两个 P0 性能瓶颈，给出改动最小且有一定效果的改进方案。

## 核心问题

1. **多文件查询始终失败**：12个考勤文件 concat 后按月汇总，代码无法识别各文件月份来源，只有第1个文件数据被统计，其余全0。Agent反复试错5次浪费约120s。
2. **规则7日期列误杀**：`pd.to_datetime` 对整数列（如出勤天数=17）误转为"1970-01-01"，拼接后 ValueError 崩溃。浪费约20s。

## 改动目标

- 只修改 `data_agent.py` 和 `code_executor.py` 两个文件
- 总改动约6-8行，不影响现有单文件查询逻辑
- 预期消除5次无效重试（节省约120s）和 ValueError 崩溃（节省约20s）

## Tech Stack

- Python 3.x（现有项目）
- LangChain + LangGraph（现有框架）
- 无需引入新依赖

## Implementation Approach

### 改动1：多文件合并时注入 `_source_file` 来源标识列

**问题**：LLM 生成的代码用 `pd.concat(dfs)` 合并多文件后，无法区分每行数据来自哪个文件，导致按月分组时只有第一个文件的标签被正确识别。
**方案**：在多文件代码模板中，将列表推导式改为 for 循环，逐个读取并为每个 df 添加 `_source_file` 列（取 `os.path.basename(p)`），这样合并后 LLM 可以从文件名提取月份做分组。文件名如"1月考勤.xlsx"天然包含月份信息。
**改动量**：data_agent.py 2处模板字符串（第94-96行和第102行），约5行文本变更。

### 改动2：规则7从"强制转换"改为"条件转换"

**问题**：规则7要求所有日期/时间列都 `pd.to_datetime`，但整数列（出勤天数=17）会被转为"1970-01-01"，导致后续数值计算崩溃。
**方案**：将规则7改为"只对 pandas 已识别为 datetime 类型的列做字符串转换"，使用 `pd.api.types.is_datetime64_any_dtype()` 判断，避免对纯数字列误调 `pd.to_datetime`。
**改动量**：data_agent.py 第105行，1行文本变更。

### 改动3：code_executor 模板添加 `os` 模块导入

**原因**：改动1的多文件模板中使用了 `os.path.basename()`，而 code_executor.py 第39行的模板只导入了 `pandas, json, warnings`，需要补上 `os`。
**改动量**：code_executor.py 第39行，添加 `, os`，1行变更。

### 改动4：agent prompt 补充多文件分组提示

**原因**：告诉 LLM 多文件查询时利用 `_source_file` 列从文件名提取分组标签，避免 LLM 不知道这个列的存在而忽略它。
**改动量**：data_agent.py 第153-157行效率规则区域，新增1条提示。

## Implementation Notes

- `_source_file` 列名以下划线开头，与业务列区分，避免与真实数据列冲突
- 单文件查询时不走 `multi_file_rules` 分支，`_source_file` 列不会被添加，完全不影响现有单文件逻辑
- `os.path.basename` 在 Windows/Linux 均可用，跨平台无风险
- 规则7改为条件判断后，pandas 自动识别的 datetime 列仍会被正确转换，JSON 序列化安全性不变

## Architecture Design

无需架构变更，仅修改两个文件中的提示模板和 import 语句。

## Directory Structure

```
d:/App_data/HNGD-Agent/HNGD-backend/
├── agents/
│   └── data_agent.py  # [MODIFY] 4处改动：多文件模板加_source_file、规则7改为条件转换、prompt补充分组提示
├── code_executor.py    # [MODIFY] 1处改动：模板添加 import os
└── project_documents/
    └── Dev_log.md      # [MODIFY] 新增本次优化记录
```