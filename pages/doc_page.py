# pages/doc_page.py — 文档编写专用页（两步交互：目录生成→用户确认→内容生成）
import time
from datetime import datetime
import streamlit as st
from auth.session import get_current_user, require_login, require_role
from audit.audit_service import log_event
from data.file_parser import extract_file_content
from data.kb_search import build_reference_context
from data.document_service import (
    save_document,
    get_documents,
    get_document,
    delete_document,
    generate_title_from_requirements,
)

# ── 目录生成提示词 ─────────────────────────────────────────────────────────

OUTLINE_PROMPT = """你是一位专业的文档编写专家。请根据用户的需求，以及提供的参考上下文（可能包含用户上传的附件内容和知识库检索到的相关文件），生成一份结构清晰、逻辑严谨的文档目录。

要求：
1. 目录使用多级编号（如 1、1.1、1.1.1），层级控制在 2-3 级
2. 每个条目后附一句话说明（该章节将涵盖的内容简介），格式为"章节名 — 内容说明"
3. 目录结构完整，覆盖用户需求的所有要点
4. **充分参考提供的参考上下文**：如果提示中带"【参考上下文】"部分，请结合其中的附件内容和知识库资料来设计目录结构，确保覆盖参考资料中的关键内容
5. 语言使用中文
6. 输出格式如下（Markdown 格式）：

# 文档标题：[根据需求自动生成标题]

## 1. 章节名 — 内容说明
### 1.1 小节名 — 内容说明
### 1.2 小节名 — 内容说明

## 2. 章节名 — 内容说明
### 2.1 小节名 — 内容说明
...

只输出目录结构，不要添加其他说明文字。"""


# ── 单章节生成提示词 ───────────────────────────────────────────────────────

SECTION_PROMPT = """你是一位资深的文档撰写专家。请根据用户提供的文档需求、参考上下文（包含附件和知识库资料）、整体目录结构，以及当前需要撰写的**单个章节**，撰写该章节的完整内容。

要求：
1. **只撰写当前指定的章节**，不要写其他章节
2. **一级标题只用章节名**：如 "## 1. 日报概述"，不要在标题中加入目录里的补充说明文字（如 "— 内容说明"）
3. **保留所有二级标题**：如果提示中给出了"该章节下的二级标题"列表，必须在正文中以 "### 1.1 xxx" 格式按顺序完整写入，每个二级标题下都要有对应的正文内容，绝对不能遗漏或跳过
4. **二级标题只用标题名和编号**：同样不要包含目录里的补充说明文字（如 "— 内容说明"）
5. **内容充实**：当前章节至少有两三段实质性内容，每个二级标题下也应有实质内容，避免空洞无物
6. **合理引用参考资料**：如果提示中带"【参考上下文】"部分，请充分利用其中的附件内容和知识库资料撰写正文，并在引用处标注来源，格式为：[附件1]、[附件2]、[知识库：文件名.docx] 等
7. **语言专业**：使用正式、专业的书面语，避免口语化表达
8. **格式规范**：使用 Markdown 格式，一级标题用 ##，二级标题用 ###
9. **数据引用**：如有涉及数据的部分，使用示例数据并标注"（示例数据）"
10. **自然过渡**：如果当前章节有前文章节，请适当衔接前文；如果是开头章节，直接切入主题

输出格式：只输出当前章节的 Markdown 内容，从该章节的一级标题开始，包含所有二级标题及其正文。不要输出其他章节的任何内容。"""


# ── 目录解析：提取一级章节（## 开头）及其下属二级标题（### 开头）──────────

def _parse_sections(outline: str):
    """从 Markdown 目录中提取一级章节及其下属二级标题。
    自动去除章节名后面的描述说明（如 "— 内容说明"），只保留章节名。
    返回 list[dict]，每项：{"title": str, "subsections": list[str]}"""
    import re
    sections = []
    current = None  # dict: {"title": ..., "subsections": [...]}
    for line in outline.strip().splitlines():
        m_h2 = re.match(r"^##\s+(.+)$", line.strip())
        m_h3 = re.match(r"^###\s+(.+)$", line.strip())
        if m_h2:
            if current is not None:
                sections.append(current)
            title = m_h2.group(1).strip()
            title = re.split(r"\s*[—－]\s*", title, maxsplit=1)[0].strip()
            current = {"title": title, "subsections": []}
        elif m_h3 and current is not None:
            sub_title = m_h3.group(1).strip()
            sub_title = re.split(r"\s*[—－]\s*", sub_title, maxsplit=1)[0].strip()
            current["subsections"].append(sub_title)
    if current is not None:
        sections.append(current)
    return sections


