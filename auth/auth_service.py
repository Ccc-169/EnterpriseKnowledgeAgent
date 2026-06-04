# auth/auth_service.py — 登录验证、密码哈希
from passlib.hash import bcrypt
from core.database import get_db


def hash_password(password: str) -> str:
    """bcrypt 哈希密码。"""
    return bcrypt.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """验证密码是否匹配。"""
    return bcrypt.verify(plain, hashed)


def authenticate_user(username: str, password: str) -> dict | None:
    """
    查数据库验证用户名密码。
    成功返回 {user_id, username, role, display_name}。
    失败返回 None（不区分用户名错误还是密码错误）。
    同时检查 is_active，禁用账号返回 None。
    """
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, username, password_hash, display_name, role, is_active, avatar "
            "FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    finally:
        conn.close()

    # 用户不存在 / 账号禁用 / 密码错误 → 统一返回 None
    if row is None:
        return None
    if not row["is_active"]:
        return None
    if not verify_password(password, row["password_hash"]):
        return None

    return {
        "user_id":      row["id"],
        "username":     row["username"],
        "role":         row["role"],
        "display_name": row["display_name"],
        "avatar":       row["avatar"],
    }


# ── 用户管理（供管理员页面调用）─────────────────────────

def create_user(username: str, password: str, display_name: str, role: str) -> bool:
    """
    创建新用户。
    成功返回 True，用户名已存在返回 False。
    """
    password_hash = hash_password(password)
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash, display_name, role) "
            "VALUES (?, ?, ?, ?)",
            (username, password_hash, display_name, role),
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()


def list_users() -> list[dict]:
    """返回全部用户列表。"""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id, username, display_name, role, is_active, created_at "
            "FROM users ORDER BY id"
        ).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


def update_user_role(user_id: int, new_role: str) -> bool:
    """修改用户角色。成功返回 True。"""
    conn = get_db()
    try:
        conn.execute(
            "UPDATE users SET role = ? WHERE id = ?",
            (new_role, user_id),
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()


def toggle_user_active(user_id: int, is_active: bool) -> bool:
    """启用/禁用用户。成功返回 True。"""
    conn = get_db()
    try:
        conn.execute(
            "UPDATE users SET is_active = ? WHERE id = ?",
            (1 if is_active else 0, user_id),
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()


# ── 用户自助设置（供用户设置页面调用）─────────────────────────

def update_password(user_id: int, old_password: str, new_password: str) -> tuple[bool, str]:
    """
    修改用户密码。
    成功返回 (True, "密码修改成功")，失败返回 (False, 错误信息)。
    """
    conn = get_db()
    try:
        # 验证旧密码
        row = conn.execute(
            "SELECT password_hash FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()

        if row is None:
            return False, "用户不存在"

        if not verify_password(old_password, row["password_hash"]):
            return False, "当前密码错误"

        # 更新密码
        new_password_hash = hash_password(new_password)
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (new_password_hash, user_id),
        )
        conn.commit()
        return True, "密码修改成功"
    except Exception as e:
        conn.rollback()
        return False, f"修改失败: {str(e)}"
    finally:
        conn.close()


def update_avatar(user_id: int, avatar_data: str) -> tuple[bool, str]:
    """更新用户头像（base64 编码的图片数据或 SVG data URL）。"""
    if not avatar_data:
        return False, "头像数据不能为空"
    if len(avatar_data) > 400_000:
        return False, "头像图片过大，请选择较小的图片"
    conn = get_db()
    try:
        conn.execute("UPDATE users SET avatar = ? WHERE id = ?", (avatar_data, user_id))
        conn.commit()
        return True, "头像更新成功"
    except Exception as e:
        conn.rollback()
        return False, f"更新失败: {str(e)}"
    finally:
        conn.close()


def update_display_name(user_id: int, new_display_name: str) -> tuple[bool, str]:
    """
    修改用户显示名称。
    成功返回 (True, "显示名称修改成功")，失败返回 (False, 错误信息)。
    """
    if not new_display_name or not new_display_name.strip():
        return False, "显示名称不能为空"

    conn = get_db()
    try:
        conn.execute(
            "UPDATE users SET display_name = ? WHERE id = ?",
            (new_display_name.strip(), user_id),
        )
        conn.commit()
        return True, "显示名称修改成功"
    except Exception as e:
        conn.rollback()
        return False, f"修改失败: {str(e)}"
    finally:
        conn.close()
