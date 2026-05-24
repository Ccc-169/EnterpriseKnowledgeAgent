# agents/data_agent.py
import os
import re
import requests
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

# 复用 TCP 连接，避免每次请求重新建连（~2s → <10ms）
_http_session = requests.Session()

# ── 规则引擎导入 ─────────────────────────────────────
from rules.integration import check_generated_code
from rules.engine import RuleViolationError


def create_data_agent(llm):

    DATA_DIR     = os.environ["DATA_DIR"]
    EXECUTOR_URL = os.environ["EXECUTOR_URL"]

    # 代码生成缓存：同一文件+同skiprows+同query 避免重复调用 LLM
    _code_cache: dict[tuple, str] = {}

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
    def execute_data_query(query: str, file_path: str, skiprows: int = 0) -> str:
        """
        根据自然语言描述生成 Python 代码并执行，对 Excel 文件做数据统计。
        支持多文件分析：file_path 可以是多个路径（用逗号分隔），会自动合并所有文件后统一分析。
        必须在 inspect_file 之后调用，使用真实列名生成代码。
        参数：
          query     - 自然语言描述要统计什么
          file_path - 文件完整路径（从 list_files 结果中获取），多个文件用逗号分隔
          skiprows  - 表头所在行号（从 inspect_file 结果中获取），表头在第N行则 skiprows=N
        适用：统计、汇总、排名、均值、跨月对比、条件筛选、全年综合分析。
        """
        file_paths = [p.strip() for p in file_path.split(",") if p.strip()]
        is_multi = len(file_paths) > 1

        # 多文件时提示代码必须先合并再分析
        multi_file_rules = ""
        if is_multi:
            multi_file_rules = f"""
8. 多文件须逐个读取并标记来源（用于按文件分组）：
dfs=[]
for p in DATA_PATH:
    d = pd.read_excel(p,skiprows={skiprows}) if p.endswith(('.xlsx','.xls')) else pd.read_csv(p,skiprows={skiprows})
    d['_source_file'] = os.path.basename(p)
    dfs.append(d)
df = pd.concat(dfs, ignore_index=True)
"""

        code_prompt = f"""生成 Python 统计代码，规则：
1. 必须使用 DATA_PATH 变量读取文件，禁止硬编码任何文件名（如"data.xlsx"、"file.xlsx"等都是错误的）
2. DATA_PATH {'是文件路径列表(list)，必须逐个读取后合并' if is_multi else '是单个文件路径(str)，直接传入 pd.read_excel/read_csv'}
3. 单文件：df = pd.read_excel(DATA_PATH, skiprows={skiprows})  或  pd.read_csv(DATA_PATH, skiprows={skiprows})
4. 多文件：dfs=[]; 
for p in DATA_PATH:
    d = pd.read_excel(p,skiprows={skiprows}) if p.endswith(('.xlsx','.xls')) else pd.read_csv(p,skiprows={skiprows})
    d['_source_file'] = os.path.basename(p)
    dfs.append(d)
df = pd.concat(dfs, ignore_index=True)
5. 禁调 inspect_file/list_files 等 agent 工具（沙箱无这些工具）
6. 数字列用 pd.to_numeric(..., errors='coerce').fillna(0)
7. 仅对pandas已识别为datetime类型的列做字符串转换：if pd.api.types.is_datetime64_any_dtype(df['列名']): df['列名']=df['列名'].dt.strftime('%Y-%m-%d')。禁止对纯数字列调用pd.to_datetime
8. 最后一行：print(json.dumps(result, ensure_ascii=False, default=str))
9. result={{status/summary/data}} 三个字段
只输出纯 Python 代码，不含说明和 markdown

需求：{query}
"""
        cache_key = (file_path, skiprows, query)
        if cache_key in _code_cache:
            code = _code_cache[cache_key]
        else:
            code = llm.invoke(code_prompt).content
            code = code.replace("```python", "").replace("```", "").strip()
            # 后处理兜底：将 LLM 硬编码的文件名替换为 DATA_PATH 变量
            hardcoded_pattern = re.compile(
                r'''(['"])[\w\u4e00-\u9fff]+\.(?:xlsx|xls|csv)\1'''
            )
            code = hardcoded_pattern.sub('DATA_PATH', code)
            _code_cache[cache_key] = code

        # 统一只发一次请求：多文件传列表，单文件传字符串
        payload_data_path = file_paths if is_multi else file_paths[0]

        # ── 规则检查：仅 CRITICAL 危险操作（os.system/eval/subprocess 等）才会阻断 ──
        try:
            check_generated_code(code, agent_name="data_agent", raise_on_critical=True)
        except RuleViolationError as e:
            return f"代码安全校验未通过：{e}\n请修改代码后重试（提示：os.path 操作是安全的，但 os.system/eval/subprocess 等危险调用已拦截）。"

        # 优先使用 /execute_batch，若服务未更新则回退到 /execute
        batch_payload = {"codes": [code], "data_path": payload_data_path}
        simple_payload = {"code": code, "data_path": payload_data_path}

        resp = _http_session.post(f"{EXECUTOR_URL}/execute_batch", json=batch_payload)
        if resp.status_code != 200:
            resp = _http_session.post(f"{EXECUTOR_URL}/execute", json=simple_payload)

        result = resp.json()
        if result.get("status") == "error":
            return f"执行失败：{result.get('error', '未知错误')}\n生成代码：\n{code}"
        # /execute_batch 返回 outputs 列表，/execute 返回 output 字符串
        return result.get("outputs", [result.get("output", "")])[0]

    return create_react_agent(
        model=llm,
        name="data_agent",
        tools=[list_files, inspect_file, execute_data_query],
        prompt="""你是企业数据分析专家，处理统计、汇总、排名、对比、筛选等数据计算任务。

【工具说明】
- list_files：查看数据目录中有哪些文件
- inspect_file：读取文件原始内容，判断表头行位置和列名
- execute_data_query：生成 Python 代码并执行统计，需传入 query、file_path、skiprows

【效率规则——减少等待时间，提升响应速度】
4. 合并统计：对同一文件的多项需求（如"硬件采购+软件采购"）应合并为一次 execute_data_query，用多个变量存储结果
5. 多文件合并：同类型文件用逗号分隔 file_path 一次性传入（如 "file1.xlsx,file2.xlsx"），共享一次读取和执行。合并后每行会带 _source_file 列标记来源文件名，按文件名中的月份/类别分组即可
6. 禁止拆句：不要将"列出A和B以及C"拆成三次独立调用，拆句会导致重复加载文件和重复等待
7. 失败先修代码：执行失败时优先检查 skiprows 是否正确、是否对纯数字列误调了 pd.to_datetime，先修改代码后重试，而非拆分查询

【硬性约束——运行环境物理限制，违反必然失败】
1. execute_data_query 的 skiprows 参数必须传入 inspect_file 判断出的表头行号
2. 生成代码运行在沙箱中，只能用 pandas/json/os 等标准库，禁调 agent 工具
3. .xlsx/.xls→pd.read_excel(), .csv→pd.read_csv()，用错函数会报错

【回答语言】中文，执行失败时如实告知，不编造数据。"""
    )