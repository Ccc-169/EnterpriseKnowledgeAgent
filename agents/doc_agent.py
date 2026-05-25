# agents/doc_agent.py
import time
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

# ── 规则引擎导入 ─────────────────────────────────────
from rules.integration import check_generated_answer


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
                time.sleep(wait)
            else:
                raise e
        except Exception:
            raise
    raise last_error


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


# ── 目录生成提示词 ─────────────────────────────────────────────────────────

OUTLINE_PROMPT = """你是一位专业的文档编写专家。请根据用户的需求，以及提供的参考上下文（可能包含用户上传的附件内容和知识库检索到的相关文件），生成一份结构清晰、逻辑严谨的文档目录。

要求：
1. 目录使用多级编号（如 1、1.1、1.1.1），层级控制在 2-3 级
2. 每个条目后附一句话说明（该章节将涵盖的内容简介）
3. 目录结构完整，覆盖用户需求的所有要点
4. **充分参考提供的参考上下文**：如果提示中带"【参考上下文】"部分，请结合其中的附件内容和知识库资料来设计目录结构，确保覆盖参考资料中的关键内容
5. 语言使用中文
6. 输出格式如下（Markdown 格式）：

# 文档标题：[根据需求自动生成标题]

## 1. 章节名 — 内容说明
### 1.1 小节名 — 内容说明
### 1.2 小节名 — 内容说明
...
## 2. 章节名 — 内容说明
...

只输出目录结构，不要添加其他说明文字。"""


# ── 文档生成提示词 ─────────────────────────────────────────────────────────

DOCUMENT_PROMPT = """你是一位资深的文档撰写专家。请根据用户确认的目录结构和原始需求，撰写一份专业、详实、格式规范的中文文档。

注意：
- 章节标题只用章节名和编号，不要包含目录里的补充说明文字（如 "—— 内容说明"）。
- 如果提示中有【参考上下文】，请合理引用其中的附件和知识库资料，并在引用处标注来源（如 [附件1]、[知识库：文件名.docx]）。

要求：
1. **严格遵循目录结构**：按用户确认的目录逐章节展开，不增删章节
2. **内容充实**：每个章节至少有一段实质性内容，避免空洞无物
3. **语言专业**：使用正式、专业的书面语，避免口语化表达
4. **格式规范**：使用 Markdown 格式，标题层级与目录一致（# → ## → ###）
5. **逻辑连贯**：章节之间过渡自然，前后呼应
6. **数据引用**：如有涉及数据的部分，使用示例数据并标注"（示例数据）"
7. **合理引用参考资料**：充分利用参考上下文中的附件和知识库内容，标注来源

输出格式：完整的 Markdown 格式文档，从文档标题开始，包含所有章节内容。"""


# ── Doc Agent 创建函数 ──────────────────────────────────────────────────────

def create_doc_agent(llm):

    @tool
    def generate_document_outline(requirements: str) -> str:
        """
        根据用户描述的需求，生成文档目录结构（含多级标题和内容说明）。
        适用场景：用户需要编写报告、方案、手册、总结、规章制度等各类文档时，第一步先生成目录。

        参数：
          requirements - 用户对文档的完整需求描述，包括文档类型、主题、内容要点、风格要求等
        """
        outline_input = f"{OUTLINE_PROMPT}\n\n用户需求：\n{requirements}"
        return _invoke_with_retry(llm, outline_input, label="目录生成")

    @tool
    def generate_document_content(outline: str, requirements: str) -> str:
        """
        根据用户已确认的目录结构和原始需求，生成完整的文档内容。
        必须在用户确认目录之后才调用此工具。
        适用场景：目录已确认，需要生成完整文档正文。

        参数：
          outline   - 用户已确认的文档目录结构（Markdown 格式）
          requirements - 用户原始需求描述
        """
        sections = _parse_sections(outline)

        # 如果解析不到章节，回退到一次性生成（兜底）
        if not sections:
            doc_input = (
                f"{DOCUMENT_PROMPT}\n\n"
                f"【原始需求】\n{requirements}\n\n"
                f"【已确认的目录结构（严格遵循此结构）】\n{outline}"
            )
            answer = _invoke_with_retry(llm, doc_input, label="文档生成")
            return answer

        # ── 逐章节生成，降低单次请求压力 ──
        full_doc_parts = []
        for idx, section_info in enumerate(sections, start=1):
            section_title = section_info["title"]
            subsections = section_info.get("subsections", [])

            # 构造二级标题提示
            subsections_str = ""
            if subsections:
                sub_list = "\n".join(f"  - {s}" for s in subsections)
                subsections_str = (
                    f"\n\n【该章节下的二级标题（必须在正文中以 ### 标题形式按顺序完整写入，不要遗漏）】\n"
                    f"{sub_list}\n"
                )

            section_prompt = (
                f"{SECTION_PROMPT}\n\n"
                f"【原始需求】\n{requirements}\n\n"
                f"【完整目录结构（供参考，不要写其他章节）】\n{outline}\n\n"
                f"【当前需要撰写的章节】\n{section_title}"
                f"{subsections_str}\n"
                f"【前面已生成的内容（供衔接参考）】\n"
                f"{'\n'.join(full_doc_parts[-2:]) if full_doc_parts else '（无，这是第一章）'}"
            )
            section_content = _invoke_with_retry(
                llm, section_prompt, label=f"第{idx}章"
            )
            full_doc_parts.append(section_content)

        answer = "\n\n".join(full_doc_parts)

        # 答案质量后校验
        try:
            report = check_generated_answer(answer, context=outline, agent_name="doc_agent")
            for f in report.get_failures():
                if f.rule_id == "GEN_QUALITY-002":
                    return "系统处理时遇到技术问题，已自动恢复。请您重新描述需求，或联系管理员处理。"
        except Exception:
            pass

        return answer

    @tool
    def improve_document_outline(outline: str, feedback: str) -> str:
        """
        根据用户的反馈意见，修改和完善文档目录结构。
        适用场景：用户对生成的目录不满意，提出了具体的修改意见。

        参数：
          outline  - 当前的文档目录结构
          feedback - 用户的修改意见和反馈
        """
        improve_prompt = f"""你是文档编写专家。请根据用户反馈修改文档目录。

当前目录：
{outline}

用户反馈：
{feedback}

请输出修改后的完整目录结构，保持 Markdown 格式和多级编号。只输出目录，不要添加其他说明。"""
        return _invoke_with_retry(llm, improve_prompt, label="目录修改")

    return create_react_agent(
        model=llm,
        name="doc_agent",
        tools=[generate_document_outline, generate_document_content, improve_document_outline],
        prompt="""你是企业文档编写专家，处理文档生成、报告撰写、方案编写等任务。

【工具说明】
- generate_document_outline：根据需求生成文档目录（第一步使用）
- generate_document_content：根据确认的目录生成完整文档（目录确认后使用）
- improve_document_outline：根据用户反馈修改目录

【工作流程】
1. 首先调用 generate_document_outline 生成目录
2. 将目录展示给用户确认或修改
3. 用户确认后，调用 generate_document_content 生成完整文档
4. 如果用户对目录有修改意见，调用 improve_document_outline 调整

【硬性约束】
1. 必须先确认目录再生成内容，不要跳过目录确认步骤
2. 生成的文档内容必须严格遵循已确认的目录结构
3. 文档使用中文撰写，格式规范、内容专业
4. 不编造需要实际数据的数字，如需数据应标注"（示例数据）"

【回答语言】中文。""",
    )
