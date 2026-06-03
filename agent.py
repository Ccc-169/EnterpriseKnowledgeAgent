# agent.py
import os
import re
import sqlite3
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph_supervisor import create_supervisor
from langgraph.checkpoint.sqlite import SqliteSaver
from langchain_core.messages import HumanMessage, AIMessage
from agents.rag_agent import create_rag_agent
from agents.data_agent import create_data_agent
from agents.doc_agent import create_doc_agent
from rules.integration import init_engine, check_user_input
from rules.engine import RuleViolationError

load_dotenv()

# ── LLM ──────────────────────────────────────────────
# 云端 Qwen API（按量计费）
llm = ChatOpenAI(
    model="qwen-plus",
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    api_key=os.environ["QWEN_API_KEY"],
    temperature=0,
    max_tokens=8192,
    timeout=300,
    max_retries=2,
)

# # 本地 Ollama（需先启动 Ollama 服务，模型名根据本地部署情况修改）
# llm = ChatOpenAI(
#     model="qwen3.6:35b",
#     base_url="http://192.168.1.155:11434/v1",
#     api_key="ollama",
#     temperature=0,
# )



# ── 创建三个 Sub-Agent ────────────────────────────────
rag_agent  = create_rag_agent(llm)
data_agent = create_data_agent(llm)
doc_agent  = create_doc_agent(llm)

# ── 初始化全局规则引擎（含 LLM 检查器）──────────────
init_engine(llm=llm)

# ── Router：只做分发，不干活 ──────────────────────
# 使用 SqliteSaver 持久化 checkpointer（替代纯内存的 MemorySaver）
# 优势：Streamlit rerun / 服务重启后对话状态不丢失
# 注意：from_conn_string() 是 context manager，模块级使用需手动管理连接
_CHECKPOINT_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "checkpoints.sqlite")
_checkpoint_conn = sqlite3.connect(_CHECKPOINT_DB, check_same_thread=False)
checkpointer = SqliteSaver(_checkpoint_conn)
checkpointer.setup()

router = create_supervisor(
    agents=[rag_agent, data_agent],
    model=llm,
    prompt="""
    你是任务路由器，只做一件事：
判断问题类型，转发给对应 Agent，然后将 Agent 的回答原样返回。
禁止修改、总结、补充 Agent 的任何回答内容。

转发给 rag_agent 的情况：
- 对文档内容提问（公司制度、规定、政策、员工手册）
- 总结文档、仿写内容、文档概述
- 撰写简短报告、工作总结、方案建议等文本类内容
- 查询知识库里有哪些文档
- 公司背景、业务介绍等知识性问题
- 文档管理、技术方案等咨询建议类问题（由 rag_agent 基于 LLM 知识回答）

转发给 data_agent 的情况：
- 统计、排名、汇总、计算
- 出勤率、迟到次数、工作时长等考勤数据分析
- 任何需要读取 Excel 文件的问题
- 跨月数据对比、趋势分析

【严格规则——违反将导致无限循环】
1. 只做判断和转发，最多做两次转发
2. 达到两次转发后，即使 Agent 返回的是"未找到相关内容"或"建议联系部门确认"，也必须原样返回
3. 禁止对 Agent 的回答进行二次总结、改写或压缩
4. 禁止在 Agent 回答之外添加任何补充说明
""",
    checkpointer=checkpointer,
).compile()


# ── 对话上下文记忆（从 SQLite 读取历史消息注入） ────
# 双重保险：SqliteSaver 负责 LangGraph 内部状态持久化，
#          本函数负责在 Streamlit rerun 导致内存重建时手动恢复上下文。

def _parse_conversation_id(thread_id: str) -> int | None:
    """从 thread_id 中解析 conversation_id。格式：conversation-{数字}"""
    match = re.match(r"^conversation-(\d+)$", thread_id)
    if match:
        return int(match.group(1))
    return None


