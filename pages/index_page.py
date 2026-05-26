# pages/index_page.py — 首页：侧边栏导航 + 三种智能体模式切换
import streamlit as st
from core.time_utils import calc_rel_time
from auth.session import get_current_user, require_login, require_role, logout_session
from auth.auth_service import update_password, update_display_name
from audit.audit_service import log_event
from data.conversation_service import (
    create_conversation,
    get_conversations,
    get_conversation,
    update_conversation_title,
    delete_conversation,
    get_messages,
)
from pages.chat_page import render_chat_main


def render():
    """渲染首页：左侧导航栏 + 右侧三种智能体模式切换。"""
    require_login()
    require_role(["user", "admin"])

    user = get_current_user()

    # ── 初始化 session_state ─────────────────────────────
    if "agent_mode" not in st.session_state:
        st.session_state.agent_mode = "knowledge_qa"  # knowledge_qa | data_stats | doc_write
    if "current_conversation_id" not in st.session_state:
        st.session_state.current_conversation_id = None
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "conversations" not in st.session_state:
        st.session_state.conversations = []
    if "show_settings" not in st.session_state:
        st.session_state.show_settings = False

    # 加载对话列表
    if not st.session_state.conversations or st.session_state.get("_reload_conversations", False):
        st.session_state.conversations = get_conversations(user["user_id"])
        st.session_state._reload_conversations = False

    # ── 侧边栏 ──────────────────────────────────────────
    _render_sidebar(user)

    # ── 如果显示设置界面，单独渲染 ──────────────────────
    if st.session_state.show_settings:
        _render_user_settings(user)
        return

    # ── 主区域：公共母版（标题 + 模式按钮）+ 各模式内容 ──
    _render_agent_selector()

    if st.session_state.agent_mode == "knowledge_qa":
        st.caption("当前智能体：知识库问答")
        render_chat_main(user)
    elif st.session_state.agent_mode == "data_stats":
        st.caption("当前智能体：数据统计")
        render_chat_main(user, use_direct_agent="data_agent")
    elif st.session_state.agent_mode == "doc_write":
        st.caption("当前智能体：文档撰写")
        _render_doc_write_mode()


# ── 侧边栏渲染 ──────────────────────────────────────────────────────────────

def _render_sidebar(user: dict) -> None:
    """渲染左侧导航栏。"""
    with st.sidebar:
        # 用户信息区域
        role_label = {"admin": "管理员", "user": "普通用户", "visitor": "访客"}
        st.markdown(f"**{user['display_name']}** ({role_label.get(user['role'], user['role'])})")
        st.divider()

        # 新建对话按钮
        if st.button("+ 新建对话", use_container_width=True, type="primary"):
            st.session_state.agent_mode = "knowledge_qa"
            new_conv_id = create_conversation(user["user_id"])
            st.session_state.current_conversation_id = new_conv_id
            st.session_state.messages = []
            st.session_state._reload_conversations = True
            st.rerun()

        # 历史对话窗口列表
        st.markdown("### 历史对话")
        if not st.session_state.conversations:
            st.caption("暂无对话记录")

        for conv in st.session_state.conversations:
            conv_id = conv["id"]
            title = conv["title"]
            updated_at = conv["updated_at"]

            # 计算相对时间
            rel_time = calc_rel_time(updated_at)

            col1, col2 = st.columns([4, 1])
            with col1:
                if st.button(
                    f"{title[:20]}{'...' if len(title) > 20 else ''}",
                    key=f"conv_{conv_id}",
                    use_container_width=True,
                    type="secondary" if st.session_state.current_conversation_id != conv_id else "primary",
                ):
                    st.session_state.agent_mode = "knowledge_qa"
                    st.session_state.current_conversation_id = conv_id
                    st.session_state.messages = get_messages(conv_id, user["user_id"])
                    st.rerun()
            with col2:
                if st.button("🗑️", key=f"del_{conv_id}", use_container_width=True):
                    delete_conversation(conv_id, user["user_id"])
                    if st.session_state.current_conversation_id == conv_id:
                        st.session_state.current_conversation_id = None
                        st.session_state.messages = []
                    st.session_state._reload_conversations = True
                    st.rerun()

            st.caption(rel_time)

        st.divider()

        # 后台管理（仅管理员可见）
        if user["role"] == "admin":
            if st.button("⚙️ 后台管理", use_container_width=True):
                st.session_state.current_page = "管理后台"
                st.rerun()

        # 账号管理
        if st.button("👤 账号管理", use_container_width=True):
            st.session_state.show_settings = not st.session_state.show_settings
            st.rerun()

        # 退出登录
        if st.button("退出登录", use_container_width=True):
            log_event(user["user_id"], user["username"], "logout")
            logout_session()
            st.rerun()


