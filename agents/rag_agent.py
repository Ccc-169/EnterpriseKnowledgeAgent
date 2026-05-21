# agents/rag_agent.py
import os
import json
import re
import requests
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent


# ── 常量 ────────────────────────────────────────────────────────────────

MAX_RETRY_COUNT = 1          # 检索验证最多重试 1 次
SHORT_QUERY_THRESHOLD = 10   # 短问题字符阈值
SHORT_WORD_THRESHOLD = 3     # 短问题词数阈值


# ── Query 改写 ────────────────────────────────────────────────────────────

QUERY_REWRITE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是一个企业知识库检索专家。
用户输入了一个问题，请将其改写为更适合向量语义检索的形式。

返回严格的 JSON 格式，包含以下字段：
- "rewritten_query": 改写后的完整语义查询（一句话，去除口语化，补充隐含意图）
- "keywords": 关键词列表（3-6个字符串）
- "sub_questions": 子问题列表（复合问题拆分；简单问题填原问题；最多3个）

只返回 JSON，禁止输出任何其他内容（包括 markdown 代码块标记）。"""),
    ("human", "原始问题：{question}"),
])


def rewrite_query(llm, question: str) -> dict:
    """
    用 LLM 改写用户查询，返回结构化检索参数。
    任何异常均回退到原始问题，保证主流程不中断。
    """
    if len(question) <= SHORT_QUERY_THRESHOLD or len(question.split()) <= SHORT_WORD_THRESHOLD:
        print(f"[QueryRewrite] 问题较短，跳过改写: {question}")
        return {
            "rewritten_query": question,
            "keywords": [],
            "sub_questions": [question],
        }

    try:
        chain = QUERY_REWRITE_PROMPT | llm
        result = chain.invoke({"question": question})
        text = result.content if hasattr(result, "content") else str(result)
        text = re.sub(r"```json|```", "", text).strip()
        parsed = json.loads(text)
        rewritten = {
            "rewritten_query": parsed.get("rewritten_query", question),
            "keywords": parsed.get("keywords", []),
            "sub_questions": parsed.get("sub_questions", [question]),
        }
        print(f"[QueryRewrite] 原始: {question}")
        print(f"[QueryRewrite] 改写: {rewritten['rewritten_query']}")
        print(f"[QueryRewrite] 关键词: {rewritten['keywords']}")
        return rewritten
    except Exception as e:
        print(f"[QueryRewrite] 改写失败，使用原始问题: {e}")
        return {
            "rewritten_query": question,
            "keywords": [],
            "sub_questions": [question],
        }


# ── 答案验证 ──────────────────────────────────────────────────────────────

ANSWER_VERIFY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是一个答案质量审核员。
根据以下信息判断答案质量，只返回一个词，不要有其他输出：

- GOOD         ：答案有明确的文档依据，内容具体，无无中生有。只要答案中包含了文档中的相关内容，即使不够全面也应判定为GOOD。
- HALLUCINATION：答案包含文档中未提及的内容，或编造了数据/规定
- NO_CONTEXT   ：文档中确实没有相关内容，答案已诚实说明"未找到"
- INSUFFICIENT ：仅当文档片段与问题完全无关，或答案完全无法回答问题时使用

判断原则：
1. 只要检索到的文档与问题有相关性（即使只是部分相关），且答案基于文档内容生成，就应判定为GOOD
2. 不要因为答案不够全面、不够详细就判定为INSUFFICIENT
3. 只有在文档片段与问题毫不相关、答案完全无法回答问题时，才判定为INSUFFICIENT

只返回四个词之一：GOOD / HALLUCINATION / NO_CONTEXT / INSUFFICIENT"""),
    ("human", """用户问题：{question}

检索到的文档片段：
{retrieved_context}

生成的答案：
{answer}

质量判断："""),
])


