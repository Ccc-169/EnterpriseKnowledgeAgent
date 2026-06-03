# pages/doc_page.py — 文档编写专用页（两步交互：目录生成→用户确认→内容生成）
from datetime import datetime
import streamlit as st
from auth.session import get_current_user, require_login, require_role
from audit.audit_service import log_event
from data.file_parser import extract_file_content
from data.document_service import (
    save_document,
    generate_title_from_requirements,
)
from data.conversation_service import (
    create_conversation,
    save_message as save_conv_message,
)
from agent import chat_direct


# ── 自动保存辅助函数 ─────────────────────────────────────────────────────────

def _auto_save_document(user: dict, outline: str) -> int | None:
    """文档生成完成后自动保存到数据库，并同步创建侧边栏对话记录。
    返回 document_id，失败返回 None。"""
    try:
        doc_title = generate_title_from_requirements(
            outline or st.session_state.get("doc_requirements", "")
        )
        doc_id = save_document(
            user_id=user["user_id"],
            title=doc_title,
            requirements=st.session_state.doc_requirements,
            outline=st.session_state.doc_outline,
            content=st.session_state.doc_content,
            reference_context=st.session_state.get("doc_reference_context", ""),
        )

        # 同步创建对话记录（展示在侧边栏历史对话中）
        try:
            conv_id = create_conversation(user["user_id"], title=doc_title)
            save_conv_message(
                conversation_id=conv_id,
                role="user",
                content=f"📝 文档撰写需求：\n{st.session_state.doc_requirements}",
            )
            save_conv_message(
                conversation_id=conv_id,
                role="assistant",
                content=st.session_state.doc_content,
            )
            st.session_state._reload_conversations = True
        except Exception:
            pass  # 对话创建失败不影响文档保存

        return doc_id
    except Exception:
        return None




# ── 页面渲染 ──────────────────────────────────────────────────────────────

# ── 文档状态重置（供外部页面调用，确保切换到文档编写时是新文档）──

def reset_doc_state():
    """清空文档编写相关 session_state，回到新建文档状态。"""
    import streamlit as st
    st.session_state.doc_step = "input"
    st.session_state.doc_requirements = ""
    st.session_state.doc_outline = ""
    st.session_state.doc_content = ""
    st.session_state.doc_reference_context = ""
    st.session_state.doc_current_id = None
    st.session_state.doc_expanded_id = None
    st.session_state.doc_uploader_key = st.session_state.get("doc_uploader_key", 0) + 1


