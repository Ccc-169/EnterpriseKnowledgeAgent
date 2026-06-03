# agents/data_agent.py
import os
import re
import json
import requests
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

# 复用 TCP 连接，避免每次请求重新建连（~2s → <10ms）
_http_session = requests.Session()

# ── 规则引擎导入 ─────────────────────────────────────
from rules.integration import check_generated_code
from rules.engine import RuleViolationError

_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "..", "project_documents", "data_schema.json")


def create_data_agent(llm):

    DATA_DIR     = os.environ["DATA_DIR"]
    EXECUTOR_URL = os.environ["EXECUTOR_URL"]

    # 代码生成缓存：同一文件+同skiprows+同query 避免重复调用 LLM
    _code_cache: dict[tuple, str] = {}

    @tool
    def lookup_schema(category: str = "") -> str:
        """
        查询 data_schema.json 中已登记的文件模板信息，在 list_files/inspect_file 之前优先调用。
        - 不传参数：返回所有已知数据类别及其描述和可用文件期间概览
        - 传入类别名（如"考勤"）：返回该类别的完整模板（skiprows、列名、文件路径、备注）
        命中模板后可直接调用 execute_data_query，无需再调用 list_files 和 inspect_file。
        """
        try:
            with open(_SCHEMA_PATH, encoding="utf-8") as f:
                schema = json.load(f)
        except FileNotFoundError:
            return "data_schema.json 不存在，请使用 list_files 查找文件。"
        except Exception as e:
            return f"读取 data_schema.json 失败：{e}，请使用 list_files 查找文件。"

        if not category:
            lines = ["已登记的数据模板（可直接使用，无需 list_files/inspect_file）："]
            for cat, info in schema.items():
                periods = "、".join(info.get("files", {}).keys())
                lines.append(f"- {cat}：{info['description']}（可用期间：{periods}）")
            lines.append("\n如需完整列名和文件路径，请传入类别名再次调用，如 lookup_schema('考勤')。")
            return "\n".join(lines)

        if category not in schema:
            return f"未找到类别 '{category}'，已登记类别：{list(schema.keys())}。请改用 list_files 查找文件。"

        info = schema[category]
        columns_str = "、".join(info.get("columns", []))
        files_str = "\n".join(f"  {k}: {v}" for k, v in info.get("files", {}).items())
        return (
            f"类别：{category}\n"
            f"描述：{info['description']}\n"
            f"skiprows：{info['skiprows']}\n"
            f"列名：{columns_str}\n"
            f"备注：{info.get('notes', '无')}\n"
            f"文件列表：\n{files_str}"
        )

    @tool
    def list_files() -> str:
        """
        列出数据目录中所有可用的 Excel 文件及其完整路径。
        执行任何数据统计前必须先调用，不需要传入任何参数。
        """
        if not os.path.exists(DATA_DIR):
            return f"目录不存在：{DATA_DIR}"

        files = sorted([
            f for f in os.listdir(DATA_DIR)
            if f.endswith((".xlsx", ".xls", ".csv"))
        ])

        if not files:
            return "目录中没有找到任何数据文件。"

        result = [
            f"{f}  →  {os.path.join(DATA_DIR, f)}"
            for f in files
        ]
        return f"共找到 {len(result)} 个文件：\n" + "\n".join(result)

    @tool
    def inspect_file(file_path: str) -> str:
        """
        读取 Excel 文件的原始前10行内容，由 LLM 判断表头所在行位置。
        在 execute_data_query 之前必须调用，获取真实列名和表头行位置后再生成统计代码。
        参数：file_path - 文件的完整路径（从 list_files 结果中获取）
        """
        try:
            import pandas as pd
            # 读取原始前10行（不指定 header），让 LLM 判断哪一行是表头
            raw_df = pd.read_excel(file_path, header=None, nrows=10)
            raw_preview = raw_df.to_string(index=False, max_colwidth=30)

            # 同时用 header=0 读取列名作为参考（假设第一行为表头时的列名）
            try:
                header_df = pd.read_excel(file_path, nrows=3)
                col_info = (
                    f"【参考列名（假设第一行为表头）】\n"
                    f"列名：{header_df.columns.tolist()}\n"
                    f"数据类型：{header_df.dtypes.to_dict()}\n"
                    f"样本数据（前3行）：\n{header_df.to_string()}"
                )
            except Exception:
                col_info = "（无法以第一行为表头读取）"

            return (
                f"【原始前10行内容（行号从0开始）】\n"
                f"请根据以下内容判断哪一行是表头（列名所在行）：\n"
                f"{raw_preview}\n\n"
                f"{col_info}\n\n"
                f"【重要】请告诉用户：表头在第 N 行（行号从0开始），"
                f"则后续代码生成时使用 skiprows=N。"
            )
        except Exception as e:
            return f"读取失败：{e}"

    @tool
    def execute_data_query(query: str, file_path: str, skiprows: int = 0, columns: str = "") -> str:
        """
        根据自然语言描述生成 Python 代码并执行，对 Excel 文件做数据统计。
        支持多文件分析：file_path 可以是多个路径（用逗号分隔），会自动合并所有文件后统一分析。
        必须在 inspect_file 之后调用，使用真实列名生成代码。
        参数：
          query     - 自然语言描述要统计什么
          file_path - 文件完整路径（从 list_files 结果中获取），多个文件用逗号分隔
          skiprows  - 表头所在行号（从 inspect_file 结果中获取），表头在第N行则 skiprows=N
          columns   - inspect_file 返回的真实列名（逗号分隔字符串），必须填入以避免列名猜测错误
        适用：统计、汇总、排名、均值、跨月对比、条件筛选、全年综合分析。
        """
        file_paths = [p.strip() for p in file_path.split(",") if p.strip()]
        is_multi = len(file_paths) > 1
        hardcoded_re = re.compile(r'''(['"])[\w一-鿿]+\.(?:xlsx|xls|csv)\1''')

        def _clean(raw: str) -> str:
            raw = raw.replace("```python", "").replace("```", "").strip()
            return hardcoded_re.sub("DATA_PATH", raw)

        # ── 建议 1：将真实列名直接注入 prompt，消除 LLM 猜测 ──────────────
        col_hint = (
            f"【真实列名（必须严格使用，含空格/括号的列名用 df['列名'] 而非 df.列名）】\n{columns}\n\n"
            if columns else ""
        )

        # ── 建议 2：代码骨架——LLM 只填数据处理逻辑，不再重复写样板代码 ────
        if is_multi:
            load_block = (
                f"dfs = []\n"
                f"for p in DATA_PATH:\n"
                f"    d = pd.read_excel(p, skiprows={skiprows}) if p.endswith(('.xlsx', '.xls')) else pd.read_csv(p, skiprows={skiprows})\n"
                f"    d['_source_file'] = os.path.basename(p)\n"
                f"    dfs.append(d)\n"
                f"df = pd.concat(dfs, ignore_index=True)"
            )
        else:
            load_block = (
                f"df = pd.read_excel(DATA_PATH, skiprows={skiprows}) "
                f"if str(DATA_PATH).endswith(('.xlsx', '.xls')) else pd.read_csv(DATA_PATH, skiprows={skiprows})"
            )

        skeleton = (
            f"import pandas as pd, json, os, numpy as np\n\n"
            f"{load_block}\n\n"
            f"# === 数据处理逻辑（只填写此处，最后定义 result 字典） ===\n\n"
            f"# result = {{\"status\": \"success\", \"summary\": \"...\", \"data\": {{}}}}\n"
            f"# === 结束 ===\n"
            f"print(json.dumps(result, ensure_ascii=False, default=str))"
        )

        # ── 建议 3：精简 prompt，9 条规则压缩为骨架 + 3 条约束 ─────────────
        code_prompt = (
            f"{col_hint}"
            f"按以下骨架填写「数据处理逻辑」部分，输出完整代码（保留骨架其余部分不变）：\n\n"
            f"{skeleton}\n\n"
            f"约束：① 数字列用 pd.to_numeric(..., errors='coerce').fillna(0)；"
            f"② datetime 列用 .dt.strftime('%Y-%m-%d')（先用 is_datetime64_any_dtype 检查，禁止对数字列调用 pd.to_datetime）；"
            f"③ result 必须含 status/summary/data 三个字段；"
            f"④ DataFrame.reset_index() 用 names=（复数），Series.reset_index() 才用 name=（单数），混用必然报错。\n\n"
            f"需求：{query}"
        )

        cache_key = (file_path, skiprows, query)
        if cache_key in _code_cache:
            code = _code_cache[cache_key]
        else:
            code = _clean(llm.invoke(code_prompt).content)
            _code_cache[cache_key] = code

        payload_data_path = file_paths if is_multi else file_paths[0]

        def _run(c: str) -> dict:
            resp = _http_session.post(
                f"{EXECUTOR_URL}/execute_batch", json={"codes": [c], "data_path": payload_data_path}
            )
            if resp.status_code != 200:
                resp = _http_session.post(
                    f"{EXECUTOR_URL}/execute", json={"code": c, "data_path": payload_data_path}
                )
            return resp.json()

        # ── 规则安全校验 ──────────────────────────────────────────────────────
        try:
            check_generated_code(code, agent_name="data_agent", raise_on_critical=True)
        except RuleViolationError as e:
            return f"代码安全校验未通过：{e}\n请修改代码后重试。"

        exec_result = _run(code)

        # ── 建议 4：执行失败时在工具内部增量修复（最多 2 次），避免外层 ReAct 全量重生成 ──
        for _ in range(2):
            if exec_result.get("status") != "error":
                break
            fix_prompt = (
                f"以下 Python 代码执行报错，只修改出错的行，输出完整修复后的代码：\n\n"
                f"【原代码】\n{code}\n\n"
                f"【错误信息】\n{exec_result.get('error', '')}\n\n"
                f"{col_hint}"
                f"只输出修复后的纯 Python 代码，不含说明。"
            )
            code = _clean(llm.invoke(fix_prompt).content)
            _code_cache[cache_key] = code
            try:
                check_generated_code(code, agent_name="data_agent", raise_on_critical=True)
            except RuleViolationError as e:
                return f"代码安全校验未通过：{e}"
            exec_result = _run(code)

        if exec_result.get("status") == "error":
            return f"执行失败：{exec_result.get('error', '未知错误')}\n生成代码：\n{code}"

        # /execute_batch 返回 outputs 列表，/execute 返回 output 字符串
        return exec_result.get("outputs", [exec_result.get("output", "")])[0]

    return create_react_agent(
        model=llm,
        name="data_agent",
        tools=[lookup_schema, list_files, inspect_file, execute_data_query],
        prompt="""你是企业数据分析专家，处理统计、汇总、排名、对比、筛选等数据计算任务。

【工具说明】
- lookup_schema：查询已登记的文件模板，优先调用
- list_files：查看数据目录中有哪些文件（schema 未命中时使用）
- inspect_file：读取文件原始内容，判断表头行位置和列名（schema 未命中时使用）
- execute_data_query：生成 Python 代码并执行统计，需传入 query、file_path、skiprows、columns
  - columns 参数：必须使用真实列名，以逗号分隔填入（如 "序号,经费类别,实际支出 (元),支出日期"）

【优先流程——每次任务开始时执行】
1. 先调用 lookup_schema（不传参）查看有哪些已登记模板
2. 若用户问题匹配某类别，再调用 lookup_schema(category) 获取完整信息（skiprows、列名、文件路径）
   → 直接调用 execute_data_query，跳过 list_files 和 inspect_file
3. 若未匹配到任何类别，再按原流程：list_files → inspect_file → execute_data_query

【效率规则——减少等待时间，提升响应速度】
4. 合并统计：对同一文件的多项需求（如"硬件采购+软件采购"）应合并为一次 execute_data_query，用多个变量存储结果
5. 多文件合并：同类型文件用逗号分隔 file_path 一次性传入（如 "file1.xlsx,file2.xlsx"），共享一次读取和执行。合并后每行会带 _source_file 列标记来源文件名，按文件名中的月份/类别分组即可
6. 禁止拆句：不要将"列出A和B以及C"拆成三次独立调用，拆句会导致重复加载文件和重复等待

【硬性约束——运行环境物理限制，违反必然失败】
1. execute_data_query 的 skiprows 参数必须与文件实际表头行一致（从 schema 或 inspect_file 获取）
2. 生成代码运行在沙箱中，只能用 pandas/json/os 等标准库，禁调 agent 工具
3. .xlsx/.xls→pd.read_excel(), .csv→pd.read_csv()，用错函数会报错
4. 工具调用判断标准：
   a) 涉及具体数值/统计/排名/筛选的问题 → 必须调 execute_data_query 从文件获取真实数据
   b) 纯对话类问题（如"你是谁""能做什么""刚才问了什么"）→ 无需调工具
   c) 不确定时 → 优先调工具，宁可多查一次也不凭空回答
5. 历史回复中的数据值为当时查询结果，回答新问题必须从文件重新获取，不得直接复用
6. 当工具返回异常值（如 0.0、空结果）时，不得编造解释，应如实报告并建议重新查询

【回答语言】中文，执行失败时如实告知，不编造数据。"""
    )
