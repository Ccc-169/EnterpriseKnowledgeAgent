# pages/admin_page.py — 管理员页面
import os

import streamlit as st
from auth.session import get_current_user, require_role
from auth.auth_service import create_user, list_users, update_user_role, toggle_user_active
from audit.audit_service import get_logs, get_summary_stats, log_event
from data.dify_service import list_datasets, list_documents


def render():
    """渲染管理员页面。"""
    require_role(["admin"])

    user = get_current_user()

    st.title("管理后台")

    tab_users, tab_logs, tab_kb = st.tabs(["用户管理", "审计日志", "知识库管理"])

    # ── Tab 1: 用户管理 ──────────────────────────────────
    with tab_users:
        _render_user_management(user)

    # ── Tab 2: 审计日志 ──────────────────────────────────
    with tab_logs:
        _render_audit_logs()

    # ── Tab 3: 知识库管理 ──────────────────────────────────
    with tab_kb:
        _render_knowledge_base()


def _render_user_management(current_user: dict):
    """渲染用户管理 Tab。"""
    # 统计摘要
    stats = get_summary_stats()
    col1, col2, col3 = st.columns(3)
    col1.metric("用户总数", stats["total_users"])
    col2.metric("今日活跃用户", stats["active_users_today"])
    col3.metric("今日对话数", stats["total_chats_today"])

    st.divider()

    # 新建用户表单
    with st.expander("新建用户", expanded=False):
        with st.form("create_user_form"):
            new_username = st.text_input("用户名 *", key="new_username")
            new_password = st.text_input("密码 *", type="password", key="new_password")
            new_display_name = st.text_input("显示名", key="new_display_name")
            new_role = st.selectbox("角色", ["visitor", "user", "admin"], key="new_role")
            submitted = st.form_submit_button("创建用户")

            if submitted:
                if not new_username or not new_password:
                    st.error("用户名和密码为必填项")
                elif create_user(new_username, new_password, new_display_name, new_role):
                    st.success(f"用户 '{new_username}' 创建成功")
                    log_event(
                        current_user["user_id"], current_user["username"],
                        "admin_op", status="success",
                    )
                    st.rerun()
                else:
                    st.error(f"用户名 '{new_username}' 已存在，请更换")

    st.divider()

    # 用户列表
    users = list_users()
    st.subheader("用户列表")

    for u in users:
        with st.container():
            col_info, col_role, col_status, col_action = st.columns([3, 2, 1.5, 2])

            with col_info:
                status_icon = " " if u["is_active"] else " [已禁用]"
                st.markdown(
                    f"**ID:{u['id']}** | {u['username']} | "
                    f"{u['display_name'] or '-'} | 角色: {u['role']}{status_icon}"
                )
                st.caption(f"创建时间: {u['created_at']}")

            with col_role:
                new_role = st.selectbox(
                    "角色",
                    ["visitor", "user", "admin"],
                    index=["visitor", "user", "admin"].index(u["role"]),
                    key=f"role_{u['id']}",
                    label_visibility="collapsed",
                )
                if st.button("修改角色", key=f"btn_role_{u['id']}"):
                    if new_role != u["role"]:
                        update_user_role(u["id"], new_role)
                        log_event(
                            current_user["user_id"], current_user["username"],
                            "admin_op", status="success",
                        )
                        st.rerun()

            with col_status:
                if u["id"] == current_user["user_id"]:
                    st.caption("(当前用户)")
                else:
                    toggle_label = "禁用" if u["is_active"] else "启用"
                    if st.button(toggle_label, key=f"btn_toggle_{u['id']}"):
                        toggle_user_active(u["id"], not u["is_active"])
                        log_event(
                            current_user["user_id"], current_user["username"],
                            "admin_op", status="success",
                        )
                        st.rerun()

            with col_action:
                pass  # 预留扩展

            st.divider()


def _render_audit_logs():
    """渲染审计日志 Tab。"""
    st.subheader("审计日志")

    # 筛选条件（横排）
    col1, col2, col3, col4, col5 = st.columns([2, 2, 1.5, 1.5, 1])
    with col1:
        filter_username = st.text_input("用户名", key="log_filter_username")
    with col2:
        filter_action = st.selectbox(
            "操作类型",
            ["全部", "login", "logout", "chat", "admin_op", "denied"],
            key="log_filter_action",
        )
    with col3:
        filter_date_from = st.text_input("开始日期", placeholder="YYYY-MM-DD", key="log_filter_from")
    with col4:
        filter_date_to = st.text_input("结束日期", placeholder="YYYY-MM-DD", key="log_filter_to")
    with col5:
        st.write("")  # 对齐
        st.write("")
        query_clicked = st.button("查询")

    # 查询日志
    action_param = None if filter_action == "全部" else filter_action
    logs = get_logs(
        limit=200,
        username=filter_username or None,
        action=action_param,
        date_from=filter_date_from or None,
        date_to=filter_date_to or None,
    )

    # 日志表格
    if logs:
        for log in logs:
            question_preview = (log["question"] or "")[:50]
            st.markdown(
                f"| {log['created_at']} | **{log['username']}** | "
                f"{log['action']} | {log['agent_used'] or '-'} | "
                f"{question_preview} | {log['status']} |"
            )
        st.caption(f"共 {len(logs)} 条记录")
    else:
        st.info("暂无日志记录")


