from agent import chat

print("企业知识库智能体已启动，输入 exit 退出\n")

thread_id = "test-session-001"
while True:
    user_input = input("你：").strip()
    if user_input.lower() == "exit":
        break
    if not user_input:
        continue
    response, _, _ = chat(
        user_input=user_input,
        thread_id=thread_id,
        username="cli-user",         # CLI 模式固定值，用于 LangSmith tracing
    )
    print(f"\n助手：{response}\n")