# ── LLM 调用重试 ──────────────────────────────────────────────────────────

def _invoke_with_retry(llm_obj, prompt: str, max_retries: int = 3, label: str = "生成"):
    """带重试的 LLM 调用，处理连接超时等瞬时错误。"""
    from openai import APIConnectionError

    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            result = llm_obj.invoke(prompt)
            return result.content if hasattr(result, "content") else str(result)
        except APIConnectionError as e:
            last_error = e
            if attempt < max_retries:
                wait = 2 ** attempt
                st.warning(f"{label}连接超时，正在重试（{attempt}/{max_retries}），等待 {wait} 秒...")
                time.sleep(wait)
            else:
                raise e
        except Exception:
            raise

    raise last_error


# ── 自动保存辅助函数 ─────────────────────────────────────────────────────────

def _auto_save_document(user: dict, outline: str) -> int | None:
    """文档生成完成后自动保存到数据库。返回 document_id，失败返回 None。"""
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
        return doc_id
    except Exception:
        return None


# ── 历史记录渲染辅助 ──────────────────────────────────────────────────────

def _render_doc_history(user_id: int):
    """在页面底部渲染文档编写历史记录列表。"""
    # 按需从数据库重新加载
    if st.session_state.doc_history_reload:
        st.session_state.doc_history = get_documents(user_id)
        st.session_state.doc_history_reload = False

    docs = st.session_state.doc_history

    # 确定当前文档是否已有的历史（用于高亮）
    current_doc_id = st.session_state.get("doc_current_id", None)

    for doc in docs:
        doc_id = doc["id"]
        title = doc["title"]
        updated_at = doc["updated_at"]

        # 计算相对时间
        try:
            dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            now = datetime.now()
            delta = now.replace(tzinfo=None) - dt.replace(tzinfo=None)
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

        preview = doc.get("requirements_preview", "") or ""

        col_time, col_title, col_query, col_del = st.columns([0.85, 4, 1.4, 0.7])
        with col_time:
            st.markdown(
                f"<div style='background:#f0f2f6;border-radius:6px;padding:5px 4px;"
                f"text-align:center;font-size:0.78em;color:#555;line-height:1.8;"
                f"white-space:nowrap'>{rel_time}</div>",
                unsafe_allow_html=True,
            )
        with col_title:
            is_current = (current_doc_id == doc_id)
            btn_type = "primary" if is_current else "secondary"
            if st.button(
                f"{'📄 ' if is_current else ''}{title[:20]}{'...' if len(title) > 20 else ''}",
                key=f"doc_hist_{doc_id}",
                use_container_width=True,
                type=btn_type,
            ):
                _load_history_document(doc_id, user_id)
        with col_query:
            if st.button("📋 查看用户query", key=f"doc_query_{doc_id}", use_container_width=True):
                st.session_state.doc_expanded_id = (
                    None if st.session_state.get("doc_expanded_id") == doc_id else doc_id
                )
                st.rerun()
        with col_del:
            if st.button("🗑️", key=f"doc_del_{doc_id}", use_container_width=True):
                delete_document(doc_id, user_id)
                if st.session_state.get("doc_current_id") == doc_id:
                    st.session_state.doc_current_id = None
                st.session_state.doc_history_reload = True
                st.rerun()

        # 点击"查看用户query"后在按钮下方局部展开完整需求原文
        if st.session_state.get("doc_expanded_id") == doc_id:
            with st.expander("📝 用户原始需求", expanded=True):
                st.text(preview)


def _load_history_document(doc_id: int, user_id: int):
    """从数据库加载历史文档到 session_state 并跳转到展示页。"""
    doc = get_document(doc_id, user_id)
    if doc:
        st.session_state.doc_requirements = doc.get("requirements", "")
        st.session_state.doc_outline = doc.get("outline", "")
        st.session_state.doc_content = doc.get("content", "")
        st.session_state.doc_reference_context = doc.get("reference_context", "")
        st.session_state.doc_step = "document_generated"
        st.session_state.doc_current_id = doc_id
        st.session_state.doc_expanded_id = None  # 清除展开状态
        st.rerun()


# ── 页面渲染 ──────────────────────────────────────────────────────────────

