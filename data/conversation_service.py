"""
conversation_service.py — 对话记录和消息的 CRUD 操作
"""
import json
from datetime import datetime
from core.database import get_db


def create_conversation(user_id: int, title: str = "新对话") -> int:
    """创建新对话，返回 conversation_id"""
    conn = get_db()
    try:
        cursor = conn.execute(
            "INSERT INTO conversations (user_id, title) VALUES (?, ?)",
            (user_id, title)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_conversations(user_id: int, limit: int = 50, offset: int = 0) -> list:
    """获取用户的对话列表（按 updated_at 降序）"""
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT id, title, created_at, updated_at
               FROM conversations
               WHERE user_id = ?
               ORDER BY updated_at DESC
               LIMIT ? OFFSET ?""",
            (user_id, limit, offset)
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_conversation(conversation_id: int, user_id: int) -> dict | None:
    """获取单个对话信息（验证权限）"""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, title, created_at, updated_at FROM conversations WHERE id = ? AND user_id = ?",
            (conversation_id, user_id)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_conversation_title(conversation_id: int, user_id: int, title: str) -> bool:
    """修改对话标题，返回是否成功"""
    conn = get_db()
    try:
        cursor = conn.execute(
            "UPDATE conversations SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?",
            (title, conversation_id, user_id)
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def delete_conversation(conversation_id: int, user_id: int) -> bool:
    """删除对话（级联删除消息）"""
    conn = get_db()
    try:
        cursor = conn.execute(
            "DELETE FROM conversations WHERE id = ? AND user_id = ?",
            (conversation_id, user_id)
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def save_message(conversation_id: int, role: str, content: str,
                 steps_log: list = None, agent_used: str = None) -> int:
    """保存单条消息，返回 message_id"""
    conn = get_db()
    try:
        steps_json = json.dumps(steps_log, ensure_ascii=False) if steps_log else None
        cursor = conn.execute(
            """INSERT INTO messages (conversation_id, role, content, steps_log, agent_used)
               VALUES (?, ?, ?, ?, ?)""",
            (conversation_id, role, content, steps_json, agent_used)
        )
        # 更新对话的 updated_at
        conn.execute(
            "UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (conversation_id,)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_messages(conversation_id: int, user_id: int) -> list:
    """获取对话的所有消息（按 created_at 升序）"""
    conn = get_db()
    try:
        # 先验证对话属于该用户
        conv = conn.execute(
            "SELECT id FROM conversations WHERE id = ? AND user_id = ?",
            (conversation_id, user_id)
        ).fetchone()
        if not conv:
            return []

        rows = conn.execute(
            """SELECT id, role, content, steps_log, agent_used, created_at
               FROM messages
               WHERE conversation_id = ?
               ORDER BY created_at ASC""",
            (conversation_id,)
        ).fetchall()

        messages = []
        for row in rows:
            msg = dict(row)
            if msg["steps_log"]:
                msg["steps_log"] = json.loads(msg["steps_log"])
            messages.append(msg)
        return messages
    finally:
        conn.close()


def update_conversation_timestamp(conversation_id: int) -> None:
    """更新对话的 updated_at 时间戳"""
    conn = get_db()
    try:
        conn.execute(
            "UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (conversation_id,)
        )
        conn.commit()
    finally:
        conn.close()


def generate_title_from_message(message: str, max_length: int = 20) -> str:
    """从第一条消息生成对话标题（截取前 N 个字符）"""
    if not message:
        return "新对话"
    title = message.strip()
    if len(title) > max_length:
        title = title[:max_length] + "..."
    return title
