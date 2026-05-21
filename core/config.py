# core/config.py — 统一读取 .env 配置
import os
from dotenv import load_dotenv

load_dotenv()

# ── LLM 配置 ──────────────────────────────────────────
QWEN_API_KEY = os.environ.get("QWEN_API_KEY", "")

# ── Dify 知识库 ────────────────────────────────────────
DIFY_DATASET_KEY = os.environ.get("DIFY_DATASET_KEY", "")
DIFY_KB_ID = os.environ.get("DIFY_KB_ID", "")

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
