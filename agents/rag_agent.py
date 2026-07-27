# agents/rag_agent.py
import json
import re
import logging
import threading
import requests
from typing import TypedDict, Annotated
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.graph.message import add_messages
from langgraph.graph import StateGraph, START, END

# ── 规则引擎导入 ─────────────────────────────────────
from rules.integration import check_generated_answer

logger = logging.getLogger(__name__)


# ── 实时进度推送机制 ─────────────────────────────────────────────────────
# threading.local 存储：由 agent.py chat_direct 注入 progress_callback，
# 节点函数通过 _emit_progress 发送实时进度，绕过 LangGraph 流式通道。
_local = threading.local()


def _emit_progress(text: str):
    """推送实时进度到 SSE 通道。异常静默吞掉，绝不打断主流程。"""
    try:
        cb = getattr(_local, 'progress_callback', None)
        if cb:
            cb(text)
    except Exception:
        pass


# ── 常量 ────────────────────────────────────────────────────────────────

SHORT_QUERY_THRESHOLD = 10   # 短问题字符阈值
SHORT_WORD_THRESHOLD = 3     # 短问题词数阈值


# ── StateGraph State 定义 ──────────────────────────────────────────────────

class RAGAgentState(TypedDict):
    """RAG Agent 的 StateGraph 共享状态"""
    messages: Annotated[list, add_messages]  # LangGraph 标准消息字段（Supervisor 接口契约）
    question: str          # 从 messages 提取的原始用户问题
    cache_context: str     # QA 缓存上下文（历史相似问答参考）
    search_query: str      # LLM 改写后的检索查询
    records: list          # 检索到的知识库记录列表
    context_text: str      # 格式化后的检索文本
    full_context: str      # context_text + cache_context（最终送给 generate 的上下文）
    answer: str            # LLM 生成的答案
    # === 新增（KB 指纹 + 双阈值短路）===
    kb_version: str                  # 当前 KB 全局指纹
    short_circuit: bool              # 是否跳过 RAG + LLM
    short_circuit_answer: str        # 短路时直接用的答案
    cache_hit_id: int                # 短路命中的 qa_cache.id（用于 hit_count 计数）


# ── 意图分类关键词常量 ──────────────────────────────────────────────────────
# ⚠️ 注意：plan.md 明确指出"无意图分类"，当前 Workflow 为纯线性流程。
# 以下常量保留用于可能的未来扩展（如质检/监控分类），当前流程中不参与路由决策。

INTENT_KEYWORDS: dict[str, list[str]] = {
    "greeting":        ["你好", "您好", "hi", "hello", "hey", "早上好", "下午好", "晚上好", "再见", "谢谢"],
    "knowledge_query": ["是什么", "如何", "怎么", "什么是", "怎样", "介绍", "说明", "描述", "解释", "区别"],
    "policy_query":    ["制度", "规定", "政策", "流程", "办法", "标准", "规则", "要求", "规范", "条例"],
    "troubleshooting": ["故障", "报错", "错误", "问题", "不工作", "失败", "异常", "无法", "不能"],
    "writing_reference": ["仿写", "范文", "模板", "参考", "示例", "样例", "格式", "模版"],
}


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


# ── 检索核心 ──────────────────────────────────────────────────────────────

