# core/cancel.py — 对话取消基础设施
#
# 为各 agent 提供"真中断"能力：
#   1. 把 api.py 中的 threading.Event 通过线程局部存储注入到 agent 内部；
#   2. 在每次 LLM token 生成、检查点切换、长操作前调用 check_or_raise()，
#      一旦用户停止即抛出 UserCancelledError，协作式退出当前节点；
#   3. 在 api.py / agent.py 中 try/finally 注入/清理，避免线程池复用导致串台。
#
# 之所以用 threading.local：
#   - api.py 在 asyncio 主线程持有 cancel_event；
#   - 真正的 LangGraph 调用在 asyncio.to_thread 创建的工作线程中跑；
#   - threading.Event 是线程安全对象，可以跨线程 set()/is_set()；
#   - 但工作线程需要"知道"当前 cancel_event 是哪个（避免新任务顶掉旧任务后串台），
#     所以把它挂到线程局部存储里，仅当前在途任务可见。

import threading


class UserCancelledError(Exception):
    """用户主动取消生成时抛出的协作式异常。

    各 agent 节点在 LLM 流式生成、检查点切换、长操作前后调用
    check_or_raise()，发现 cancel_event 已 set 时抛此异常。

    api.py 应单独捕获此异常（区别于普通 Exception），向前端推送 done 事件
    而不是 error 事件，保持前端"正常停止"的体验。
    """
    pass


# 线程局部存储：当前线程在途任务的取消事件。
# 仅在工作线程（agent.stream 所在线程）内有意义。
_state = threading.local()


def set_cancel_event(event: threading.Event) -> None:
    """注入当前线程的取消事件。在 agent.stream 前调用。"""
    _state.event = event


def get_cancel_event() -> "threading.Event | None":
    """读取当前线程的取消事件。如果未注入，返回 None。"""
    return getattr(_state, "event", None)


def clear_cancel_event() -> None:
    """清理当前线程的取消事件。在 finally 中调用，防线程池复用串台。"""
    if hasattr(_state, "event"):
        delattr(_state, "event")


def check_or_raise() -> None:
    """在 token 边界或长操作前后调用。

    如果当前线程注入了 cancel_event 且已被 set，立即抛出
    UserCancelledError，由 api.py 单独捕获并正常结束 SSE 流。
    """
    event = get_cancel_event()
    if event is not None and event.is_set():
        raise UserCancelledError("用户主动取消生成")


def is_cancelled() -> bool:
    """非异常退出场景使用的检查函数（例如要跳过某步骤而非整体中断时）。

    仅返回布尔，不抛异常。
    """
    event = get_cancel_event()
    return event is not None and event.is_set()