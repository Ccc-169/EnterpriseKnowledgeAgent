# core/chat_registry.py — 对话取消注册中心
#
# 维护 user_id -> threading.Event 的映射，用于：
#   1. 单飞（single-flight）：同一用户发起新请求时，自动取消其旧请求；
#   2. 主动停止：/api/chat/stop 通过 user_id 取消当前任务；
#   3. 排队位次：waiting_count() 统计当前在排队/运行的任务数。
#
# threading.Event 而非 asyncio.Event：取消标志要在 to_thread 的工作线程
# （agent.stream 循环）里被检查，必须是线程安全的同步原语。

import threading

_lock: threading.Lock = threading.Lock()
_events: dict = {}   # user_id -> threading.Event


def register(user_id) -> threading.Event:
    """登记一个新任务的取消事件。

    若该用户已有在途任务，先 set 旧事件（单飞：挤掉旧请求），再写入新事件。
    返回新建的 Event，调用方持有它并在结束时传给 unregister。
    """
    new_event = threading.Event()
    with _lock:
        old = _events.get(user_id)
        if old is not None:
            old.set()          # 单飞：通知旧任务退出
        _events[user_id] = new_event
    return new_event


def unregister(user_id, event: threading.Event) -> None:
    """任务结束时清理。

    仅当当前存储的事件 is 本事件时才移除——若已被单飞替换为新任务的事件，
    则不动它，避免误删新任务的取消通道。
    """
    with _lock:
        if _events.get(user_id) is event:
            _events.pop(user_id, None)


def cancel(user_id) -> bool:
    """取消该用户当前在途任务（供 /api/chat/stop 调用）。

    返回是否存在可取消的任务。
    """
    with _lock:
        event = _events.get(user_id)
        if event is not None:
            event.set()
            return True
    return False


def waiting_count() -> int:
    """当前在排队/运行的任务总数（用于精确排队位次提示）。"""
    with _lock:
        return len(_events)