def verify_answer(llm, question: str, retrieved_context: str, answer: str) -> str:
    """
    验证答案质量，返回 GOOD / HALLUCINATION / NO_CONTEXT / INSUFFICIENT。
    任何异常均默认 GOOD（保守策略：验证失败时不阻断主流程）。
    """
    try:
        chain = ANSWER_VERIFY_PROMPT | llm
        result = chain.invoke({
            "question": question,
            "retrieved_context": retrieved_context,
            "answer": answer,
        })
        text = result.content.strip().upper() if hasattr(result, "content") else str(result).strip().upper()
        valid_verdicts = {"GOOD", "HALLUCINATION", "NO_CONTEXT", "INSUFFICIENT"}
        verdict = text if text in valid_verdicts else "GOOD"
        print(f"[AnswerVerify] 验证结果: {verdict}")
        return verdict
    except Exception as e:
        print(f"[AnswerVerify] 验证失败，默认通过: {e}")
        return "GOOD"


# ── 检索核心 ──────────────────────────────────────────────────────────────

def _retrieve_from_dify(base_url: str, api_key: str, kb_id: str, query: str) -> list:
    """调用 Dify 知识库检索 API，返回记录列表。"""
    resp = requests.post(
        f"{base_url}/datasets/{kb_id}/retrieve",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "query": query,
            "retrieval_model": {
                "search_method": "semantic_search",
                "reranking_enable": False,
                "top_k": 10,
                "score_threshold_enabled": False,
            },
        },
    )
    if resp.status_code != 200:
        print(f"[DifyRetrieve] 请求失败: {resp.status_code} {resp.text}")
        return []
    return resp.json().get("records", [])


def _format_records(records: list) -> str:
    """将检索记录格式化为可读文本。"""
    if not records:
        return ""
    chunks = sorted(records, key=lambda x: x.get("score", 0), reverse=True)
    return "\n---\n".join(
        f"[来源：{c['segment']['document']['name']}]\n{c['segment']['content']}"
        for c in chunks
    )


def _log_records(records: list, query: str) -> None:
    """打印检索结果调试日志。"""
    print(f"[DifyRetrieve] 查询: {query}")
    print(f"[DifyRetrieve] 返回记录数: {len(records)}")
    for i, record in enumerate(records):
        score = record.get("score", 0)
        source = record.get("segment", {}).get("document", {}).get("name", "未知来源")
        content_preview = record.get("segment", {}).get("content", "")[:50]
        print(f"[DifyRetrieve] 记录{i+1}: 分数={score:.3f}, 来源={source}, 内容预览={content_preview}...")


# ── RAG Agent 创建函数 ──────────────────────────────────────────────────────

