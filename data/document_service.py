"""
document_service.py — 文档编写历史记录的 CRUD 操作
参照 conversation_service.py 的设计模式。
"""
import re
from core.database import get_db


def save_document(
    user_id: int,
    title: str = "新建文档",
    requirements: str = "",
    outline: str = "",
    content: str = "",
    reference_context: str = "",
) -> int:
    """保存文档编写记录（新建或更新最近一次记录），返回 document_id。

    策略：如果用户最近 5 分钟内有一份内容相同的记录，则更新它（避免重复）；
    否则新建一条记录。"""
    conn = get_db()
    try:
        # 查最近一条同用户、内容相同的记录（5 分钟内）
        # 如存在则更新，否则插入新记录
        recent = conn.execute(
            """SELECT id FROM document_history
               WHERE user_id = ?
                 AND content = ?
                 AND (strftime('%s', 'now') - strftime('%s', updated_at)) < 300
               ORDER BY updated_at DESC LIMIT 1""",
            (user_id, content),
        ).fetchone()

        if recent:
            doc_id = recent["id"]
            conn.execute(
                """UPDATE document_history
                   SET title = ?, requirements = ?, outline = ?, content = ?,
                       reference_context = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (title, requirements, outline, content, reference_context, doc_id),
            )
        else:
            cursor = conn.execute(
                """INSERT INTO document_history
                   (user_id, title, requirements, outline, content, reference_context)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (user_id, title, requirements, outline, content, reference_context),
            )
            doc_id = cursor.lastrowid

        conn.commit()
        return doc_id
    finally:
        conn.close()


def get_documents(user_id: int, limit: int = 50, offset: int = 0) -> list:
    """获取用户的文档历史列表（按 updated_at 降序）。"""
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT id, title, created_at, updated_at,
               substr(requirements, 1, 100) as requirements_preview
               FROM document_history
               WHERE user_id = ?
               ORDER BY updated_at DESC
               LIMIT ? OFFSET ?""",
            (user_id, limit, offset),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_document(doc_id: int, user_id: int) -> dict | None:
    """获取单份文档的全部内容（含权限校验）。"""
    conn = get_db()
    try:
        row = conn.execute(
            """SELECT id, title, requirements, outline, content, reference_context,
                      created_at, updated_at
               FROM document_history
               WHERE id = ? AND user_id = ?""",
            (doc_id, user_id),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def delete_document(doc_id: int, user_id: int) -> bool:
    """删除文档记录，返回是否成功。"""
    conn = get_db()
    try:
        cursor = conn.execute(
            "DELETE FROM document_history WHERE id = ? AND user_id = ?",
            (doc_id, user_id),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def generate_title_from_requirements(requirements: str, max_length: int = 20) -> str:
    """从需求描述或目录中提取文档标题。

    优先从目录第一行提取 '# 文档标题：xxx' 格式，
    否则截取需求描述前 N 个字符。"""
    if not requirements:
        return "新建文档"
    # 尝试从 Markdown 一级标题提取
    m = re.match(r"^#\s*(?:文档标题[：:]\s*)?(.+)$", requirements.strip(), re.MULTILINE)
    if m:
        title = m.group(1).strip()
    else:
        title = requirements.strip()
    if len(title) > max_length:
        title = title[:max_length] + "..."
    return title