def _build_messages_with_history(user_input: str, thread_id: str, user_id: int = None) -> list:
    """
    构建包含完整历史上下文的消息列表。
    
    原理：从 SQLite 读取持久化的对话记录，手动构建完整的消息列表，
    确保多轮对话的上下文连续性。
    
    即使 SqliteSaver 已提供持久化 checkpoint，本函数仍作为双重保险：
    Streamlit rerun 导致 Python 模块重载时，内存中的 SqliteSaver 连接
    可能与新实例不同，而直接读 SQLite 消息表是最可靠的方式。
    """
    conv_id = _parse_conversation_id(thread_id)
    
    if not conv_id or not user_id:
        # 无法解析 conversation_id 或没有 user_id，退回单条消息
        return [HumanMessage(content=user_input)]
    
    from data.conversation_service import get_messages
    history = get_messages(conv_id, user_id)  # ✅ 必须传 user_id
    
    if not history or len(history) <= 1:
        # 无历史或只有当前这条消息（新建对话的第一轮），直接发送
        return [HumanMessage(content=user_input)]
    
    # 从历史消息构建 LangChain Message 列表
    # 注意：history 末尾是当前用户刚保存的消息，需要排除以避免重复
    messages = []
    for msg in history[:-1]:  # 排除最后一条（当前用户输入，下面单独追加）
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            # 语义降权：历史回复中的数据和结论是基于当时的查询结果，
            # 不代表当前文件状态，避免 LLM 把旧结论当作已验证事实
            tagged = f"[历史回复，其中的数据和结论为当时查询结果，不代表当前真实状态]{msg['content']}"
            messages.append(AIMessage(content=tagged))
    
    # 追加当前用户输入
    messages.append(HumanMessage(content=user_input))
    
    print(f"[ContextMemory] thread_id={thread_id}, user_id={user_id}, "
          f"加载 {len(history)-1} 条历史消息, 总计 {len(messages)} 条")
    
    return messages


def chat_direct(
    agent_name: str,
    user_input: str,
    thread_id: str = "default",
    user_context: dict = None,
    username: str = "unknown",
) -> tuple[str, list, str]:
    """
    直接调用指定子智能体，不使用 Router 自动路由分发。

    Args:
        agent_name: "rag_agent" 或 "data_agent"
        user_input: 用户输入的问题
        thread_id: 对话线程 ID（支持多轮对话记忆）
        user_context: 用户上下文 {user_id, username, role}
        username: 用户名（用于 Tracing 分组）

    Returns:
        (final_answer, steps_log, agent_used)
    """
    from langchain_core.messages import AIMessage, ToolMessage

    # ── 规则检查 ──
    try:
        check_user_input(user_input)
    except RuleViolationError as e:
        return f"⚠️ 输入安全检查未通过：{e}", [], None

    agent_map = {"rag_agent": rag_agent, "data_agent": data_agent, "doc_agent": doc_agent}
    agent = agent_map.get(agent_name)
    if agent is None:
        return f"未知智能体：{agent_name}", [], None

    # 用户名优先级
    trace_username = "unknown"
    if user_context and isinstance(user_context, dict):
        trace_username = user_context.get("username", trace_username)
    else:
        trace_username = username

    metadata = {
        "user_id": trace_username,
        "conversation_id": thread_id,
    }

    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 50,
        "metadata": metadata,
    }

    steps_log = []
    seen_tools = set()
    all_messages = []
    final_answer = ""

    # ── 构建消息：注入历史上下文 ──
    _uid = (user_context.get("user_id") if isinstance(user_context, dict) else None)
    messages_with_history = _build_messages_with_history(user_input, thread_id, _uid)
    state_input = {"messages": messages_with_history}
    if user_context:
        state_input["user_context"] = user_context

    try:
        for chunk in agent.stream(state_input, config=config, stream_mode="updates"):
            for node_name, node_data in chunk.items():
                for msg in node_data.get("messages", []):
                    all_messages.append(msg)

                    # 记录工具调用
                    if hasattr(msg, "tool_calls") and msg.tool_calls:
                        for tc in msg.tool_calls:
                            tool_key = tc["id"]
                            if tool_key not in seen_tools:
                                seen_tools.add(tool_key)
                                steps_log.append(f"🔧 调用工具：**{tc['name']}**")
                                if tc.get("args"):
                                    for k, v in tc["args"].items():
                                        steps_log.append(f"&nbsp;&nbsp;&nbsp;参数 {k}：{v}")

                    # 记录工具返回
                    if getattr(msg, "name", None):
                        tool_key = f"{msg.name}_{str(msg.content)[:20]}"
                        if tool_key not in seen_tools:
                            seen_tools.add(tool_key)
                            preview = str(msg.content)[:80]
                            steps_log.append(f"✅ 工具返回：{preview}...")
    except Exception as e:
        # 流式过程中发生连接错误：如果已收集到有效答案则直接返回，避免前功尽弃
        err_str = str(e)
        is_connection_err = (
            "APIConnectionError" in err_str or "Connection error" in err_str
            or "RemoteProtocolError" in err_str or "Server disconnected" in err_str
        )
        if not is_connection_err:
            raise

    # 提取最终答案（优先从工具返回中获取，其次取最后一个 AIMessage）
    for msg in reversed(all_messages):
        if (
            isinstance(msg, ToolMessage)
            and msg.content
            and getattr(msg, "name", "").startswith("generate_document")
        ):
            final_answer = str(msg.content)
            break
    if not final_answer:
        for msg in reversed(all_messages):
            if isinstance(msg, AIMessage) and msg.content and not getattr(msg, "tool_calls", None):
                final_answer = msg.content
                break

    if not final_answer:
        final_answer = "智能体未返回有效回答，请重试。"

    return final_answer, steps_log, agent_name


