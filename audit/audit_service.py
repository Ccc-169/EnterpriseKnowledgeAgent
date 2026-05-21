# audit/audit_service.py — 写日志、查日志
from core.database import get_db

MAX_QUESTION_LENGTH = 200


def log_event(
    user_id: int,
    username: str,
    action: str,
    agent_used: str = None,
    question: str = None,
    status: str = "success",
) -> None:
    """
    写一条审计日志。
    question 自动截断至200字。
    """
    if question and len(question) > MAX_QUESTION_LENGTH:
        question = question[:MAX_QUESTION_LENGTH]

    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO audit_logs (user_id, username, action, agent_used, question, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, username, action, agent_used, question, status),
        )
        conn.commit()
    finally:
        conn.close()


def get_logs(
    limit: int = 100,
    offset: int = 0,
    username: str = None,
    action: str = None,
    date_from: str = None,
    date_to: str = None,
) -> list[dict]:
    """
    查询日志列表，仅供管理员页面调用。
    支持按用户名、操作类型、日期范围过滤。
    """
    conditions = []
    params = []

    if username:
        conditions.append("username = ?")
        params.append(username)
    if action:
        conditions.append("action = ?")
        params.append(action)
    if date_from:
        conditions.append("DATE(created_at) >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("DATE(created_at) <= ?")
        params.append(date_to)

    where_clause = (" WHERE " + " AND ".join(conditions)) if conditions else ""

    conn = get_db()
    try:
        rows = conn.execute(
            f"SELECT * FROM audit_logs{where_clause} "
            "ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


def get_summary_stats() -> dict:
    """
    返回统计摘要供管理员页面展示：
    {total_users, active_users_today, total_chats_today, total_chats_all}
    """
    conn = get_db()
    try:
        total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        active_users_today = conn.execute(
            "SELECT COUNT(DISTINCT user_id) FROM audit_logs "
            "WHERE DATE(created_at) = DATE('now') AND action = 'chat'"
        ).fetchone()[0]
        total_chats_today = conn.execute(
            "SELECT COUNT(*) FROM audit_logs "
            "WHERE DATE(created_at) = DATE('now') AND action = 'chat'"
        ).fetchone()[0]
        total_chats_all = conn.execute(
            "SELECT COUNT(*) FROM audit_logs WHERE action = 'chat'"
        ).fetchone()[0]
    finally:
        conn.close()

    return {
        "total_users": total_users,
        "active_users_today": active_users_today,
        "total_chats_today": total_chats_today,
        "total_chats_all": total_chats_all,
    }
