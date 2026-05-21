# auth/session.py — Streamlit session 状态管理
import streamlit as st

_SESSION_KEY = "current_user"


def is_logged_in() -> bool:
    """检查当前 session 是否已登录。"""
    return _SESSION_KEY in st.session_state and st.session_state[_SESSION_KEY] is not None


def get_current_user() -> dict | None:
    """返回当前用户信息 {user_id, username, role, display_name}。"""
    return st.session_state.get(_SESSION_KEY)


def login_session(user: dict) -> None:
    """将用户信息写入 session_state。"""
    st.session_state[_SESSION_KEY] = user


def logout_session() -> None:
    """清空 session_state 中的用户信息。"""
    if _SESSION_KEY in st.session_state:
        del st.session_state[_SESSION_KEY]


def require_login() -> None:
    """未登录则显示提示并 st.stop()。"""
    if not is_logged_in():
        st.warning("请先登录后再使用此功能。")
        st.stop()


def require_role(allowed_roles: list[str]) -> None:
    """角色不在 allowed_roles 中则显示无权限提示并 st.stop()。"""
    user = get_current_user()
    if user is None or user["role"] not in allowed_roles:
        st.error("您没有权限访问此页面。如需开通权限，请联系管理员。")
        st.stop()