def chat(
    user_input: str,
    thread_id: str = "default",
    user_context: dict = None,
    username: str = "unknown",
) -> tuple[str, list, str]:
    """
    调用智能体进行对话。

    Args:
        user_input: 用户输入的问题
        thread_id: 对话线程 ID（支持多轮对话记忆）
        user_context: 用户上下文 {user_id, username, role}，供 Router 和 Agent 感知用户身份
        username: 用户名（用于 LangSmith Tracing 分组，优先级低于 user_context 中的 username）

    Returns:
        (final_answer, steps_log, agent_used)
        agent_used: 实际处理问题的智能体名称，如 "rag_agent" / "data_agent" / None
    """
    # 优先从 user_context 提取用户名，其次使用 username 参数
    trace_username = "unknown"
    if user_context and isinstance(user_context, dict):
        trace_username = user_context.get("username", trace_username)
    else:
        trace_username = username

    # ── 规则检查：用户输入安全校验 ─────────────────
    try:
        check_user_input(user_input)
    except RuleViolationError as e:
        return f"⚠️ 输入安全检查未通过：{e}", [], None

    # 构建 LangSmith 元数据（用于 Trace 分组和筛选）
    metadata = {
        "user_id": trace_username,           # 对应登录用户名，便于按用户筛选
        "conversation_id": thread_id,  # 对应 conversation_id，便于按对话聚合
    }

    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 50,
        "metadata": metadata,  # 注入 LangSmith tracing metadata
    }
    from langchain_core.messages import AIMessage

    steps_log = []
    seen_tools = set()
    all_messages = []      # 收集 stream 过程中的所有消息
    agent_used = None

    # ── 构建消息：注入历史上下文（替代 MemorySaver 不可靠的运行时记忆） ──
    _uid = (user_context.get("user_id") if isinstance(user_context, dict) else None)
    messages_with_history = _build_messages_with_history(user_input, thread_id, _uid)
    state_input = {"messages": messages_with_history}
    if user_context:
        state_input["user_context"] = user_context

    # 单次 stream：同时收集步骤日志 + 所有消息（用于提取最终答案）
    for chunk in router.stream(
        state_input,
        config=config,
        stream_mode="updates"
    ):
        for node_name, node_data in chunk.items():
            for msg in node_data.get("messages", []):
                all_messages.append(msg)

                # 记录工具调用（用 tool_call id 去重）
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    for tc in msg.tool_calls:
                        if tc["name"].startswith("transfer"):
                            continue
                        tool_key = tc["id"]
                        if tool_key not in seen_tools:
                            seen_tools.add(tool_key)
                            steps_log.append(f"🔧 调用工具：**{tc['name']}**")
                            if tc.get("args"):
                                for k, v in tc["args"].items():
                                    steps_log.append(f"&nbsp;&nbsp;&nbsp;参数 {k}：{v}")

                # 记录工具返回（用 name 去重）
                if getattr(msg, "name", None):
                    if msg.name.startswith("transfer"):
                        continue
                    tool_key = f"{msg.name}_{str(msg.content)[:20]}"
                    if tool_key not in seen_tools:
                        seen_tools.add(tool_key)
                        preview = str(msg.content)[:80]
                        steps_log.append(f"✅ 工具返回：{preview}...")

    # 从收集到的消息中提取最终答案
    final_answer = ""
    for msg in reversed(all_messages):
        if (
            isinstance(msg, AIMessage)
            and msg.content
            and not getattr(msg, "tool_calls", None)
            and getattr(msg, "name", None) in ("rag_agent", "data_agent", "doc_agent")
            and not str(msg.content).startswith("Transferring")
        ):
            final_answer = msg.content
            agent_used = getattr(msg, "name", None)
            break

    # 兜底：如果 sub-agent 没找到，取 supervisor 的最终回答
    if not final_answer:
        for msg in reversed(all_messages):
            if (
                isinstance(msg, AIMessage)
                and msg.content
                and not getattr(msg, "tool_calls", None)
                and getattr(msg, "name", None) == "supervisor"
            ):
                final_answer = msg.content
                break

    return final_answer, steps_log, agent_used