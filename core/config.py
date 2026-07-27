# core/config.py — 统一读取 .env 配置
import os
from dotenv import load_dotenv

load_dotenv()

# ── LLM 配置 ──────────────────────────────────────────
QWEN_API_KEY = os.environ.get("QWEN_API_KEY", "")

# ── RAGFlow 知识库 ─────────────────────────────────────
RAGFLOW_API_BASE   = os.environ.get("RAGFLOW_API_BASE", "http://localhost/api/v1")
RAGFLOW_API_KEY    = os.environ.get("RAGFLOW_API_KEY", "")
RAGFLOW_DATASET_ID = os.environ.get("RAGFLOW_DATASET_ID", "")

# ── Dify 知识库（已弃用） ──────────────────────────────
DIFY_API_BASE    = os.environ.get("DIFY_API_BASE", "https://api.dify.ai/v1")
DIFY_DATASET_KEY = os.environ.get("DIFY_DATASET_KEY", "")
DIFY_KB_ID       = os.environ.get("DIFY_KB_ID", "")

# ── 代码沙箱 ───────────────────────────────────────────
EXECUTOR_URL = os.environ.get("EXECUTOR_URL", "http://localhost:8001")
EXECUTOR_POOL_SIZE = int(os.environ.get("EXECUTOR_POOL_SIZE", "0")) or min(4, os.cpu_count() or 2)

# ── 数据文件目录 ────────────────────────────────────────
DATA_DIR = os.environ.get("DATA_DIR", "./data/files")

# ── 安全配置 ───────────────────────────────────────────
SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-to-a-random-32-char-string")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))

# ── 数据库 ─────────────────────────────────────────────
DB_PATH = os.environ.get("DB_PATH", "./data/hngd.db")

# ── 会话并发控制 ───────────────────────────────────────
# CHAT_MAX_CONCURRENCY：全系统同时生成的回复数上限。严格对齐 Ollama 的 -np 1，
# 设为 1。设大于 1 只会让请求堆在 Ollama 内部队列、拿不到应用层排队位次。
CHAT_MAX_CONCURRENCY      = int(os.environ.get("CHAT_MAX_CONCURRENCY", "1"))
# 客户端断开（切页/关页）时是否自动取消其后台生成任务。-np 1 下默认必须开启。
CHAT_CANCEL_ON_DISCONNECT = os.environ.get("CHAT_CANCEL_ON_DISCONNECT", "true").lower() == "true"
# to_thread 默认线程池上限。线程在等 Ollama 不耗 CPU，真正闸门是信号量。
CHAT_THREAD_POOL_SIZE     = int(os.environ.get("CHAT_THREAD_POOL_SIZE", "32"))
# 断开检测轮询间隔（秒）。
CHAT_DISCONNECT_POLL_SEC  = float(os.environ.get("CHAT_DISCONNECT_POLL_SEC", "0.5"))

# ── 全局规则引擎 ───────────────────────────────────────
RULES_CONFIG_PATH = os.environ.get("RULES_CONFIG_PATH", "./rules/rule_config.yaml")
RULES_ENABLED = os.environ.get("RULES_ENABLED", "true").lower() == "true"
RULES_BLOCK_ON_CRITICAL = os.environ.get("RULES_BLOCK_ON_CRITICAL", "true").lower() == "true"

# ── KB 全局指纹 ────────────────────────────────────────
# 调 RAGFlow 算指纹的进程内缓存 TTL（秒）。5 分钟内不重复打 RAGFlow。
KB_FINGERPRINT_TTL_SECONDS = int(os.environ.get("KB_FINGERPRINT_TTL_SECONDS", "300"))

# ── QA 缓存分层阈值（双阈值短路）─────────────────────
# 候选门槛：相似度 < 此值的连候选都不算。
QA_CACHE_MIN_CONFIDENCE = float(os.environ.get("QA_CACHE_MIN_CONFIDENCE", "0.80"))
# 中置信门槛：[MIN, MED) 走"参考骨架"路径。
QA_CACHE_MED_CONFIDENCE = float(os.environ.get("QA_CACHE_MED_CONFIDENCE", "0.85"))
# 高置信门槛：≥ 此值走"短路"路径，直接返回缓存答案。
QA_CACHE_HIGH_CONFIDENCE = float(os.environ.get("QA_CACHE_HIGH_CONFIDENCE", "0.90"))
# 候选召回 top K。
QA_CACHE_TOP_K = int(os.environ.get("QA_CACHE_TOP_K", "3"))

# ── QA 缓存灰度开关（feature flags）───────────────────
# 关掉后所有缓存视为 kb_version 缺失 → 永远 miss → 退化为旧行为。
ENABLE_KB_FINGERPRINT = os.environ.get("ENABLE_KB_FINGERPRINT", "true").lower() == "true"
# 关掉后高置信也走完整 RAG（保留 kb_version 校验过滤，但不再"直接返回缓存"）。
ENABLE_QA_CACHE_SHORTCIRCUIT = os.environ.get("ENABLE_QA_CACHE_SHORTCIRCUIT", "true").lower() == "true"