# ── 智能体选择器 ────────────────────────────────────────────────────────────

def _render_agent_selector() -> None:
    """渲染公共母版：标题 + 副标题 + 三种智能体模式切换按钮。"""
    st.title("企业知识库智能体")
    st.caption("支持文档问答 · 数据统计 · 文档编写 · 内容仿写")

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button(
            "📚 知识库问答",
            use_container_width=True,
            type="primary" if st.session_state.agent_mode == "knowledge_qa" else "secondary",
        ):
            if st.session_state.agent_mode != "knowledge_qa":
                st.session_state.agent_mode = "knowledge_qa"
                st.session_state.current_conversation_id = None
                st.session_state.messages = []
            st.rerun()
    with col2:
        if st.button(
            "📊 数据统计",
            use_container_width=True,
            type="primary" if st.session_state.agent_mode == "data_stats" else "secondary",
        ):
            if st.session_state.agent_mode != "data_stats":
                st.session_state.agent_mode = "data_stats"
                st.session_state.current_conversation_id = None
                st.session_state.messages = []
            st.rerun()
    with col3:
        if st.button(
            "📝 文档撰写",
            use_container_width=True,
            type="primary" if st.session_state.agent_mode == "doc_write" else "secondary",
        ):
            if st.session_state.agent_mode != "doc_write":
                st.session_state.agent_mode = "doc_write"
                st.session_state.current_conversation_id = None
                st.session_state.messages = []
            st.rerun()

    st.divider()


# ── 文档撰写模式 ────────────────────────────────────────────────────────────

def _render_doc_write_mode() -> None:
    """渲染文档撰写模式（使用 doc_page 的三步式流程，嵌入模式）。"""
    from pages.doc_page import render as render_doc

    # 嵌入模式下不显示 doc_page 自己的标题，由母版统一展示
    render_doc(embedded=True)


# ── 用户设置界面 ────────────────────────────────────────────────────────────

def _render_user_settings(user: dict) -> None:
    """
    渲染用户设置界面（账号管理）。
    包含：基本信息显示、修改显示名称、修改密码。
    """
    st.title("账号管理")
    st.divider()

    # ── 基本信息 ──────────────────────────────────────────
    st.subheader("基本信息")
    col1, col2 = st.columns(2)
    with col1:
        st.text_input("用户名", value=user["username"], disabled=True)
    with col2:
        role_label = {"admin": "管理员", "user": "普通用户", "visitor": "访客"}
        st.text_input("角色", value=role_label.get(user["role"], user["role"]), disabled=True)

    st.divider()

    # ── 修改显示名称 ──────────────────────────────────────
    st.subheader("修改显示名称")
    with st.form("update_display_name_form"):
        new_display_name = st.text_input(
            "新显示名称",
            value=user["display_name"],
            max_chars=50,
            help="显示名称将显示在侧边栏的用户信息区域",
        )
        submitted = st.form_submit_button("保存显示名称")

        if submitted:
            if new_display_name.strip() == user["display_name"]:
                st.info("显示名称未更改")
            else:
                success, msg = update_display_name(user["user_id"], new_display_name)
                if success:
                    st.success(msg)
                    st.session_state.current_user["display_name"] = new_display_name.strip()
                    log_event(user["user_id"], user["username"], "update_display_name")
                    st.rerun()
                else:
                    st.error(msg)

    st.divider()

    # ── 修改密码 ──────────────────────────────────────────
    st.subheader("修改密码")
    with st.form("update_password_form"):
        old_password = st.text_input("当前密码", type="password")
        new_password = st.text_input("新密码", type="password")
        confirm_password = st.text_input("确认新密码", type="password")
        submitted = st.form_submit_button("修改密码")

        if submitted:
            if not old_password:
                st.error("请输入当前密码")
            elif not new_password:
                st.error("请输入新密码")
            elif new_password != confirm_password:
                st.error("新密码与确认密码不一致")
            elif len(new_password) < 6:
                st.error("新密码长度至少 6 位")
            else:
                success, msg = update_password(user["user_id"], old_password, new_password)
                if success:
                    st.success(msg)
                    log_event(user["user_id"], user["username"], "update_password")
                else:
                    st.error(msg)

    st.divider()

    # ── 返回按钮 ──────────────────────────────────────────
    if st.button("← 返回首页", use_container_width=True):
        st.session_state.show_settings = False
        st.rerun()


# ── 辅助函数 ────────────────────────────────────────────────────────────────
# calc_rel_time 统一使用 UTC 时间对比，避免与本地时间（UTC+8）出现 8 小时偏差。
# 详见 core/time_utils.py。
