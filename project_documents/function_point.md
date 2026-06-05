# EnterpriseKnowledgeAgent 功能点清单

> 最后更新：2026-06-04 | 基于 `doc_agent` 分支代码梳理

---

## 一、多入口与认证

| # | 功能 | 说明 |
|---|---|---|
| 1 | **Streamlit 原生前端** (`app.py` + `pages/`) | 登录 / 对话 / 文档编写 / 管理后台 / 首页 |
| 2 | **FastAPI REST 后端** (`api.py` :8000) | SSE 流式对话 + JWT 鉴权，与 HTML 前端解耦 |
| 3 | **HTML 静态前端** (`html_files/` 6 页) | login / home / admin / setting / doc-write / more-features |
| 4 | **JWT 认证** | 8 小时 token，角色分流登录（管理员/用户身份严格匹配）|
| 5 | **三角色权限** | admin(全部) / user(对话+文档编写) / visitor(仅提示无权限) |

## 二、多智能体核心 (Supervisor 路由)

| # | 子 Agent | 核心能力 |
|---|---|---|
| 1 | **RAG 文档问答** | 查询改写 → Dify 语义检索 → 四级答案验证 → 自动重试；经验记忆命中则直接复用缓存答案 |
| 2 | **数据分析** | 数据模板快速匹配(7类) 或 文件探查→代码生成→沙箱执行；失败时增量修复出错行，支持多文件合并统计 |
| 3 | **文档编写** | 目录生成 → 用户确认 → 逐章分段输出 Markdown；支持知识库检索+附件参考融合 |
| 4 | **API 接口调用** | 接口发现 / 分组浏览 / 参数填充 / 一键调用(GET/POST/PUT/DELETE)；支持 bearer/apikey/noauth 三种认证 |

### 对话基础设施

- Supervisor Router 智能分类 + 支持绕过路由直接指定 Agent
- 双重记忆持久化（LangGraph checkpoint + SQLite 手动注入），rerun 不丢上下文
- 历史回复语义降权，避免 LLM 将旧回复当作当前事实
- 多轮对话 CRUD + 智能标题生成 + 相对时间显示 + 流式步骤日志回溯
- **Q&A 经验记忆**：Qwen Embedding v3 向量化历史问答对，相似度 ≥ 0.80 直接复用缓存（自动过滤闲聊和过短问题）

## 三、安全体系

| # | 能力 | 说明 |
|---|---|---|
| 1 | **规则引擎** | YAML 配置驱动，四层分类(SAFETY/STYLE/QUALITY/DOMAIN) × 五阶段检查(PRE_GENERATE → POST_RETRIEVE) × 四级严重程度 |
| 2 | **柔性拦截** | 仅 CRITICAL 阻断流程，WARNING/INFO 仅日志记录，异常默认放行保证主流程不中断 |
| 3 | **代码沙箱** | 进程池预热 + namespace 隔离执行，超时保护 30s，批量执行共享进程池 |

## 四、文档编写流程

| 步骤 | 说明 |
|------|------|
| 目录生成 | 根据需求(+附件+知识库资料)生成多级编号目录，支持用户反馈迭代优化 |
| 逐章生成 | 确认目录后逐章节调用 LLM，每章传入前 2 章内容确保衔接，APIConnectionError 自动指数退避重试 |
| 参考融合 | 合并附件内容与知识库检索结果为统一参考文本，LLM 引用时可标注来源 |
| 质量校验 | 完成后经规则引擎检查，技术错误类(GEN_QUALITY-002)做友好替换 |

## 五、管理员功能

| # | 功能 | 说明 |
|---|---|---|
| 1 | **仪表盘** | 用户总数 / 今日活跃 / 今日对话 / 历史总量 |
| 2 | **用户管理** | 新建(防重名)、改角色、启禁用账号 |
| 3 | **审计日志** | 按用户/操作类型/日期筛选，全覆盖 login/logout/chat/admin_op/update_password 等 |
| 4 | **知识库浏览** | 双层分页查看知识库列表及内部文档状态 |
| 5 | **数据文件查看** | DATA_DIR 下文件名/扩展名/大小 |
| 6 | **接口配置管理** | 读写 interface_configs.json，配合 api_agent 使用 |

## 六、个人设置

修改显示名称(≤50字) / 修改密码(验旧密码≥6位) / 更新头像(base64 data URL)

## 七、技术栈与外部依赖

| 组件 | 说明 |
|------|------|
| LLM | 阿里千问 qwen-plus |
| Embedding | Qwen text-embedding-v3 (1024维)，用于 Q&A 缓存 |
| Rerank | Dify Rerank API |
| 追踪 | LangSmith 全链路追踪 |
| 数据库 | SQLite WAL 模式，幂等建表+自动迁移 |
| 部署 | start.bat 一键启动四端口服务 (:8501 Streamlit / :8000 FastAPI / :8002 Alarm Mock / :8100 内部调度) |