def _retrieve_from_ragflow(base_url: str, api_key: str, dataset_id: str, query: str) -> list:
    """调用 RAGFlow 知识库检索 API，返回记录列表（统一为 RAGFlow records 格式）。"""
    resp = requests.post(
        f"{base_url}/retrieval",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "question": query,
            "dataset_ids": [dataset_id],
            "page": 1,
            "page_size": 4,
            "similarity_threshold": 0.2,
            "vector_similarity_weight": 0.7,
            "keyword": False,
        },
        timeout=20,
    )
    if resp.status_code != 200:
        print(f"[RAGFlowRetrieve] 请求失败: {resp.status_code} {resp.text}")
        return []
    data = resp.json().get("data", {})
    chunks = data.get("chunks", [])
    # 构建 doc_id → doc_name 映射
    doc_name_map = {d["doc_id"]: d["doc_name"] for d in data.get("doc_aggs", [])}
    # 转换为内部统一格式
    records = []
    for c in chunks:
        records.append({
            "score": c.get("similarity", 0),
            "segment": {
                "content": c.get("content", ""),
                "document": {"name": doc_name_map.get(c.get("document_id", ""), "未知文档")},
            },
        })
    return records


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
    print(f"[RAGFlowRetrieve] 查询: {query}")
    print(f"[RAGFlowRetrieve] 返回记录数: {len(records)}")
    for i, record in enumerate(records):
        score = record.get("score", 0)
        source = record.get("segment", {}).get("document", {}).get("name", "未知来源")
        content_preview = record.get("segment", {}).get("content", "")[:50]
        print(f"[RAGFlowRetrieve] 记录{i+1}: 分数={score:.3f}, 来源={source}, 内容预览={content_preview}...")


# ── 规则引擎后校验 ──────────────────────────────────────────────────────

# 规则 → 替换文本映射，按优先级排序（先匹配优先返回）
RULE_RESPONSE_MAP: list[tuple[str, str]] = [
    ("GEN_QUALITY-002", "系统处理时遇到技术问题，已自动恢复。请您重新描述问题，或联系管理员处理。"),
    ("GEN_QUALITY-003", "回答中包含系统内部信息，已自动过滤。请重新提问或联系管理员。"),
    ("GEN_QUALITY-001", "未能生成有效回答，请尝试更具体地描述您的问题。"),
    ("GEN_QUALITY-004", "未找到相关信息，请尝试换个方式提问或联系管理员。"),
    # GEN_QUALITY-005: info 级别，追加提示而非替换
]


def _post_check_answer(raw_answer: str, context_text: str = "") -> str:
    """对生成的答案执行全局质量检查，按规则优先级返回友好提示"""
    try:
        report = check_generated_answer(raw_answer, context=context_text, agent_name="rag_agent")
        failures = report.get_failures()
        if not failures:
            return raw_answer

        # 1. 按优先级匹配替换型规则
        matched_ids = {f.rule_id for f in failures}
        for rule_id, replacement in RULE_RESPONSE_MAP:
            if rule_id in matched_ids:
                return replacement

        # 2. GEN_QUALITY-005: info 级别，追加提示而非替换
        if "GEN_QUALITY-005" in matched_ids and len(raw_answer) < 50:
            return raw_answer + "\n\n---\n💡 如需更详细的信息，请进一步描述您的问题。"

        # 3. 其他规则失败：记录日志但不替换
        logger.info(f"[post_check] 答案有轻微质量问题但无需替换: "
                    f"{', '.join(f.rule_id for f in failures)}")
    except Exception:
        pass  # 规则引擎异常时静默跳过
    return raw_answer


# ── RAG Agent 创建函数 ──────────────────────────────────────────────────────

