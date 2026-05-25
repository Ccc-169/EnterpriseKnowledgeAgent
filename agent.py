# agent.py
import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph_supervisor import create_supervisor
from langgraph.checkpoint.memory import MemorySaver
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

# ── Router：只做分发，不干具体活 ──────────────────────
memory = MemorySaver()

router = create_supervisor(
    agents=[rag_agent, data_agent, doc_agent],
    model=llm,
    prompt="""
    你是任务路由器，只做一件事：
判断问题类型，转发给对应 Agent，然后将 Agent 的回答原样返回。
禁止修改、总结、补充 Agent 的任何回答内容。

转发给 rag_agent 的情况：
- 对文档内容提问（公司制度、规定、政策、员工手册）
- 总结文档、仿写内容
- 查询知识库里有哪些文档
- 公司背景、业务介绍等知识性问题

转发给 data_agent 的情况：
- 统计、排名、汇总、计算
- 出勤率、迟到次数、工作时长等考勤数据分析
- 任何需要读取 Excel 文件的问题
- 跨月数据对比、趋势分析

转发给 doc_agent 的情况：
- 编写文档、报告、方案、手册、规章制度
- 生成文档目录/大纲
- 撰写工作总结、汇报材料
- 文档格式排版、内容扩写

【严格规则】
1. 只做判断和转发，不自己回答问题
2. 收到 Agent 返回的结果后，必须将完整内容原封不动返回给用户
3. 禁止对 Agent 的回答进行二次总结、改写或压缩
4. 禁止在 Agent 回答之外添加任何补充说明
""",
    checkpointer=memory,
).compile()


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
    from langchain_core.messages import AIMessage

    # ── 规则检查 ──
    try:
        check_user_input(user_input)
    except RuleViolationError as e:
        return f"⚠️ 输入安全检查未通过：{e}", [], None

    agent_map = {"rag_agent": rag_agent, "data_agent": data_agent}
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

    state_input = {"messages": [{"role": "user", "content": user_input}]}
    if user_context:
        state_input["user_context"] = user_context

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

    # 提取最终答案
    final_answer = ""
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

    # 构建消息，注入 user_context
    state_input = {"messages": [{"role": "user", "content": user_input}]}
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