def _render_knowledge_base():
    """渲染知识库管理 Tab。"""
    st.subheader("知识库管理")
    st.caption("当前为只读模式，展示 Dify 知识库及文档信息。")

    # 检查 API Key 是否配置
    if not os.environ.get("DIFY_DATASET_KEY"):
        st.warning("未配置 DIFY_DATASET_KEY，请在 .env 文件中配置后重启应用。")
        return

    # 初始化分页状态
    if "kb_page" not in st.session_state:
        st.session_state.kb_page = 1

    # 获取知识库列表
    try:
        with st.spinner("正在获取知识库列表..."):
            kb_data = list_datasets(page=st.session_state.kb_page, limit=20)
    except RuntimeError as e:
        st.error(str(e))
        return

    datasets = kb_data.get("data", [])
    has_more = kb_data.get("has_more", False)
    total = kb_data.get("total", 0)

    if not datasets:
        st.info("暂无知识库。")
        return

    st.caption(f"共 {total} 个知识库，当前第 {st.session_state.kb_page} 页")

    # 显示每个知识库
    for ds in datasets:
        doc_count = ds.get("document_count", ds.get("total_documents", 0))
        with st.expander(f"📚 {ds['name']}  ({doc_count} 个文档)"):
            # 知识库详情
            col1, col2, col3 = st.columns(3)
            col1.metric("文档数量", doc_count)
            col2.metric("总字数", ds.get("word_count", 0))
            col3.metric("嵌入模型", ds.get("embedding_model", "-"))

            if ds.get("description"):
                st.caption(f"描述：{ds['description']}")

            # 获取文档列表
            dataset_id = ds["id"]
            doc_page_key = f"doc_page_{dataset_id}"
            if doc_page_key not in st.session_state:
                st.session_state[doc_page_key] = 1

            try:
                with st.spinner("正在获取文档列表..."):
                    doc_data = list_documents(
                        dataset_id=dataset_id,
                        page=st.session_state[doc_page_key],
                        limit=20,
                    )
            except RuntimeError as e:
                st.error(str(e))
                continue

            docs = doc_data.get("data", [])
            doc_has_more = doc_data.get("has_more", False)
            doc_total = doc_data.get("total", 0)

            if not docs:
                st.info("该知识库暂无文档。")
            else:
                st.caption(f"共 {doc_total} 个文档，当前第 {st.session_state[doc_page_key]} 页")

                # 文档表格
                doc_rows = []
                for doc in docs:
                    status_icon = "✓" if doc.get("indexing_status") == "completed" else "⏳"
                    display_status = doc.get("display_status", doc.get("indexing_status", ""))
                    doc_rows.append({
                        "状态": status_icon,
                        "文档名": doc["name"],
                        "索引状态": display_status,
                        "字数": doc.get("word_count", 0),
                        "命中次数": doc.get("hit_count", 0),
                    })
                st.dataframe(doc_rows, use_container_width=True)

                # 文档分页控件
                col_prev, col_page, col_next = st.columns([1, 2, 1])
                with col_prev:
                    if st.session_state[doc_page_key] > 1:
                        if st.button("上一页", key=f"prev_doc_{dataset_id}"):
                            st.session_state[doc_page_key] -= 1
                            st.rerun()
                with col_page:
                    st.text(f"第 {st.session_state[doc_page_key]} 页")
                with col_next:
                    if doc_has_more:
                        if st.button("下一页", key=f"next_doc_{dataset_id}"):
                            st.session_state[doc_page_key] += 1
                            st.rerun()

    # 知识库分页控件
    st.divider()
    col_prev, col_page, col_next = st.columns([1, 2, 1])
    with col_prev:
        if st.session_state.kb_page > 1:
            if st.button("上一页", key="prev_kb"):
                st.session_state.kb_page -= 1
                st.rerun()
    with col_page:
        st.text(f"第 {st.session_state.kb_page} 页")
    with col_next:
        if has_more:
            if st.button("下一页", key="next_kb"):
                st.session_state.kb_page += 1
                st.rerun()

