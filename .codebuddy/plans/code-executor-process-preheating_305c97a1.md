---
name: code-executor-process-preheating
overview: 将 code_executor.py 从「每次请求创建子进程」改为「进程池预热」架构，消除 pandas 冷启动开销（~1.5s/次），提升 data_agent 查询响应速度。
todos:
  - id: refactor-code-executor
    content: 改造 code_executor.py：Pool预热 + exec执行 + stdout捕获 + 超时控制 + lifespan管理
    status: completed
  - id: update-config
    content: 更新 .env / .env.example / core/config.py 新增 EXECUTOR_POOL_SIZE 配置
    status: completed
    dependencies:
      - refactor-code-executor
  - id: update-docs
    content: 更新 data_agent_structure.md 和 Dev_log.md
    status: completed
    dependencies:
      - refactor-code-executor
  - id: smoke-test
    content: 启动服务验证：单次查询 + 并发查询 + 超时场景 + 异常恢复
    status: completed
    dependencies:
      - update-config
  - id: 17803fbe
    content: 同步更新Dev_log.md
    status: completed
---

## 产品概述

将 `code_executor.py` 从"每次 subprocess 冷启动"改为"进程池预热"模式，消除每次查询重复 `import pandas` 的 ~1.5s 开销，提升 data_agent 执行速度。

## 核心功能

- 启动时预创建 N 个 Worker 进程，每个预加载 pandas/json/os/warnings
- 请求到达时直接在预热进程中执行代码，跳过冷启动
- API 接口保持不变（/execute, /execute_batch），调用方零改动
- 进程级隔离：每次 exec 在独立 namespace 中运行，变量不泄漏
- 超时控制：单个任务 30s 超时，超时后 Worker 自动回收
- 优雅关闭：FastAPI lifespan 管理 Pool 的创建和销毁
- Windows 兼容：multiprocessing 的 `if __name__ == '__main__'` 保护

## 技术栈

- 沿用现有：FastAPI + uvicorn + Python 3.x
- 新增：`multiprocessing.Pool`（标准库，零依赖）

## 实现方案

### 核心策略

用 `multiprocessing.Pool(initializer=_worker_init)` 替换 `subprocess.run`。Pool 启动时每个 Worker 预加载 pandas，请求到达时通过 `pool.apply()` 在预热进程中 `exec()` 执行用户代码。

### 关键技术决策

| 决策 | 选择 | 理由 |
| --- | --- | --- |
| 进程模型 | multiprocessing.Pool | 进程级隔离 + 预加载 pandas，比 subprocess 快 60%+ |
| 执行方式 | exec(code, namespace) | namespace 隔离变量，进程复用但状态不泄漏 |
| 并发控制 | pool.apply() 同步阻塞 | 简单可靠，Pool 大小即并发上限，超出自动排队 |
| 超时机制 | pool.apply_async().get(timeout=30) | apply() 无超时参数，需用 apply_async + get 替代 |
| Pool 生命周期 | FastAPI lifespan | 启动时创建 Pool，关闭时 terminate，避免孤儿进程 |
| Pool 大小 | 默认 min(4, cpu_count)，可配 | 5-8 用户场景下 4 Worker 足够，内存约 1.2GB |


### 为什么不用其他方案

- **常驻 stdin 进程**：单进程串行，5-8 人全部排队；进程崩溃则全服务不可用
- **内嵌 exec()**：无进程隔离，用户代码可污染 FastAPI 进程状态，死循环直接卡死主服务
- **subprocess（当前）**：每次冷启动 pandas ~1.5s，5-8 人并发内存飙升

### 安全性保障

```
每次 exec 隔离措施：
1. 全新 namespace 字典，注入白名单模块 (pd, json, os, DATA_PATH)
2. exec 后 namespace 立即丢弃，变量不残留到下次执行
3. Worker 进程本身长期存活，但每次执行的状态完全隔离
4. 超时任务不卡死 Worker：apply_async + get(timeout=30) 超时后进程可被 Pool 回收
5. 若 Worker 因异常崩溃，Pool 自动创建新 Worker 补充（自带机制）
```

### 性能预期

| 指标 | 改造前 (subprocess) | 改造后 (Pool) |
| --- | --- | --- |
| 单次执行 | ~2.5s（含 pandas 冷启动） | ~0.6s |
| 5 人并发 | 5 进程同时冷启动，~2.5-4s | 4 人 ~0.6s，1 人等 ~1-2s |
| 内存占用（5 人） | ~2.4GB（5 × ~500MB） | ~1.2GB（4 Worker × ~300MB） |


## 实现要点

1. **Windows 兼容**：multiprocessing 在 Windows 上用 spawn 模式，需要 `if __name__ == '__main__'` 保护 Pool 创建代码，否则子进程递归导入会崩溃
2. **namespace 隔离**：每次 `exec()` 使用全新 dict 作为 namespace，注入 `pd/json/os/DATA_PATH`，执行后丢弃，防止变量泄漏
3. **stdout 捕获**：`exec()` 不走 subprocess，需要用 `io.StringIO` 临时重定向 `sys.stdout` 来捕获 `print()` 输出
4. **超时处理**：`pool.apply()` 是同步阻塞无超时参数，改用 `pool.apply_async().get(timeout=30)` 实现超时控制
5. **Pool 回收**：超时后 Worker 进程可能仍在执行，Pool 的 `terminate()` 可强制杀掉所有 Worker 再重建

## 架构设计

```
改造前：
  HTTP请求 → FastAPI → _run_code() → 写tmp.py → subprocess.run(["python", tmp.py]) → 读stdout
                                    每次都: 启动解释器 + import pandas + 执行 + 销毁进程

改造后：
  启动时: FastAPI lifespan → Pool(N, initializer=_worker_init) → N个Worker各预加载pandas
  
  HTTP请求 → FastAPI → pool.apply_async(_worker_execute, ...) → Worker中exec(code, namespace)
                    → 重定向sys.stdout捕获print输出 → get(timeout=30) → 返回结果
                    Worker存活，等待下一个任务
```

## 目录结构

```
d:\App_data\HNGD-Agent\HNGD-backend\
├── code_executor.py           # [MODIFY] 核心改造：subprocess → multiprocessing.Pool
│                             # - 新增 _worker_init()：预加载 pandas/json/os/warnings
│                             # - 新增 _worker_execute()：exec(code, namespace) + stdout 捕获
│                             # - 改造 _run_code()：调用 pool.apply_async + timeout
│                             # - 新增 lifespan()：管理 Pool 创建和销毁
│                             # - Pool 大小可通过 EXECUTOR_POOL_SIZE 环境变量配置
│
├── .env                      # [MODIFY] 新增 EXECUTOR_POOL_SIZE 配置项
├── .env.example              # [MODIFY] 新增 EXECUTOR_POOL_SIZE 配置项说明
├── core/config.py            # [MODIFY] 新增 EXECUTOR_POOL_SIZE 读取
│
├── project_documents/
│   ├── data_agent_structure.md  # [MODIFY] 更新 code_executor 执行流程图
│   └── Dev_log.md               # [MODIFY] 记录本次改造
│
├── agents/data_agent.py      # [无需修改] HTTP 调用接口不变
├── start.bat                 # [无需修改] 启动命令不变
└── start.sh                  # [无需修改] 启动命令不变
```