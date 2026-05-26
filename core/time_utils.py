"""
time_utils.py — 统一的时间/相对时间工具函数。

SQLite CURRENT_TIMESTAMP 默认返回 UTC 时间，本模块中所有"当前时间"
统一使用 UTC 进行对比，避免与本地时间（UTC+8）产生的 8 小时偏差。
"""
from datetime import datetime, timezone


def utc_now_naive() -> datetime:
    """返回朴素（无时区）的当前 UTC 时间，用于与数据库时间戳对比。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def calc_rel_time(updated_at: str | None) -> str:
    """根据数据库时间戳字符串计算相对时间（中文）。

    参数:
        updated_at: SQLite 时间戳字符串，格式为 "YYYY-MM-DD HH:MM:SS"（UTC）。
    返回:
        "刚刚" / "X分钟前" / "X小时前" / "昨天" / "X天前" / "YYYY-MM-DD"。
    """
    try:
        # 兼容 ISO 格式（带 Z 或 +00:00 后缀）和 SQLite 默认格式
        dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        # 将可能带时区的 datetime 转为朴素 UTC
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        now = utc_now_naive()
        delta = now - dt
        if delta.days == 0:
            if delta.seconds < 60:
                return "刚刚"
            elif delta.seconds < 3600:
                return f"{delta.seconds // 60}分钟前"
            else:
                return f"{delta.seconds // 3600}小时前"
        elif delta.days == 1:
            return "昨天"
        elif delta.days < 7:
            return f"{delta.days}天前"
        else:
            return updated_at[:10] if updated_at else ""
    except Exception:
        return updated_at[:10] if updated_at else ""
