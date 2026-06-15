from langsmith import Client
import os
from dotenv import load_dotenv
from datetime import datetime  # 必须添加这行导入
load_dotenv()


client = Client(api_key=os.environ["LANGCHAIN_API_KEY"])
# 填入你截图中的 Run ID (通常在 URL 中可以看到)
run_id = "019ec633-8b45-73d1-9d96-65fa675c07de" 

def get_full_trace(run_id):
    # 获取当前节点
    run = client.read_run(run_id)
    # 尝试获取该节点的所有子节点
    children = client.list_runs(parent_run_id=run_id)

    # 修改为：
    if hasattr(run, 'model_dump'):
        run_data = run.model_dump()
    else:
        run_data = run.dict()
    run_data['child_runs'] = [get_full_trace(child.id) for child in children]
    return run_data

# 导出为 JSON
import json
full_trace = get_full_trace(run_id)
from uuid import UUID

def json_serializable(obj):
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()  # 将日期时间对象转换为 ISO 字符串
    # 如果仍然报错，可以返回对象的字符串表示，防止脚本中断
    return str(obj)

# 导出时使用 default 参数
# 导出逻辑
with open('trace_export.json', 'w', encoding='utf-8') as f:
    json.dump(full_trace, f, indent=2, ensure_ascii=False, default=json_serializable)