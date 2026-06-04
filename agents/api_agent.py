# agents/api_agent.py
import json
import requests
from pathlib import Path
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

_IFACE_CONFIGS_PATH = Path(__file__).parent.parent / "project_documents" / "interface_configs.json"
_http_session = requests.Session()


def _load_configs() -> dict:
    if not _IFACE_CONFIGS_PATH.exists():
        return {"groups": [], "interfaces": []}
    try:
        return json.loads(_IFACE_CONFIGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"groups": [], "interfaces": []}


def create_api_agent(llm):

    @tool
    def list_interfaces() -> str:
        """
        列出所有已启用的接口，包含接口ID、名称、HTTP方法、URL 和默认参数。
        调用 call_interface 前必须先调用此工具，了解可用接口。
        """
        configs = _load_configs()
        groups = {g["id"]: g["name"] for g in configs.get("groups", [])}
        interfaces = [i for i in configs.get("interfaces", []) if i.get("enabled", False)]

        if not interfaces:
            return "当前没有已启用的接口。请先在「接口配置」页面添加并启用接口。"

        lines = [f"已启用接口（共 {len(interfaces)} 个）：\n"]
        for iface in interfaces:
            group_name = groups.get(iface.get("groupId", ""), "未分组")
            all_params = iface.get("params", [])
            param_lines = []
            for p in all_params:
                tag = "默认" if p.get("enabled", False) else "可选"
                desc = f"  # {p['desc']}" if p.get("desc") else ""
                param_lines.append(f"    {p['key']} = {p.get('value', '')}  [{tag}]{desc}")
            params_block = "\n".join(param_lines) if param_lines else "    （无参数）"
            lines.append(
                f"【{group_name}】{iface['name']}\n"
                f"  ID  : {iface['id']}\n"
                f"  方法: {iface.get('method', 'GET')} {iface['url']}\n"
                f"  参数:\n{params_block}"
            )
        return "\n\n".join(lines)

    @tool
    def call_interface(interface_id: str, extra_params: str = "") -> str:
        """
        按接口 ID 调用接口，自动携带配置中已启用的默认参数。

        参数：
          interface_id  - 接口 ID（从 list_interfaces 获取）
          extra_params  - 额外或覆盖的参数，JSON 字符串，如 '{"level": "2", "area": "B区"}'
                          GET 请求追加到 query params，POST 请求合并到 request body
        """
        configs = _load_configs()
        iface = next(
            (i for i in configs.get("interfaces", [])
             if i.get("id") == interface_id and i.get("enabled", False)),
            None,
        )
        if iface is None:
            return f"未找到已启用的接口 ID='{interface_id}'，请先调用 list_interfaces 确认可用接口。"

        method = iface.get("method", "GET").upper()
        url = iface["url"]

        # 接口配置中已启用的默认参数
        default_params = {
            p["key"]: p["value"]
            for p in iface.get("params", [])
            if p.get("enabled", False)
        }

        # 合并 extra_params（覆盖同名默认值）
        if extra_params:
            try:
                default_params.update(json.loads(extra_params))
            except Exception:
                return f"extra_params 格式错误，请使用 JSON 字符串：{extra_params}"

        # 请求头（接口配置中的自定义 headers）
        headers = {
            h["key"]: h["value"]
            for h in iface.get("headers", [])
            if h.get("enabled", True)
        }

        # 认证
        auth_type = iface.get("authType", "none")
        auth_value = iface.get("authValue", "")
        if auth_type == "bearer" and auth_value:
            headers["Authorization"] = f"Bearer {auth_value}"
        elif auth_type == "apikey" and auth_value:
            headers[iface.get("authKeyName", "X-API-Key")] = auth_value

        try:
            body_type = iface.get("bodyType", "none")

            if method == "GET":
                resp = _http_session.get(url, params=default_params, headers=headers, timeout=15)

            elif method in ("POST", "PUT", "PATCH"):
                if body_type == "json":
                    try:
                        body = json.loads(iface.get("body", "{}") or "{}")
                    except Exception:
                        body = {}
                    body.update(default_params)
                    headers.setdefault("Content-Type", "application/json")
                    resp = _http_session.request(method, url, json=body, headers=headers, timeout=15)
                else:
                    resp = _http_session.request(method, url, params=default_params, headers=headers, timeout=15)

            elif method == "DELETE":
                resp = _http_session.delete(url, params=default_params, headers=headers, timeout=15)

            else:
                return f"不支持的 HTTP 方法：{method}"

            if resp.status_code >= 400:
                return f"接口返回错误 HTTP {resp.status_code}：{resp.text[:300]}"

            try:
                return json.dumps(resp.json(), ensure_ascii=False, indent=2)
            except Exception:
                return resp.text[:2000]

        except requests.exceptions.ConnectionError:
            return f"无法连接到 {url}，请确认服务已启动。"
        except requests.exceptions.Timeout:
            return f"请求超时（15秒）：{url}"
        except Exception as e:
            return f"接口调用异常：{e}"

    return create_react_agent(
        model=llm,
        name="api_agent",
        tools=[list_interfaces, call_interface],
        prompt="""你是企业接口数据助手，通过调用已配置的 HTTP 接口获取实时数据并回答问题。

【工作流程】
1. 调用 list_interfaces 查看所有可用接口及默认参数
2. 根据用户问题匹配最相关的接口（可同时匹配多个）
3. 调用 call_interface 获取数据，需要时通过 extra_params 覆盖默认参数
4. 将接口返回数据整理为清晰的中文回答

【回答规则】
- 数据来自接口实时返回，如实呈现，不编造
- 接口连接失败或数据为空时，如实告知并建议检查服务状态或接口配置
- 无匹配接口时，明确告知用户需要在「接口配置」页面添加对应接口
- 可同时调用多个接口，综合数据回答复杂问题

【回答语言】中文，数据用表格或列表呈现，清晰易读。""",
    )