def create_rag_agent(llm):

    DIFY_BASE_URL = "https://api.dify.ai/v1"
    DIFY_API_KEY  = os.environ["DIFY_DATASET_KEY"]
    DIFY_KB_ID    = os.environ["DIFY_KB_ID"]

    @tool
    def rag_search(query: str) -> str:
        """
        从企业知识库检索相关文档并生成答案。内置查询改写、回退检索、答案验证和自动重试。
        适用：文档问答、内容总结、制度查询、仿写参考。
        当检索不到相关内容或答案质量不佳时会自动重试，无需多次调用。
        """
        # Step 1: 查询改写
        rewritten = rewrite_query(llm, query)
        search_query = rewritten["rewritten_query"]

        # Step 2: 首次检索（用改写后的查询）
        records = _retrieve_from_dify(DIFY_BASE_URL, DIFY_API_KEY, DIFY_KB_ID, search_query)
        _log_records(records, search_query)

        # Step 3: 回退检索（用原始查询）
        if not records:
            print(f"[DifyRetrieve] 改写查询无结果，尝试原始查询: {query}")
            records = _retrieve_from_dify(DIFY_BASE_URL, DIFY_API_KEY, DIFY_KB_ID, query)
            _log_records(records, query)

        if not records:
            return "知识库中未检索到相关内容。建议联系对应部门确认，或提供更多背景信息以便进一步检索。"

        # Step 4: 生成答案 + 验证 + 重试
        context_text = _format_records(records)
        answer = _generate_answer(llm, query, context_text)

        verdict = verify_answer(llm, query, context_text, answer)
        retry_count = 0

        while verdict != "GOOD" and retry_count < MAX_RETRY_COUNT:
            retry_count += 1
            print(f"[AnswerVerify] 验证结果={verdict}，启动第{retry_count}次重试")

            if verdict == "NO_CONTEXT":
                return "根据当前知识库，未能找到与您问题直接相关的内容。建议联系对应部门确认，或提供更多背景信息以便进一步检索。"

            # HALLUCINATION 或 INSUFFICIENT：换一种表达方式重新检索
            retry_query = f"请详细介绍关于以下内容的规定：{query}"
            retry_records = _retrieve_from_dify(DIFY_BASE_URL, DIFY_API_KEY, DIFY_KB_ID, retry_query)
            _log_records(retry_records, retry_query)

            if not retry_records:
                if verdict == "INSUFFICIENT":
                    return f"{answer}\n\n⚠️ 以上回答基于知识库中部分相关内容，可能不够完整。如需更详细信息，建议联系对应部门确认。"
                return "根据当前知识库，未能找到与您问题直接相关的内容。建议联系对应部门确认。"

            context_text = _format_records(retry_records)
            answer = _generate_answer(llm, query, context_text)
            verdict = verify_answer(llm, query, context_text, answer)

        # 重试后仍不够完整，展示部分答案
        if verdict == "INSUFFICIENT":
            return f"{answer}\n\n⚠️ 以上回答基于知识库中部分相关内容，可能不够完整。如需更详细信息，建议联系对应部门确认。"

        # HALLUCINATION 重试后仍不行
        if verdict == "HALLUCINATION":
            return "检索到的文档与问题关联度不足，无法生成可靠答案。建议提供更具体的问题或联系对应部门确认。"

        return answer

    @tool
    def list_kb_documents(keyword: str = "") -> str:
        """
        查询 Dify 知识库中存储了哪些文档。
        当用户询问知识库里有什么文件时调用。
        参数：keyword - 可选，按文件名过滤关键词
        """
        page, all_docs = 1, []
        while True:
            resp = requests.get(
                f"{DIFY_BASE_URL}/datasets/{DIFY_KB_ID}/documents",
                headers={"Authorization": f"Bearer {DIFY_API_KEY}"},
                params={"page": page, "limit": 20},
            )
            if resp.status_code != 200:
                return f"查询失败：{resp.status_code} {resp.text}"
            data = resp.json()
            all_docs.extend(data.get("data", []))
            if not data.get("has_more", False):
                break
            page += 1

        if not all_docs:
            return "知识库中暂无文档。"
        if keyword:
            all_docs = [d for d in all_docs if keyword in d.get("name", "")]

        result_lines = []
        for doc in all_docs:
            status = "✓" if doc.get("indexing_status") == "completed" else "⏳"
            result_lines.append(f"{status} {doc['name']}")

        return f"知识库共有 {len(result_lines)} 个文档：\n" + "\n".join(result_lines)

    return create_react_agent(
        model=llm,
        name="rag_agent",
        tools=[rag_search, list_kb_documents],
        prompt="""你是企业知识库问答专家，处理文档检索、内容问答、制度查询、仿写参考等知识性问题。

【工具说明】
- rag_search：从知识库检索文档并生成答案，内置查询改写、回退检索、答案验证和自动重试，通常只需调用一次
- list_kb_documents：查看知识库中有哪些文档，当用户问"知识库里有什么"时使用

【硬性约束——这些是运行环境的物理限制，违反必然失败】
1. rag_search 已内置改写、验证和重试逻辑，不需要多次调用同一个查询
2. 如果 rag_search 返回"未检索到相关内容"，不要反复用不同措辞重试，应如实告知用户
3. 回答必须基于 rag_search 返回的文档内容，不得编造知识库中没有的信息

【回答语言】中文，检索不到时如实告知，不编造内容。""",
    )


# ── 辅助函数 ──────────────────────────────────────────────────────────────

def _generate_answer(llm, question: str, context_text: str) -> str:
    """基于检索到的上下文生成答案。"""
    answer_prompt = f"""请根据以下知识库文档内容回答用户问题。
如果文档中没有相关信息，请如实告知，不要编造内容。

文档内容：
{context_text}

用户问题：{question}
"""
    result = llm.invoke([HumanMessage(content=answer_prompt)])
    return result.content if hasattr(result, "content") else str(result)