def render(embedded: bool = False):
    """渲染文档编写页面，实现两步交互流程。

    Args:
        embedded: True 表示嵌入在首页中使用（跳过标题/副标题，由母版统一显示）。
    """
    require_login()
    require_role(["user", "admin"])

    user = get_current_user()

    # ── 初始化 session_state ─────────────────────────────
    if "doc_step" not in st.session_state:
        st.session_state.doc_step = "input"  # input | outline_review | document_generated
    if "doc_requirements" not in st.session_state:
        st.session_state.doc_requirements = ""
    if "doc_outline" not in st.session_state:
        st.session_state.doc_outline = ""
    if "doc_content" not in st.session_state:
        st.session_state.doc_content = ""
    if "doc_generating" not in st.session_state:
        st.session_state.doc_generating = False
    if "doc_reference_context" not in st.session_state:
        st.session_state.doc_reference_context = ""
    if "doc_uploader_key" not in st.session_state:
        st.session_state.doc_uploader_key = 0  # 用于重置 file_uploader


    # ── 页面标题（嵌入模式下由母版统一显示，跳过）─────────
    if not embedded:
        st.title("📝 文档编写")
        st.caption("智能生成文档目录，确认后自动撰写完整文档")

    # ── 流程步骤指示器 ──────────────────────────────────
    step_names = {0: "输入需求", 1: "确认目录", 2: "生成文档"}
    step_map = {"input": 0, "outline_review": 1, "document_generated": 2}
    current_step = step_map.get(st.session_state.doc_step, 0)

    cols = st.columns(3)
    for i, (step_idx, step_name) in enumerate(step_names.items()):
        with cols[i]:
            if step_idx < current_step:
                st.markdown(f"✅ ~~{step_name}~~")
            elif step_idx == current_step:
                st.markdown(f"**🔵 {step_name}**")
            else:
                st.markdown(f"⚪ {step_name}")

    st.divider()

    # ================================================================
    # Step 1: 输入需求 → 生成目录（通过 doc_agent）
    # ================================================================
    if st.session_state.doc_step == "input":
        st.subheader("请描述您的文档需求")

        requirements = st.text_area(
            "需求描述",
            value=st.session_state.doc_requirements,
            placeholder=(
                "请详细描述您需要编写的文档，例如：\n\n"
                "文档类型：项目总结报告\n"
                "主题：2026年Q1企业数字化转型项目总结\n"
                "内容要点：\n"
                "- 项目背景与目标\n"
                "- 实施过程与关键节点\n"
                "- 成果与数据分析\n"
                "- 经验总结与改进建议\n"
                "- 下阶段规划\n\n"
                "风格：正式、专业，适合向管理层汇报"
            ),
            height=250,
            key="requirements_input",
        )

        # ── 文件上传（可选）─────────────────────────────
        uploaded_files = st.file_uploader(
            "📎 上传参考附件（可选，支持 .txt/.md/.docx/.pdf/.xlsx/.csv 等）",
            accept_multiple_files=True,
            type=["txt", "md", "docx", "pdf", "xlsx", "xls", "csv", "py", "json", "yaml", "yml", "log"],
            key=f"doc_uploader_{st.session_state.doc_uploader_key}",
        )

        col1, col2, col3 = st.columns([1, 1, 3])
        with col1:
            generate_btn = st.button("📋 生成目录", type="primary", use_container_width=True)

        if generate_btn:
            if not requirements.strip():
                st.error("请输入文档需求描述")
            else:
                st.session_state.doc_requirements = requirements

                # ── 处理上传附件 ──────────────────────
                file_contents = []
                if uploaded_files:
                    for f in uploaded_files:
                        text = extract_file_content(f, max_chars=8000)
                        file_contents.append((f.name, text))

                # ── 构建附件参考文本（知识库检索由 doc_agent 内部完成）──
                attachment_context = ""
                if file_contents:
                    attachment_lines = []
                    for i, (fname, text) in enumerate(file_contents, start=1):
                        attachment_lines.append(f"[附件{i}：{fname}]\n{text}")
                    attachment_context = "=== 用户上传附件 ===\n" + "\n\n".join(attachment_lines) + "\n\n"
                st.session_state.doc_reference_context = attachment_context

                with st.spinner("正在生成文档目录（检索知识库 + AI 生成）..."):
                    try:
                        if attachment_context:
                            outline_prompt = f"""【任务】生成文档目录

{attachment_context}
【用户需求】
{requirements}"""
                        else:
                            outline_prompt = f"""【任务】生成文档目录

【用户需求】
{requirements}"""

                        outline, steps_log, agent_used = chat_direct(
                            "doc_agent",
                            outline_prompt,
                            thread_id=f"doc_outline_{user['user_id']}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                            user_context=user,
                            username=user["username"],
                        )

                        # 展示 agent 生成步骤
                        if steps_log:
                            with st.expander("🔍 查看生成过程", expanded=False):
                                for step in steps_log:
                                    st.markdown(step)

                        st.session_state.doc_outline = outline
                        st.session_state.doc_step = "outline_review"

                        log_event(
                            user_id=user["user_id"],
                            username=user["username"],
                            action="doc_outline_generate",
                            status="success",
                        )
                        st.rerun()
                    except Exception as e:
                        st.error(f"目录生成失败：{e}")
                        log_event(
                            user_id=user["user_id"],
                            username=user["username"],
                            action="doc_outline_generate",
                            status="error",
                        )

        # 返回首页按钮
        with col2:
            if st.button("← 返回首页", use_container_width=True):
                st.session_state.doc_step = "input"
                st.session_state.agent_mode = "knowledge_qa"
                st.session_state.current_page = "首页"
                st.rerun()

    # ================================================================
    # Step 2: 确认/修改目录 → 生成文档（通过 doc_agent）
    # ================================================================
    elif st.session_state.doc_step == "outline_review":
        st.subheader("请确认或修改文档目录")
        st.caption("您可以直接在下方编辑框中修改目录结构，确认无误后点击生成文档")

        edited_outline = st.text_area(
            "文档目录",
            value=st.session_state.doc_outline,
            height=400,
            key="outline_editor",
            label_visibility="collapsed",
        )

        col1, col2, col3 = st.columns([1.5, 1, 2.5])
        with col1:
            confirm_btn = st.button(
                "✅ 确认目录，生成文档",
                type="primary",
                use_container_width=True,
            )
        with col2:
            back_btn = st.button("↩ 重新输入需求", use_container_width=True)

        if confirm_btn:
            if not edited_outline.strip():
                st.error("目录不能为空")
            else:
                st.session_state.doc_outline = edited_outline
                st.session_state.doc_generating = True

                with st.spinner("正在生成完整文档，请耐心等待..."):
                    try:
                        attachment_context = st.session_state.get("doc_reference_context", "")

                        content_prompt = f"""【任务】生成文档内容

{attachment_context}
【原始需求】
{st.session_state.doc_requirements}

【已确认的目录结构（严格遵循此结构）】
{edited_outline}"""

                        content, steps_log, agent_used = chat_direct(
                            "doc_agent",
                            content_prompt,
                            thread_id=f"doc_gen_{user['user_id']}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                            user_context=user,
                            username=user["username"],
                        )

                        # 展示 agent 生成步骤
                        if steps_log:
                            with st.expander("🔍 查看生成过程", expanded=False):
                                for step in steps_log:
                                    st.markdown(step)

                        st.session_state.doc_content = content
                        st.session_state.doc_step = "document_generated"
                        st.session_state.doc_generating = False

                        # 自动保存文档到历史记录
                        _auto_save_document(user, edited_outline)

                        log_event(
                            user_id=user["user_id"],
                            username=user["username"],
                            action="doc_generate",
                            status="success",
                        )
                        st.rerun()
                    except Exception as e:
                        st.session_state.doc_generating = False
                        st.error(f"文档生成失败：{e}")
                        log_event(
                            user_id=user["user_id"],
                            username=user["username"],
                            action="doc_generate",
                            status="error",
                        )

        if back_btn:
            st.session_state.doc_step = "input"
            st.session_state.doc_reference_context = ""
            st.session_state.doc_uploader_key += 1
            st.rerun()

    # ================================================================
    # Step 3: 展示生成的文档
    # ================================================================
    elif st.session_state.doc_step == "document_generated":
        import html as _html

        escaped_content = _html.escape(st.session_state.doc_content)

        # ── 注入自定义 CSS：减小字体、提升阅读密度 ──
        st.markdown("""
        <style>
        /* 仅在文档展示区域生效 */
        .doc-display-area h1 { font-size: 0.95rem !important; margin-top: 0.5rem !important; margin-bottom: 0.4rem !important; }
        .doc-display-area h2 { font-size: 0.90rem !important; margin-top: 0.7rem !important; margin-bottom: 0.3rem !important; }
        .doc-display-area h3 { font-size: 0.85rem !important; margin-top: 0.6rem !important; margin-bottom: 0.25rem !important; }
        .doc-display-area p, .doc-display-area li, .doc-display-area td, .doc-display-area th {
            font-size: 0.85rem !important; line-height: 1.55 !important;
        }
        .doc-display-area table { font-size: 0.82rem !important; }
        .doc-display-area { padding: 2.5rem 1rem 0.8rem 1rem !important; position: relative !important; }
        /* 复制按钮样式 —— 与 Streamlit st.code 复制按钮保持一致 */
        .doc-copy-btn {
            position: absolute; top: 0.5rem; right: 0.5rem; z-index: 10;
            background: #fff; border: 1px solid #e6e6e6; border-radius: 0.375rem;
            padding: 0.375rem; cursor: pointer; color: #4a4a4a; line-height: 1;
            display: inline-flex; align-items: center; justify-content: center;
            width: 2rem; height: 2rem;
        }
        .doc-copy-btn:hover { background: #f0f0f0; border-color: #ccc; }
        .doc-copy-btn:active { background: #e6e6e6; }
        </style>
        """, unsafe_allow_html=True)

        st.subheader("生成的文档")

        copy_icon_svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" '
            'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round">'
            '<rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>'
            '<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>'
            '</svg>'
        )
        copy_btn_html = (
            '<button class="doc-copy-btn" id="top-copy-btn" title="Copy to clipboard">'
            + copy_icon_svg +
            '</button>'
        )
        copy_script = (
            '<script>'
            '(function(){'
            'var btn=document.getElementById("top-copy-btn");'
            'if(!btn)return;'
            'btn.addEventListener("click",function(){'
            'var text=document.getElementById("doc-raw-source").value;'
            'function done(){'
            'btn.setAttribute("title","Copied!");'
            'setTimeout(function(){btn.setAttribute("title","Copy to clipboard");},2000);'
            '}'
            'if(navigator.clipboard&&navigator.clipboard.writeText){'
            'navigator.clipboard.writeText(text).then(done).catch(function(){'
            'var ta=document.createElement("textarea");ta.value=text;'
            'ta.style.cssText="position:fixed;top:-9999px;left:-9999px;opacity:0;";'
            'document.body.appendChild(ta);ta.select();'
            'try{document.execCommand("copy");}catch(e){}'
            'document.body.removeChild(ta);done();'
            '});'
            '}else{'
            'var ta=document.createElement("textarea");ta.value=text;'
            'ta.style.cssText="position:fixed;top:-9999px;left:-9999px;opacity:0;";'
            'document.body.appendChild(ta);ta.select();'
            'try{document.execCommand("copy");}catch(e){}'
            'document.body.removeChild(ta);done();'
            '}'
            '});'
            '})();'
            '</script>'
        )

        # 渲染文档内容（复制按钮嵌入容器内部右上角）
        with st.container(border=True):
            st.markdown(
                '<div class="doc-display-area">' + copy_btn_html + copy_script,
                unsafe_allow_html=True,
            )
            st.markdown(st.session_state.doc_content)
            st.markdown('</div>', unsafe_allow_html=True)

        # 藏一个 textarea 供 copy 按钮使用
        st.markdown(
            f'<textarea id="doc-raw-source" style="display:none;">{escaped_content}</textarea>',
            unsafe_allow_html=True,
        )

        st.divider()

        col1, col2, col3, col4 = st.columns([1.3, 1, 1, 1.7])
        with col1:
            if st.button("🔄 重新生成", use_container_width=True):
                st.session_state.doc_step = "outline_review"
                st.session_state.doc_content = ""
                st.rerun()
        with col2:
            if st.button("📝 新建文档", use_container_width=True):
                st.session_state.doc_step = "input"
                st.session_state.doc_requirements = ""
                st.session_state.doc_outline = ""
                st.session_state.doc_content = ""
                st.session_state.doc_reference_context = ""
                st.session_state.doc_uploader_key += 1  # 重置 file_uploader
                st.rerun()
        with col3:
            if st.button("← 返回首页", use_container_width=True):
                st.session_state.doc_step = "input"
                st.session_state.doc_reference_context = ""
                st.session_state.doc_uploader_key += 1
                st.session_state.agent_mode = "knowledge_qa"
                st.session_state.current_page = "首页"
                st.rerun()

        # 查看 Markdown 源码
        with st.expander("📋 查看 Markdown 源码（可复制）", expanded=False):
            st.code(st.session_state.doc_content, language="markdown")