def render():
    """渲染文档编写页面，实现两步交互流程。"""
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
    if "doc_history" not in st.session_state:
        st.session_state.doc_history = []  # 文档生成历史列表
    if "doc_history_reload" not in st.session_state:
        st.session_state.doc_history_reload = True
    if "doc_current_id" not in st.session_state:
        st.session_state.doc_current_id = None  # 当前查看的历史文档ID（用于高亮）
    if "doc_expanded_id" not in st.session_state:
        st.session_state.doc_expanded_id = None  # 当前展开query的历史文档ID

    # ── 页面标题 ─────────────────────────────────────────
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

    # ── 获取 LLM 实例 ───────────────────────────────────
    from agent import llm

    # ================================================================
    # Step 1: 输入需求 → 生成目录
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

                # ── 构建参考上下文（附件 + 知识库）─────
                reference_context = build_reference_context(file_contents, requirements)
                st.session_state.doc_reference_context = reference_context

                with st.spinner("正在生成文档目录..."):
                    try:
                        if reference_context:
                            outline_input = (
                                f"{OUTLINE_PROMPT}\n\n"
                                f"{reference_context}\n"
                                f"用户需求：\n{requirements}"
                            )
                        else:
                            outline_input = f"{OUTLINE_PROMPT}\n\n用户需求：\n{requirements}"
                        outline = _invoke_with_retry(llm, outline_input, label="目录")
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

        # 返回对话按钮
        with col2:
            if st.button("← 返回对话", use_container_width=True):
                st.session_state.doc_step = "input"
                st.session_state.doc_current_id = None
                st.session_state.doc_expanded_id = None
                st.session_state.current_page = "对话"
                st.rerun()

    # ================================================================
    # Step 2: 确认/修改目录 → 生成文档
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

                # 解析章节列表
                sections = _parse_sections(edited_outline)

                # 如果解析不到章节，回退到一次性生成（兜底）
                if not sections:
                    with st.spinner("正在根据目录生成完整文档，请耐心等待..."):
                        try:
                            ref_ctx = st.session_state.get("doc_reference_context", "")
                            doc_input = (
                                f"你是一位资深的文档撰写专家。请根据用户确认的目录结构和原始需求，"
                                f"撰写一份专业、详实、格式规范的中文文档。\n\n"
                                "注意：\n"
                                "- 章节标题只用章节名和编号，不要包含目录里的补充说明文字（如 —— 内容说明）。\n"
                                "- 如果提示中有【参考上下文】，请合理引用其中的附件和知识库资料，并在引用处标注来源"
                                "（如 [附件1]、[知识库：文件名.docx]）。\n\n"
                                + (f"{ref_ctx}\n" if ref_ctx else "")
                                + f"【原始需求】\n{st.session_state.doc_requirements}\n\n"
                                + f"【已确认的目录结构（严格遵循此结构）】\n{edited_outline}"
                            )
                            content = _invoke_with_retry(llm, doc_input, label="文档")
                            st.session_state.doc_content = content
                            st.session_state.doc_step = "document_generated"
                            st.session_state.doc_generating = False

                            # 自动保存文档到历史记录
                            _auto_save_document(user, edited_outline)
                            st.session_state.doc_history_reload = True

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
                else:
                    # ── 逐章节生成 ───────────────────────────────
                    progress_bar = st.progress(0, text="准备生成文档...")
                    status_text = st.empty()
                    full_doc_parts = []

                    try:
                        total = len(sections)
                        for idx, section_info in enumerate(sections, start=1):
                            section_title = section_info["title"]
                            subsections = section_info.get("subsections", [])
                            progress = int(idx / total * 100)
                            progress_bar.progress(
                                progress,
                                text=f"正在生成第 {idx}/{total} 章：{section_title[:20]}...",
                            )
                            status_text.info(f"📝 正在撰写：{section_title}")

                            # 构造二级标题提示
                            subsections_str = ""
                            if subsections:
                                sub_list = "\n".join(f"  - {s}" for s in subsections)
                                subsections_str = (
                                    f"\n\n【该章节下的二级标题（必须在正文中以 ### 标题形式按顺序完整写入，不要遗漏）】\n"
                                    f"{sub_list}\n"
                                )

                            # 构造单章节 prompt（减少单次输入长度）
                            ref_ctx = st.session_state.get("doc_reference_context", "")
                            section_prompt = (
                                f"{SECTION_PROMPT}\n\n"
                                + (f"{ref_ctx}\n" if ref_ctx else "")
                                + f"【原始需求】\n{st.session_state.doc_requirements}\n\n"
                                f"【完整目录结构（供参考，不要写其他章节）】\n{edited_outline}\n\n"
                                f"【当前需要撰写的章节】\n{section_title}"
                                f"{subsections_str}\n"
                                f"【前面已生成的内容（供衔接参考）】\n"
                                f"{'\n'.join(full_doc_parts[-2:]) if full_doc_parts else '（无，这是第一章）'}"
                            )

                            section_content = _invoke_with_retry(
                                llm, section_prompt, label=f"第{idx}章"
                            )
                            full_doc_parts.append(section_content)

                        # 拼接完整文档
                        st.session_state.doc_content = "\n\n".join(full_doc_parts)
                        st.session_state.doc_step = "document_generated"
                        st.session_state.doc_generating = False
                        progress_bar.empty()
                        status_text.empty()

                        # 自动保存文档到历史记录
                        _auto_save_document(user, edited_outline)
                        st.session_state.doc_history_reload = True

                        log_event(
                            user_id=user["user_id"],
                            username=user["username"],
                            action="doc_generate",
                            status="success",
                        )
                        st.rerun()
                    except Exception as e:
                        st.session_state.doc_generating = False
                        progress_bar.empty()
                        status_text.empty()
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
            st.session_state.doc_current_id = None
            st.session_state.doc_expanded_id = None
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
        .doc-display-area h1 { font-size: 1.2rem !important; margin-top: 0.9rem !important; margin-bottom: 0.4rem !important; }
        .doc-display-area h2 { font-size: 1.05rem !important; margin-top: 0.7rem !important; margin-bottom: 0.3rem !important; }
        .doc-display-area h3 { font-size: 0.9rem !important; margin-top: 0.6rem !important; margin-bottom: 0.25rem !important; }
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
                st.session_state.doc_current_id = None
                st.session_state.doc_expanded_id = None
                st.session_state.doc_uploader_key += 1  # 重置 file_uploader
                st.rerun()
        with col3:
            if st.button("← 返回对话", use_container_width=True):
                st.session_state.doc_step = "input"
                st.session_state.doc_reference_context = ""
                st.session_state.doc_current_id = None
                st.session_state.doc_expanded_id = None
                st.session_state.doc_uploader_key += 1
                st.session_state.current_page = "对话"
                st.rerun()

        # 复制文档按钮（使用 st.code 方便复制）
        with st.expander("📋 查看 Markdown 源码（可复制）", expanded=False):
            st.code(st.session_state.doc_content, language="markdown")

    # ================================================================
    # 页面底部：文档编写历史记录
    # ================================================================
    st.divider()
    st.subheader("📚 历史生成文档")

    # 加载历史列表
    if st.session_state.doc_history_reload or not st.session_state.doc_history:
        st.session_state.doc_history = get_documents(user["user_id"])
        st.session_state.doc_history_reload = False

    docs = st.session_state.doc_history
    if not docs:
        st.caption("暂无历史生成文档，生成文档后将自动保存到此处")
    else:
        # 清除历史记录中高亮的"当前文档ID"标记（如果用户切回 input）
        current_doc_id = st.session_state.get("doc_current_id", None)
        for doc in docs:
            doc_id = doc["id"]
            title = doc["title"]
            updated_at = doc["updated_at"]

            # 计算相对时间
            try:
                dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                now = datetime.now()
                delta = now.replace(tzinfo=None) - dt.replace(tzinfo=None)
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

            preview = doc.get("requirements_preview", "") or ""

            is_current = (current_doc_id == doc_id)
            col_time, col_title, col_query, col_del = st.columns([0.85, 4, 1.4, 0.7])
            with col_time:
                st.markdown(
                    f"<div style='background:#f0f2f6;border-radius:6px;padding:5px 4px;"
                    f"text-align:center;font-size:0.78em;color:#555;line-height:1.8;"
                    f"white-space:nowrap'>{rel_time}</div>",
                    unsafe_allow_html=True,
                )
            with col_title:
                prefix = "📄 " if is_current else ""
                if st.button(
                    f"{prefix}{title[:20]}{'...' if len(title) > 20 else ''}",
                    key=f"doc_hist_{doc_id}",
                    use_container_width=True,
                    type="primary" if is_current else "secondary",
                ):
                    _load_history_document(doc_id, user["user_id"])
            with col_query:
                if st.button("📋 查看用户query", key=f"doc_query_{doc_id}", use_container_width=True):
                    st.session_state.doc_expanded_id = (
                        None if st.session_state.get("doc_expanded_id") == doc_id else doc_id
                    )
                    st.rerun()
            with col_del:
                if st.button("🗑️", key=f"doc_del_{doc_id}", use_container_width=True):
                    delete_document(doc_id, user["user_id"])
                    if st.session_state.get("doc_current_id") == doc_id:
                        st.session_state.doc_current_id = None
                    st.session_state.doc_history_reload = True
                    st.rerun()

            # 点击"查看用户query"后在按钮下方局部展开完整需求原文
            if st.session_state.get("doc_expanded_id") == doc_id:
                with st.expander("📝 用户原始需求", expanded=True):
                    st.text(preview)
