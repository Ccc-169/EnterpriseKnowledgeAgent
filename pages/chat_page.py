# pages/chat_page.py — 主对话页（支持多对话记录）
import streamlit as st
from datetime import datetime
from agent import chat
from agents.registry import can_use_agent
from auth.session import get_current_user, require_login, require_role, logout_session
from auth.session import is_logged_in
from auth.auth_service import update_password, update_display_name
from audit.audit_service import log_event
from data.conversation_service import (
    create_conversation,
    get_conversations,
    get_conversation,
    update_conversation_title,
    delete_conversation,
    save_message,
    get_messages,
    update_conversation_timestamp,
    generate_title_from_message,
)


def render():
    """渲染主对话页面（带侧边栏对话列表）。"""
    require_login()
    require_role(["user", "admin"])

    user = get_current_user()

    # ── 初始化 session_state ─────────────────────────────
    if "current_conversation_id" not in st.session_state:
        st.session_state.current_conversation_id = None
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "conversations" not in st.session_state:
        st.session_state.conversations = []
    if "show_settings" not in st.session_state:
        st.session_state.show_settings = False

    # 加载用户的对话列表
    if not st.session_state.conversations or st.session_state.get("_reload_conversations", False):
        st.session_state.conversations = get_conversations(user["user_id"])
        st.session_state._reload_conversations = False

    # ── 侧边栏 ──────────────────────────────────────────
    with st.sidebar:
        # 用户信息区域
        role_label = {"admin": "管理员", "user": "普通用户", "visitor": "访客"}
        st.markdown(f"**{user['display_name']}** ({role_label.get(user['role'], user['role'])})")
        st.divider()

        # 新建对话按钮
        if st.button("+ 新建对话", use_container_width=True, type="primary"):
            new_conv_id = create_conversation(user["user_id"])
            st.session_state.current_conversation_id = new_conv_id
            st.session_state.messages = []
            st.session_state._reload_conversations = True
            st.rerun()

        # 对话列表
        st.markdown("### 对话记录")

        if not st.session_state.conversations:
            st.caption("暂无对话记录")

        for conv in st.session_state.conversations:
            conv_id = conv["id"]
            title = conv["title"]
            updated_at = conv["updated_at"]

            # 计算相对时间
            try:
                dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                now = datetime.now()
                delta = now - dt
                if delta.days == 0:
                    if delta.seconds < 60:
                        rel_time = "刚刚"
                    elif delta.seconds < 3600:
                        rel_time = f"{delta.seconds // 60}分钟前"
                    else:
                        rel_time = f"{delta.seconds // 3600}小时前"
                elif delta.days == 1:
                    rel_time = "昨天"
                elif delta.days < 7:
                    rel_time = f"{delta.days}天前"
                else:
                    rel_time = updated_at[:10]
            except Exception:
                rel_time = updated_at[:10] if updated_at else ""

            # 对话项
            col1, col2 = st.columns([4, 1])
            with col1:
                if st.button(
                    f"{title[:20]}{'...' if len(title) > 20 else ''}",
                    key=f"conv_{conv_id}",
                    use_container_width=True,
                    type="secondary" if st.session_state.current_conversation_id != conv_id else "primary"
                ):
                    # 切换到选中的对话
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

        # 管理后台入口（仅 admin 可见）
        if user["role"] == "admin":
            if st.button("⚙️ 管理后台", use_container_width=True):
                st.session_state.current_page = "管理后台"
                st.rerun()

        st.divider()

        # 用户设置入口
        if st.button("👤 用户设置", use_container_width=True):
            st.session_state.show_settings = not st.session_state.show_settings
            st.rerun()

        # 退出登录
        if st.button("退出登录", use_container_width=True):
            log_event(user["user_id"], user["username"], "logout")
            logout_session()
            st.rerun()

    # ── 主区域 ────────────────────────────────────────────
    # 如果显示设置界面，则渲染设置界面
    if st.session_state.show_settings:
        _render_user_settings(user)
        return

    st.title("企业知识库智能体")
    st.caption("支持文档问答 · 数据统计 · 内容仿写")

    # 如果没有选中任何对话，显示提示
    if not st.session_state.current_conversation_id:
        st.info("请在左侧侧边栏新建对话或选择已有对话")
        return

    # 显示当前对话标题
    current_conv = get_conversation(st.session_state.current_conversation_id, user["user_id"])
    if current_conv:
        st.subheader(current_conv["title"])

    # 渲染历史消息
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

            # 如果是助手消息且有推理过程，显示展开项
            if msg["role"] == "assistant" and msg.get("steps_log"):
                with st.expander("查看推理过程", expanded=False):
                    for step in msg["steps_log"]:
                        st.markdown(step)

    # 输入框
    if user_input := st.chat_input("请输入您的问题..."):
        # 检查用户是否有权使用 Agent
        user_context = {
            "user_id": user["user_id"],
            "username": user["username"],
            "role": user["role"],
        }

        # 添加用户消息到界面
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        # 保存到数据库（用户消息）
        save_message(
            conversation_id=st.session_state.current_conversation_id,
            role="user",
            content=user_input
        )

        # 如果是第一条消息，用用户问题生成对话标题
        if current_conv and current_conv["title"] == "新对话":
            new_title = generate_title_from_message(user_input)
            update_conversation_title(
                st.session_state.current_conversation_id,
                user["user_id"],
                new_title
            )
            st.session_state._reload_conversations = True

        with st.chat_message("assistant"):
            with st.spinner("思考中..."):
                response, steps, agent_used = "抱歉，处理您的问题时发生了错误，请稍后重试。", None, None
                try:
                    # 生成 thread_id（基于 conversation_id）
                    thread_id = f"conversation-{st.session_state.current_conversation_id}"

                    response, steps, agent_used = chat(
                        user_input,
                        thread_id,
                        user_context=user_context,
                    )

                    # 折叠显示思考过程
                    if steps:
                        with st.expander("查看推理过程", expanded=False):
                            for step in steps:
                                st.markdown(step)

                    # 无答案时显示橙色警告框（Phase 3 新增）
                    if "未能找到" in response:
                        st.warning(response)
                    else:
                        st.markdown(response)

                    # 审计日志：对话成功
                    log_event(
                        user_id=user["user_id"],
                        username=user["username"],
                        action="chat",
                        agent_used=agent_used,
                        question=user_input,
                        status="success",
                    )
                except Exception as err:
                    response = "抱歉，处理您的问题时发生了错误，请稍后重试。"
                    st.error(response)
                    st.exception(err)

                    # 审计日志：对话失败
                    log_event(
                        user_id=user["user_id"],
                        username=user["username"],
                        action="chat",
                        question=user_input,
                        status="error",
                    )

                # 保存到数据库（助手回复）
                save_message(
                    conversation_id=st.session_state.current_conversation_id,
                    role="assistant",
                    content=response,
                    steps_log=steps if steps else None,
                    agent_used=agent_used
                )

                # 更新对话时间戳
                update_conversation_timestamp(st.session_state.current_conversation_id)

        # 添加助手回复到 session_state
        st.session_state.messages.append({
            "role": "assistant",
            "content": response,
            "steps_log": steps if steps else None,
            "agent_used": agent_used
        })

        # 重新加载对话列表（标题可能已更新）
        st.session_state._reload_conversations = True
        st.rerun()


def _render_user_settings(user: dict) -> None:
    """
    渲染用户设置界面。
    包含：基本信息显示、修改显示名称、修改密码。
    """
    st.title("用户设置")
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
                    # 更新 session 中的用户信息
                    st.session_state.current_user["display_name"] = new_display_name.strip()
                    # 记录审计日志
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
            # 验证输入
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
                    # 记录审计日志
                    log_event(user["user_id"], user["username"], "update_password")
                else:
                    st.error(msg)

    st.divider()

    # ── 返回按钮 ──────────────────────────────────────────
    if st.button("← 返回对话", use_container_width=True):
        st.session_state.show_settings = False
        st.rerun()
