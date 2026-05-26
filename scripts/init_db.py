# scripts/init_db.py — 初始化数据库并写入默认用户
# 用法：python scripts/init_db.py
import sys
import os

# 将项目根目录加入 sys.path，确保能导入 core 模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.database import get_db, init_db
from passlib.hash import bcrypt

DEFAULT_USERS = [
    {
        "username": "admin",
        "password": "Admin@123",
        "display_name": "管理员",
        "role": "admin",
    },
    {
        "username": "user01",
        "password": "User@123",
        "display_name": "普通用户",
        "role": "user",
    },
    {
        "username": "chen",
        "password": "chen@123",
        "display_name": "管理员",
        "role": "admin",
    },
]


def seed_default_users() -> None:
    """插入默认用户，幂等执行（已存在则跳过）。"""
    conn = get_db()
    try:
        for user in DEFAULT_USERS:
            # 检查用户是否已存在
            existing = conn.execute(
                "SELECT id FROM users WHERE username = ?",
                (user["username"],),
            ).fetchone()
            if existing:
                print(f"  [SKIP] 用户 '{user['username']}' 已存在，跳过")
                continue

            password_hash = bcrypt.hash(user["password"])
            conn.execute(
                "INSERT INTO users (username, password_hash, display_name, role) "
                "VALUES (?, ?, ?, ?)",
                (user["username"], password_hash, user["display_name"], user["role"]),
            )
            print(f"  [OK] 创建用户 '{user['username']}'（角色：{user['role']}）")

        conn.commit()
    finally:
        conn.close()


def main() -> None:
    print("=" * 50)
    print("  HNGD 数据库初始化")
    print("=" * 50)

    # 建表
    print("\n[INFO] 初始化数据库表...")
    init_db()
    print("  [OK] 数据库表创建完成")

    # 写入默认用户
    print("\n[INFO] 创建默认用户...")
    seed_default_users()

    # 验证
    print("\n[INFO] 验证结果：")
    conn = get_db()
    try:
        users = conn.execute("SELECT id, username, role, is_active FROM users").fetchall()
        for u in users:
            print(f"  - ID:{u['id']} | {u['username']} | 角色:{u['role']} | 状态:{'启用' if u['is_active'] else '禁用'}")
    finally:
        conn.close()

    print(f"\n{'=' * 50}")
    print("  [WARNING] 上线前请务必修改默认密码！")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
