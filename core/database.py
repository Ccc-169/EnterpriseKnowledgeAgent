# core/database.py — SQLite 连接管理与表初始化
import sqlite3
import os
from core.config import DB_PATH

_CREATE_USERS_TABLE = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    display_name  TEXT,
    role          TEXT NOT NULL DEFAULT 'user',
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

_CREATE_AUDIT_LOGS_TABLE = """
CREATE TABLE IF NOT EXISTS audit_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    username    TEXT NOT NULL,
    action      TEXT NOT NULL,
    agent_used  TEXT,
    question    TEXT,
    status      TEXT DEFAULT 'success',
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

_CREATE_CONVERSATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS conversations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    title       TEXT NOT NULL DEFAULT '新对话',
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
"""

_CREATE_MESSAGES_TABLE = """
CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    role            TEXT NOT NULL,
    content         TEXT NOT NULL,
    steps_log       TEXT,
    agent_used      TEXT,
    question_vec    TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);
"""

_MIGRATE_MESSAGES_QUESTION_VEC = """
ALTER TABLE messages ADD COLUMN question_vec TEXT;
"""

_MIGRATE_USERS_AVATAR = """
ALTER TABLE users ADD COLUMN avatar TEXT;
"""

_CREATE_DOCUMENT_HISTORY_TABLE = """
CREATE TABLE IF NOT EXISTS document_history (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             INTEGER NOT NULL,
    title               TEXT NOT NULL DEFAULT '新建文档',
    requirements        TEXT,
    outline             TEXT,
    content             TEXT,
    reference_context   TEXT,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
"""

_CREATE_DATA_INTERFACES_TABLE = """
CREATE TABLE IF NOT EXISTS data_interfaces (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    service_name    TEXT NOT NULL,
    file_name       TEXT NOT NULL,
    path            TEXT NOT NULL,
    method          TEXT NOT NULL,
    summary         TEXT,
    operation_id    TEXT,
    parameters      TEXT,
    tags            TEXT,
    spec_file_path  TEXT NOT NULL,
    file_mtime      REAL,
    enabled         INTEGER NOT NULL DEFAULT 1,
    indexed_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(service_name, file_name, path, method)
);
"""

_CREATE_USER_INTERFACE_ACCESS_TABLE = """
CREATE TABLE IF NOT EXISTS user_interface_access (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    interface_id    INTEGER NOT NULL,
    granted         INTEGER NOT NULL DEFAULT 0,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (interface_id) REFERENCES data_interfaces(id) ON DELETE CASCADE,
    UNIQUE(user_id, interface_id)
);
"""

# ── QA 经验记忆缓存（KB 指纹 + 双阈值短路） ────────────
# 用于 cache_check 节点的快速命中。
# 旧方案是把 question_vec 存在 messages.question_vec，本表是独立的新缓存表。
# 读取和写入都走本表；messages.question_vec 列保留 1 个月后清理。
_CREATE_QA_CACHE_TABLE = """
CREATE TABLE IF NOT EXISTS qa_cache (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    question     TEXT    NOT NULL,
    question_vec TEXT    NOT NULL,
    answer       TEXT    NOT NULL,
    kb_version   TEXT    NOT NULL,
    hit_count    INTEGER NOT NULL DEFAULT 1,
    last_hit_at  TIMESTAMP,
    created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

_CREATE_QA_CACHE_VERSION_IDX = """
CREATE INDEX IF NOT EXISTS idx_qa_cache_kb_version
ON qa_cache(kb_version);
"""

_CREATE_QA_CACHE_CREATED_AT_IDX = """
CREATE INDEX IF NOT EXISTS idx_qa_cache_created_at
ON qa_cache(created_at);
"""

_CREATE_QA_CACHE_LAST_HIT_IDX = """
CREATE INDEX IF NOT EXISTS idx_qa_cache_last_hit_at
ON qa_cache(last_hit_at);
"""


def get_db() -> sqlite3.Connection:
    """返回数据库连接，自动创建 ./data/ 目录。"""
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """建表，幂等执行（表已存在不报错）。"""
    conn = get_db()
    try:
        conn.execute(_CREATE_USERS_TABLE)
        conn.execute(_CREATE_AUDIT_LOGS_TABLE)
        conn.execute(_CREATE_CONVERSATIONS_TABLE)
        conn.execute(_CREATE_MESSAGES_TABLE)
        conn.execute(_CREATE_DOCUMENT_HISTORY_TABLE)
        conn.execute(_CREATE_DATA_INTERFACES_TABLE)
        conn.execute(_CREATE_USER_INTERFACE_ACCESS_TABLE)
        conn.execute(_CREATE_QA_CACHE_TABLE)
        conn.execute(_CREATE_QA_CACHE_VERSION_IDX)
        conn.execute(_CREATE_QA_CACHE_CREATED_AT_IDX)
        conn.execute(_CREATE_QA_CACHE_LAST_HIT_IDX)
        # 迁移：为已有 messages 表添加 question_vec 列（列已存在则跳过）
        try:
            conn.execute(_MIGRATE_MESSAGES_QUESTION_VEC)
        except Exception:
            pass  # 列已存在，忽略
        try:
            conn.execute(_MIGRATE_USERS_AVATAR)
        except Exception:
            pass  # 列已存在，忽略
        conn.commit()
    finally:
        conn.close()
