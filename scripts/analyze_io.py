import json
from datetime import datetime

data = json.load(open('d:/WorkProject/EnterpriseKnowledgeAgent/trace_export.json', encoding='utf-8'))

# 提取根节点 inputs / outputs 的 messages
inp = data.get('inputs', {})
out = data.get('outputs', {})

print('=' * 80)
print('【根节点 Inputs】')
print('=' * 80)
print('user_context:', inp.get('user_context'))
print()
print('messages count:', len(inp.get('messages', [])))
for i, m in enumerate(inp.get('messages', [])):
    print()
    print('--- input msg[{}] type={} id={} ---'.format(i, m.get('type'), m.get('id')))
    content = m.get('content', '')
    if isinstance(content, str):
        if len(content) > 600:
            print(content[:600] + '... [+{} chars]'.format(len(content) - 600))
        else:
            print(content)
    else:
        print(repr(content)[:600])
    if m.get('tool_calls'):
        print('tool_calls:', m.get('tool_calls'))

print()
print('=' * 80)
print('【根节点 Outputs】')
print('=' * 80)
print('messages count:', len(out.get('messages', [])))
for i, m in enumerate(out.get('messages', [])):
    print()
    print('--- output msg[{}] type={} id={} ---'.format(i, m.get('type'), m.get('id')))
    content = m.get('content', '')
    if isinstance(content, str):
        if len(content) > 1200:
            print(content[:1200] + '... [+{} chars]'.format(len(content) - 1200))
        else:
            print(content)
    else:
        print(repr(content)[:1200])
    if m.get('tool_calls'):
        for tc in m['tool_calls']:
            print('tool_call:', tc.get('name'), 'args keys:', list((tc.get('args') or {}).keys()) if isinstance(tc.get('args'), dict) else None)
            print('  id:', tc.get('id'))
