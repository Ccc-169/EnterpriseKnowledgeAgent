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

# ── 全局规则引擎 ───────────────────────────────────────
RULES_CONFIG_PATH = os.environ.get("RULES_CONFIG_PATH", "./rules/rule_config.yaml")
RULES_ENABLED = os.environ.get("RULES_ENABLED", "true").lower() == "true"
RULES_BLOCK_ON_CRITICAL = os.environ.get("RULES_BLOCK_ON_CRITICAL", "true").lower() == "true"
