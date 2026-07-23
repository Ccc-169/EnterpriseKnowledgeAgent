import requests
r = requests.post('http://192.168.1.155:11434/v1/chat/completions',
    json={'model':'qwen3.6:35b','messages':[{'role':'user','content':'hi'}],
          'parallel_tool_calls':False,'max_tokens':5},
    headers={'Authorization':'Bearer ollama'}, timeout=20)
print(r.status_code, r.text[:200])