def create_rag_agent(llm):
    from core.config import RAGFLOW_API_BASE as RAGFLOW_BASE_URL, RAGFLOW_API_KEY, RAGFLOW_DATASET_ID

    # ── 节点函数 ──────────────────────────────────────────────────────────

    def extract_question_node(state: RAGAgentState) -> dict:
        """从 messages 提取用户问题"""
        _emit_progress("📋 正在分析您的问题...")
        for msg in reversed(state.get("messages", [])):
            if isinstance(msg, HumanMessage):
                return {"question": msg.content}
        return {"question": ""}

    def cache_check_node(state: RAGAgentState) -> dict:
        """QA 缓存检查（KB 指纹 + 双阈值短路版）"""
        _emit_progress("🔍 正在查询历史相似问答...")
        question = state.get("question", "")

        # 文件日志（解决 print 不到终端的问题）
        import logging, os
        _cl = logging.getLogger("qacache_check")
        if not _cl.handlers:
            # 日志写入 data/cache_debug.log（和 chat_page 同一个文件）
            _log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "cache_debug.log")
            _h = logging.FileHandler(os.path.normpath(_log_path), encoding="utf-8")
            _h.setFormatter(logging.Formatter("%(asctime)s [CHECK] %(message)s"))
            _cl.addHandler(_h)
            _cl.setLevel(logging.DEBUG)

        _cl.info(f"question={question[:60]}")
        cache_context = ""
        short_circuit = False
        short_circuit_answer = ""
        cache_hit_id = 0
        kb_version = ""
        try:
            from data.kb_version import compute_kb_fingerprint
            from data.cache_service import embed_text, search_qa_cache, increment_qa_cache_hit
            from core.config import ENABLE_QA_CACHE_SHORTCIRCUIT

            _cl.info(f"ENABLE_QA_CACHE_SHORTCIRCUIT={ENABLE_QA_CACHE_SHORTCIRCUIT}")
            kb_version = compute_kb_fingerprint()
            _cl.info(f"kb_version={kb_version}")
            question_vec = embed_text(question)
            _cl.info(f"embed_text success={question_vec is not None}, dim={len(question_vec) if question_vec else 0}")
            if question_vec:
                result = search_qa_cache(
                    question_vec=question_vec,
                    kb_version=kb_version,
                )
                level = result["level"]
                _cl.info(f"result: level={level}, score={result.get('score')}, candidates={len(result.get('raw_candidates', []))}")
                if level == "high" and ENABLE_QA_CACHE_SHORTCIRCUIT:
                    short_circuit = True
                    short_circuit_answer = result["answer"]
                    _emit_progress(f"⚡ 缓存命中(高置信={result['score']:.2f})，跳过检索")
                    _cl.info("SHORT_CIRCUIT! 跳过RAG+LLM")
                elif level == "med":
                    cache_context = (
                        f"\n\n【历史相似问答（KB版本已校验={kb_version[:8]}，可作参考骨架）】\n"
                        f"相似度={result['score']}\n历史回答：{result['context']}"
                    )
                    _emit_progress(f"✅ 缓存命中(中置信={result['score']:.2f})")
                    _cl.info("中置信，提供上下文参考")
                elif level == "low":
                    _emit_progress(f"ℹ️ 缓存候选未达阈值({result['score']:.2f})，走完整检索")
                    _cl.info(f"低置信({result.get('score')}),走完整检索")
                else:
                    _emit_progress("ℹ️ 未命中历史问答缓存")
                    _cl.info("完全未命中，走完整检索")
                if result.get("raw_candidates"):
                    cache_hit_id = result["raw_candidates"][0].get("id", 0)
            else:
                _cl.warning("embed_text 返回 None")
        except Exception as e:
            _cl.exception(f"缓存检查异常: {e}")
        return {
            "cache_context": cache_context,
            "kb_version": kb_version,
            "short_circuit": short_circuit,
            "short_circuit_answer": short_circuit_answer,
            "cache_hit_id": cache_hit_id,
        }

    def rewrite_query_node(state: RAGAgentState) -> dict:
        """查询改写"""
        _emit_progress("🔄 正在优化检索查询...")
        question = state.get("question", "")
        rewritten = rewrite_query(llm, question)
        _emit_progress("✅ 查询优化完成")
        return {"search_query": rewritten["rewritten_query"]}

    def retrieve_node(state: RAGAgentState) -> dict:
        """向量检索（含回退：改写查询无结果时用原始 query 重试一次）"""
        _emit_progress("📚 正在检索知识库...")
        question = state.get("question", "")
        search_query = state.get("search_query", question)

        # 首次检索（用改写后的查询）
        records = _retrieve_from_ragflow(RAGFLOW_BASE_URL, RAGFLOW_API_KEY, RAGFLOW_DATASET_ID, search_query)
        _log_records(records, search_query)

        # 回退检索（用原始查询）
        if not records:
            print(f"[RAGFlowRetrieve] 改写查询无结果，尝试原始查询: {question}")
            records = _retrieve_from_ragflow(RAGFLOW_BASE_URL, RAGFLOW_API_KEY, RAGFLOW_DATASET_ID, question)
            _log_records(records, question)

        context_text = _format_records(records)
        cache_context = state.get("cache_context", "")
        full_context = context_text + cache_context if cache_context else context_text

        _emit_progress(f"{'✅ 检索完成，找到 ' + str(len(records)) + ' 条相关记录' if records else '⚠️ 未检索到相关记录'}")

        return {
            "records": records,
            "context_text": context_text,
            "full_context": full_context,
        }

    def generate_answer_node(state: RAGAgentState) -> dict:
        """基于检索上下文生成答案"""
        _emit_progress("✍️ 正在生成答案...")
        question = state.get("question", "")
        full_context = state.get("full_context", "")
        answer = _generate_answer(llm, question, full_context)
        _emit_progress("✅ 答案生成完成")
        return {"answer": answer}

    def post_check_node(state: RAGAgentState) -> dict:
        """规则引擎后校验，输出最终 AIMessage"""
        _emit_progress("🛡️ 正在进行答案质量校验...")
        if state.get("short_circuit") and state.get("short_circuit_answer"):
            # 短路命中：缓存答案也要走规则引擎校验
            raw_answer = state["short_circuit_answer"]
            # 异步更新 hit_count
            try:
                from data.cache_service import increment_qa_cache_hit
                hit_id = state.get("cache_hit_id", 0)
                if hit_id:
                    increment_qa_cache_hit(hit_id)
            except Exception as e:
                print(f"[QACache] hit_count 更新失败: {e}")
        else:
            raw_answer = state.get("answer", "")
        context_text = state.get("context_text", "")
        final_answer = _post_check_answer(raw_answer, context_text)
        return {"messages": [AIMessage(content=final_answer, name="rag_agent")]}

    def no_answer_node(state: RAGAgentState) -> dict:
        """未检索到结果时的回复"""
        _emit_progress("⚠️ 未找到相关信息，生成提示回复...")
        fallback = "知识库中未检索到相关内容。建议联系对应部门确认，或提供更多背景信息以便进一步检索。"
        return {"messages": [AIMessage(content=fallback, name="rag_agent")]}

    # ── 条件路由 ──────────────────────────────────────────────────────────

    def route_after_cache_check(state: RAGAgentState) -> str:
        """缓存后路由：short_circuit=True 直接跳到 post_check，否则走完整 RAG 流程"""
        if state.get("short_circuit"):
            return "post_check"
        return "rewrite_query"

    def route_after_retrieve(state: RAGAgentState) -> str:
        """检索后路由：有结果 → generate_answer，无结果 → no_answer"""
        if state.get("records"):
            return "generate_answer"
        return "no_answer"

    # ── 构建 StateGraph ──────────────────────────────────────────────────

    graph = StateGraph(RAGAgentState)
    graph.name = "rag_agent"

    graph.add_node("extract_question", extract_question_node)
    graph.add_node("cache_check", cache_check_node)
    graph.add_node("rewrite_query", rewrite_query_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("generate_answer", generate_answer_node)
    graph.add_node("post_check", post_check_node)
    graph.add_node("no_answer", no_answer_node)

    graph.add_edge(START, "extract_question")
    graph.add_edge("extract_question", "cache_check")
    # 新增条件路由：short_circuit 直接跳到 post_check
    graph.add_conditional_edges(
        "cache_check",
        route_after_cache_check,
        {
            "post_check": "post_check",
            "rewrite_query": "rewrite_query",
        },
    )
    graph.add_edge("rewrite_query", "retrieve")
    graph.add_conditional_edges("retrieve", route_after_retrieve)
    graph.add_edge("generate_answer", "post_check")
    graph.add_edge("post_check", END)
    graph.add_edge("no_answer", END)

    return graph.compile(name="rag_agent")


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
