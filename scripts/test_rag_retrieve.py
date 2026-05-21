"""
测试脚本：验证 RAG 检索改进效果

使用方法：
1. 确保已激活虚拟环境
2. 确保 .env 文件中的 DIFY_API_KEY 和 DIFY_KB_ID 已正确配置
3. 运行：python scripts/test_rag_retrieve.py
"""

import os
import sys
import django

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 加载 .env 文件
from dotenv import load_dotenv
load_dotenv()

# 测试问题列表
TEST_QUESTIONS = [
    "公司的核心价值观是什么",
    "公司核心优势",
    "告诉我公司的基本信息",
    "年假怎么算",
    "迟到扣多少钱",
]


def test_rag_search():
    """测试 rag_search 函数的改进效果"""
    from agents.rag_agent import create_rag_agent
    from langchain_openai import ChatOpenAI
    
    # 初始化 LLM（使用与项目相同的配置）
    llm = ChatOpenAI(
        model=os.environ.get("QWEN_MODEL", "qwen-plus"),
        api_key=os.environ.get("QWEN_API_KEY"),
        base_url=os.environ.get("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    )
    
    # 创建 RAG agent
    rag_agent = create_rag_agent(llm)
    
    # 测试每个问题
    for question in TEST_QUESTIONS:
        print("\n" + "="*60)
        print(f"测试问题：{question}")
        print("="*60)
        
        # 调用 RAG agent（React Agent 使用标准 messages 接口）
        result = rag_agent.invoke({
            "messages": [("user", question)],
        })
        
        # 从消息列表中提取最终答案
        answer = ""
        for msg in reversed(result.get("messages", [])):
            if hasattr(msg, "content") and msg.content and not getattr(msg, "tool_calls", None):
                answer = msg.content
                break
        print(f"\n答案：\n{answer}\n")


if __name__ == "__main__":
    try:
        test_rag_search()
    except Exception as e:
        print(f"测试失败：{e}")
        import traceback
        traceback.print_exc()
