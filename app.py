import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# 确保数据库表结构最新（幂等，已存在不重复创建）
from core.database import init_db
# init_db()

from auth.session import is_logged_in, get_current_user, login_session, logout_session
from auth.auth_service import authenticate_user
from audit.audit_service import log_event

st.set_page_config(page_title="企业知识库智能体", layout="wide")

# ── 未登录：显示登录表单 ──────────────────────────────────
if not is_logged_in():
    st.title("企业知识库智能体")
    st.caption("请登录后使用")

    with st.form("login_form"):
        username = st.text_input("用户名")
        password = st.text_input("密码", type="password")
        submitted = st.form_submit_button("登录")

        if submitted:
            user = authenticate_user(username, password)
            if user is None:
                st.error("用户名或密码错误")
            else:
                login_session(user)
                log_event(user["user_id"], user["username"], "login")
                st.rerun()

    st.stop()

# ── 已登录：根据角色分发页面 ──────────────────────────────
user = get_current_user()

# visitor 角色只显示无权限提示
if user["role"] == "visitor":
    st.title("企业知识库智能体")
    st.warning("您的账号暂无使用权限。如需开通，请联系管理员。")
    with st.sidebar:
        st.markdown(f"**{user['display_name']}** (访客)")
        if st.button("退出登录", use_container_width=True):
            log_event(user["user_id"], user["username"], "logout")
            logout_session()
            st.rerun()
    st.stop()

# ── 页面路由 ──────────────────────────────────────────────
# 管理页面状态
if "current_page" not in st.session_state:
    st.session_state.current_page = "对话"

if st.session_state.current_page == "对话":
    from pages.chat_page import render as render_chat
    render_chat()
elif st.session_state.current_page == "管理后台":
    from pages.admin_page import render as render_admin
    render_admin()
elif st.session_state.current_page == "文档编写":
    from pages.doc_page import render as render_doc
    render_doc()
