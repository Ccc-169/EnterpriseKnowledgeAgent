# agents/registry.py — Agent 注册与权限声明，预留扩展点

AGENT_REGISTRY = {
    "rag_agent": {
        "name": "RAG 知识库智能体",
        "description": "文档检索、内容问答、知识库查询",
        "required_role": ["user", "admin"],   # visitor 不可用
        "enabled": True,
    },
    "data_agent": {
        "name": "Data 数据分析智能体",
        "description": "统计分析、Excel处理、代码生成",
        "required_role": ["user", "admin"],
        "enabled": True,
    },
    "doc_agent": {
        "name": "Doc 文档编写智能体",
        "description": "文档生成、报告撰写、方案编写",
        "required_role": ["user", "admin"],
        "enabled": True,
    },
    "api_agent": {
        "name": "API 接口查询智能体",
        "description": "调用 data_interface/ 下 OpenAPI 规范对应的真实 HTTP 接口，获取实时业务数据",
        "required_role": ["user", "admin"],
        "enabled": True,
    },
    # 未来扩展示例（不需要修改 agent.py）：
    # "report_agent": {
    #     "name": "Report 报告生成智能体",
    #     "description": "自动生成分析报告",
    #     "required_role": ["admin"],
    #     "enabled": False,
    # },
}


def get_agent_info(agent_name: str) -> dict:
    """获取 Agent 配置信息，不存在返回 None。"""
    return AGENT_REGISTRY.get(agent_name)


def can_use_agent(agent_name: str, role: str) -> bool:
    """检查该角色是否可使用某 Agent。"""
    info = AGENT_REGISTRY.get(agent_name)
    if info is None:
        return False
    if not info["enabled"]:
        return False
    return role in info["required_role"]


def list_enabled_agents() -> list[str]:
    """返回所有启用的 Agent 名称列表。"""
    return [name for name, info in AGENT_REGISTRY.items() if info["enabled"]]
