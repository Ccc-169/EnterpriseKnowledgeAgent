# data_agent 结构图

## 整体架构

```
用户提问
  │
  ▼
┌─────────────┐     路由分发     ┌──────────────────────────────────────┐
│  主 Agent    │ ──────────────▶ │  data_agent (ReAct Agent)            │
│  (app.py)   │                 │  模型: LLM  工具: 3个                │
└─────────────┘                 └──────────┬───────────────────────────┘
                                           │
                    ┌──────────────────────┼──────────────────────┐
                    │                      │                      │
                    ▼                      ▼                      ▼
             ┌────────────┐      ┌──────────────┐      ┌──────────────────┐
             │ list_files │      │ inspect_file │      │execute_data_query│
             │  列出文件   │      │  预览表头     │      │  生成+执行代码   │
             └────────────┘      └──────────────┘      └────────┬─────────┘
                                                                          │
                                                                          ▼
                                                               ┌────────────────────┐
                                                               │ code_executor 服务  │
                                                               │ FastAPI :8001      │
                                                               │ 进程池预热执行      │
                                                               │ (multiprocessing)  │
                                                               └────────────────────┘
```

## 3个工具调用链路

```
① list_files()                    ② inspect_file(file_path)
   │                                 │
   │ 读取 DATA_DIR 目录              │ pd.read_excel(header=None, nrows=10)
   │ 返回文件名+完整路径              │ 返回原始前10行 + 参考列名
   │                                 │ LLM 自行判断 skiprows=N
   ▼                                 ▼
  文件列表                           表头行号 + 列名信息
```

```
③ execute_data_query(query, file_path, skiprows)
   │
   ├─ 1. 解析文件路径
   │     file_path="a.xlsx,b.xlsx" → file_paths=["a.xlsx","b.xlsx"]
   │     is_multi = len > 1
   │
   ├─ 2. 构建 code_prompt (9条规则 + 多文件规则)
   │     ┌─────────────────────────────────────────────────┐
   │     │ 规则1: 禁止硬编码文件名，必须用 DATA_PATH        │
   │     │ 规则2: DATA_PATH 类型 (str/list)                │
   │     │ 规则3: 单文件读取模板                            │
   │     │ 规则4: 多文件读取模板 (for循环+_source_file)     │
   │     │ 规则5: 禁调 agent 工具                          │
   │     │ 规则6: 数字列 pd.to_numeric(...,errors='coerce') │
   │     │ 规则7: 仅对 datetime 类型列做字符串转换 ★修复    │
   │     │ 规则8: 最后一行 print(json.dumps(result,...))    │
   │     │ 规则9: result={status/summary/data}             │
   │     │ + multi_file_rules (is_multi时追加)             │
   │     └─────────────────────────────────────────────────┘
   │
   ├─ 3. LLM 生成代码 (带缓存)
   │     cache_key = (file_path, skiprows, query)
   │     ├── 命中缓存 → 直接取 code
   │     └── 未命中   → llm.invoke(code_prompt)
   │                     → 去除 markdown 围栏
   │                     → 正则替换硬编码文件名为 DATA_PATH
   │                     → 写入缓存
   │
   ├─ 4. 发送到 code_executor
   │     payload.data_path = file_paths(多文件) 或 file_paths[0](单文件)
   │     优先 POST /execute_batch → 失败回退 /execute
   │
   └─ 5. 返回结果
        ├── status=error → 返回错误信息+生成代码
        └── status=success → 返回 output 内容
```

## code_executor 执行流程（进程池预热版）

```
启动时：
  FastAPI lifespan → multiprocessing.Pool(N, initializer=_worker_init)
                   → N 个 Worker 各预加载 pandas/json/os/warnings
                   → Pool 大小由 EXECUTOR_POOL_SIZE 配置（默认 min(4, cpu_count)）

请求时：
  POST /execute_batch  或  POST /execute
     │
     ▼
  _run_code(code, data_path)
     │
     ├─ 1. pool.apply_async(_worker_execute, (code, data_path))
     │
     ├─ 2. Worker 中 _worker_execute 执行：
     │     ┌─────────────────────────────────────┐
     │     │ namespace = {                       │
     │     │   pd: 预加载的 pandas,              │
     │     │   json: 预加载的 json,              │
     │     │   os: 预加载的 os,                  │
     │     │   DATA_PATH: 文件路径(str/list)     │
     │     │ }                                   │
     │     │ exec(code, namespace)  ← 隔离执行   │
     │     │ stdout → StringIO 捕获 print 输出   │
     │     └─────────────────────────────────────┘
     │
     ├─ 3. .get(timeout=30)  ← 超时控制
     │
     └─ 4. 返回 {status, output, error}
          /execute_batch 额外按 __BATCH_SEP__ 拆分为 outputs 列表

关闭时：
  lifespan → pool.terminate() + pool.join()
```

## 多文件查询关键路径 (★本次修复)

```
多文件 file_path="1月.xlsx,2月.xlsx,...,12月.xlsx"
   │
   ▼  is_multi=True
代码模板 (规则4 + multi_file_rules):
   │
   │  dfs = []
   │  for p in DATA_PATH:
   │      d = pd.read_excel(p, skiprows=N)
   │      d['_source_file'] = os.path.basename(p)   ← 注入来源标识
   │      dfs.append(d)
   │  df = pd.concat(dfs, ignore_index=True)
   │
   ▼
合并后 df 示例:
   ┌──────┬──────┬─────────────────┐
   │ 姓名 │ 出勤 │ _source_file     │
   ├──────┼──────┼─────────────────┤
   │ 张三 │  22  │ 1月考勤.xlsx     │
   │ 张三 │  20  │ 2月考勤.xlsx     │
   │ ...  │ ...  │ ...              │
   └──────┴──────┴─────────────────┘
   │
   ▼  LLM 可从 _source_file 提取月份分组
   df.groupby(df['_source_file'].str.extract(r'(\d+)月')[0])...
```

## 关键设计决策

| 项目 | 设计 | 原因 |
|------|------|------|
| LLM 生成代码 | 沙箱执行，非本地 eval | 安全隔离 |
| 进程池预热 | multiprocessing.Pool + initializer | 消除 pandas 冷启动 ~1.5s，单次查询 ~2.5s→0.6s |
| namespace 隔离 | 每次 exec 用全新 dict | 进程复用但状态不泄漏 |
| skiprows 由 LLM 判断 | inspect_file 只展示原始行 | 表头位置不固定，需人工/LLM判断 |
| 代码缓存 | (file_path, skiprows, query) 为 key | 同查询避免重复调用 LLM |
| 硬编码文件名正则替换 | 兜底后处理 | LLM 偶尔无视规则1 |
| _source_file 列注入 | 多文件 concat 时标记来源 | 合并后无法区分数据来源 |
| 规则7 条件判断 | 仅 datetime 类型列转字符串 | 避免整数列被 pd.to_datetime 误杀 |
