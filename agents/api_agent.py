# agents/api_agent.py
"""
真实数据接口智能体 — 从 data_interface/ 目录加载 OpenAPI 3.0 规范文件，
提供动态接口发现与实时调用能力。
"""
import json
import os
import requests
from pathlib import Path
from datetime import datetime
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

# ── 路径 & HTTP Session ──────────────────────────────
_DATA_INTERFACE_DIR = Path(__file__).parent.parent / "data_interface"
_http_session = requests.Session()

# ── 认证 Token（从环境变量读取）───────────────────────
# 如果真实接口需要 Bearer Token 认证，在 .env 中配置 REAL_API_TOKEN
_REAL_API_TOKEN = os.getenv("REAL_API_TOKEN", "")


# ══════════════════════════════════════════════════════
#  解析引擎：将 OpenAPI 3.0 规范转为内部 API 列表
# ══════════════════════════════════════════════════════

def _load_all_specs() -> list[dict]:
    """递归加载 data_interface/ 下所有 OpenAPI JSON 文件。"""
    specs = []
    if not _DATA_INTERFACE_DIR.exists():
        return specs
    for json_file in sorted(_DATA_INTERFACE_DIR.rglob("*.json")):
        try:
            spec = json.loads(json_file.read_text(encoding="utf-8"))
            if "openapi" in spec and "paths" in spec:
                specs.append(spec)
        except Exception as e:
            print(f"[api_agent] 跳过无法解析的文件 {json_file}: {e}")
    return specs


def _parse_apis_from_specs(specs: list[dict]) -> list[dict]:
    """
    将 OpenAPI 3.0 规范列表解析为扁平的接口描述列表。
    每个接口包含足够 LLM 调用的元信息。
    自动处理重复的 operationId（追加 tag 名或序号区分）。
    """
    apis = []
    used_ids = set()

    def _make_unique_id(raw_id: str, tags: list[str]) -> str:
        """生成全局唯一的 operation ID。"""
        if raw_id not in used_ids:
            used_ids.add(raw_id)
            return raw_id
        # 尝试加 tag 后缀
        tag_suffix = tags[0] if tags else ""
        if tag_suffix:
            candidate = f"{raw_id}_{tag_suffix}"
            if candidate not in used_ids:
                used_ids.add(candidate)
                return candidate
        # 同一 tag 下仍有重复，加递增序号
        idx = 1
        while True:
            candidate = f"{raw_id}_{idx}"
            if candidate not in used_ids:
                used_ids.add(candidate)
                return candidate
            idx += 1

    for spec in specs:
        service_name = spec.get("info", {}).get("title", "未命名服务")
        server_url = (spec.get("servers", [{}])[0].get("url", "") or "").rstrip("/")
        has_auth = bool(spec.get("components", {}).get("securitySchemes", {}))

        for path, path_item in spec.get("paths", {}).items():
            for method in ("get", "post", "put", "delete", "patch"):
                operation = path_item.get(method)
                if not operation:
                    continue

                # 提取参数（path / query / header）
                params = []
                for p in operation.get("parameters", []):
                    params.append({
                        "name": p.get("name", ""),
                        "in": p.get("in", "query"),
                        "required": p.get("required", False),
                        "description": p.get("description", ""),
                        "schema": p.get("schema", {}),
                    })

                # 提取 requestBody 信息（POST / PUT 场景）
                rb = operation.get("requestBody")
                has_body = rb is not None if rb else False
                body_content_type = None
                body_schema = None
                if rb and rb.get("content"):
                    content_types = list(rb["content"].keys())
                    body_content_type = content_types[0] if content_types else None
                    if body_content_type:
                        body_schema = rb["content"][body_content_type].get("schema", {})

                raw_id = operation.get("operationId", f"{method}:{path}")
                tags = operation.get("tags", [])
                api_id = _make_unique_id(raw_id, tags)

                api_info = {
                    "id": api_id,
                    "service": service_name,
                    "summary": operation.get("summary", "") or path,
                    "description": operation.get("description", "") or "",
                    "method": method.upper(),
                    "path": path,
                    "full_url": f"{server_url}{path}",
                    "tags": tags,
                    "params": params,
                    "has_body": has_body,
                    "body_content_type": body_content_type,
                    "body_schema": body_schema,
                    "deprecated": operation.get("deprecated", False),
                    "auth_required": has_auth,
                }
                apis.append(api_info)
    return apis


# ══════════════════════════════════════════════════════
#  工具：接口列表 & 调用
# ══════════════════════════════════════════════════════

def _build_api_list_summary(apis: list[dict]) -> str:
    """生成按服务分组的接口摘要（用于无关键词时的概览）。"""
    from collections import defaultdict
    grouped = defaultdict(list)
    for api in apis:
        grouped[api["service"]].append(api)

    lines = [f"当前可用接口总数：{len(apis)} 个，分布如下：\n"]
    for service, svc_apis in sorted(grouped.items()):
        methods = defaultdict(int)
        for a in svc_apis:
            methods[a["method"]] += 1
        method_str = ", ".join(f"{m}×{c}" for m, c in sorted(methods.items()))
        lines.append(f"  【{service}】共 {len(svc_apis)} 个接口（{method_str}）")
    lines.append("\n请使用关键词（如「建筑」「车辆」「消息」）搜索具体接口，再调用 call_real_api 获取数据。")
    return "\n".join(lines)


def _format_api_detail(api: dict) -> str:
    """格式化单个接口的详细信息。"""
    params_desc = []
    for p in api["params"]:
        required = "必填" if p["required"] else "可选"
        desc = p.get("description", "")
        schema_type = p.get("schema", {}).get("type", "")
        type_info = f" [{schema_type}]" if schema_type else ""
        params_desc.append(f"    {p['name']} ({p['in']}, {required}{type_info}): {desc}")
    params_block = "\n".join(params_desc) if params_desc else "    （无参数）"

    body_info = ""
    if api["has_body"]:
        body_info = f"\n  请求体: {api.get('body_content_type', '')}"

    tags_str = f" [{', '.join(api['tags'])}]" if api['tags'] else ""
    auth_str = " [需要认证]" if api['auth_required'] else ""

    return (
        f"【{api['service']}】{api['summary']}{tags_str}{auth_str}\n"
        f"  操作ID: {api['id']}\n"
        f"  方法: {api['method']} {api['full_url']}\n"
        f"  参数:\n{params_block}{body_info}"
    )


def create_api_agent(llm):
    # ── 预加载所有真实接口 ──────────────────────────
    specs = _load_all_specs()
    apis = _parse_apis_from_specs(specs)
    api_map = {api["id"]: api for api in apis}

    print(f"[api_agent] 已加载 {len(specs)} 个 OpenAPI 规范，共 {len(apis)} 个接口")

    @tool
    def list_available_apis(keyword: str = "") -> str:
        """
        列出所有可用的真实数据接口。

        无关键词时返回按服务分组的接口概览。

        参数:
          keyword - 可选，按接口名称/描述/路径/标签搜索。
                    例如："建筑"、"车辆"、"消防"、"消息"、"地图"、"值班"
        """
        if not apis:
            return (
                "当前没有加载任何真实接口配置。\n"
                "请确认 data_interface/ 目录下有 OpenAPI 3.0 JSON 文件。\n"
                f"当前路径：{_DATA_INTERFACE_DIR.resolve()}"
            )

        if not keyword:
            return _build_api_list_summary(apis)

        kw = keyword.lower()
        filtered = [
            a for a in apis
            if kw in a["summary"].lower()
            or kw in a["description"].lower()
            or kw in a["service"].lower()
            or any(kw in t.lower() for t in a["tags"])
            or kw in a["path"].lower()
            or kw in a["id"].lower()
        ]

        if not filtered:
            return (
                f"未找到与「{keyword}」相关的接口（共 {len(apis)} 个可用接口）。\n"
                "请尝试其他关键词，或不带关键词调用 list_available_apis 查看完整概览。"
            )

        lines = [f"匹配接口（共 {len(filtered)} 个 / 总计 {len(apis)} 个）：\n"]
        for api in filtered:
            lines.append(_format_api_detail(api))
        return "\n\n".join(lines)

    @tool
    def call_real_api(
        operation_id: str,
        query_params: str = "",
        path_params: str = "",
        body: str = "",
    ) -> str:
        """
        调用真实数据接口获取实时数据。

        必须先调用 list_available_apis 获取可用的 operation_id。

        参数:
          operation_id - 接口操作ID（从 list_available_apis 返回结果中获取）
          query_params - 查询参数，JSON 字符串。
                         如 '{"current": 1, "size": 10, "title": "报警"}'
          path_params  - 路径参数，JSON 字符串。
                         如 '{"userId": "123", "messageId": "456"}'
          body         - 请求体，JSON 字符串。
                         仅 POST/PUT 请求使用，如 '{"title": "测试", "content": "..."}'
        """
        if operation_id not in api_map:
            # 尝试模糊匹配
            similar = [k for k in api_map if operation_id.lower() in k.lower()]
            hint = ""
            if similar:
                hint = f"\n可能的匹配：{', '.join(similar[:5])}"
            return (
                f"未找到接口 operation_id='{operation_id}'。{hint}\n"
                "请先调用 list_available_apis 获取可用接口列表。"
            )

        api = api_map[operation_id]
        method = api["method"]
        url = api["full_url"]

        # ── 处理路径参数：替换 URL 中的 {xxx} 占位符 ──
        if path_params:
            try:
                path_values = json.loads(path_params)
            except Exception:
                return f"path_params 格式错误，请使用 JSON 字符串：{path_params}"
            for key, value in path_values.items():
                url = url.replace(f"{{{key}}}", str(value))

        # ── 处理查询参数 ──
        params = {}
        if query_params:
            try:
                params = json.loads(query_params)
            except Exception:
                return f"query_params 格式错误，请使用 JSON 字符串：{query_params}"

        # ── 处理请求体 ──
        json_body = None
        form_body = None
        if body and method in ("POST", "PUT", "PATCH"):
            content_type = api.get("body_content_type", "")
            if "json" in content_type or not content_type:
                try:
                    json_body = json.loads(body)
                except Exception:
                    return f"请求体格式错误，请使用 JSON 字符串：{body}"
            elif "form" in content_type:
                try:
                    form_body = json.loads(body)
                except Exception:
                    return f"请求体格式错误，请使用 JSON 字符串：{body}"

        # ── 请求头 ──
        headers = {}
        if api["auth_required"] and _REAL_API_TOKEN:
            headers["Authorization"] = f"Bearer {_REAL_API_TOKEN}"
        elif api["auth_required"]:
            print("[api_agent] 警告：接口需要认证但未配置 REAL_API_TOKEN")

        if json_body is not None:
            headers["Content-Type"] = "application/json"

        # ── 发起请求 ──
        try:
            if method == "GET":
                resp = _http_session.get(url, params=params, headers=headers, timeout=30)
            elif method == "DELETE":
                resp = _http_session.delete(url, params=params, headers=headers, timeout=30)
            elif method in ("POST", "PUT", "PATCH"):
                if json_body is not None:
                    resp = _http_session.request(method, url, params=params, json=json_body, headers=headers, timeout=30)
                elif form_body is not None:
                    resp = _http_session.request(method, url, params=params, data=form_body, headers=headers, timeout=30)
                else:
                    resp = _http_session.request(method, url, params=params, headers=headers, timeout=30)
            else:
                return f"不支持的 HTTP 方法：{method}"

            if resp.status_code >= 400:
                return f"接口返回错误 HTTP {resp.status_code}：\n{resp.text[:500]}"

            try:
                result = resp.json()
                return json.dumps(result, ensure_ascii=False, indent=2)
            except Exception:
                return resp.text[:3000]

        except requests.exceptions.ConnectionError:
            return f"无法连接到 {url}，请确认目标服务已启动。"
        except requests.exceptions.Timeout:
            return f"请求超时（30秒）：{url}"
        except Exception as e:
            return f"接口调用异常：{e}"

    return create_react_agent(
        model=llm,
        name="api_agent",
        tools=[list_available_apis, call_real_api],
        prompt=f"""你是企业数据接口助手，通过调用公司内部 HTTP 接口获取实时业务数据并回答问题。

【当前时间】（服务器实时时间，用户口中的"今天/昨日/本周"以此为准）
- 今天是: {datetime.now().strftime("%Y-%m-%d %A")}
⚠️ 严禁自行推测日期；当用户提到"今天/昨天/本周"等相对时间时，必须按上方"今天"换算为具体 yyyy-MM-dd。

【工作流程】
1. 调用 list_available_apis 查看所有可用接口（支持关键词搜索）
2. 根据用户问题匹配最相关的接口
3. 调用 call_real_api 获取数据，按接口参数说明传递正确的 query_params 和 body
4. 将接口返回数据整理为清晰的中文回答

【参数规则】
- query_params / path_params / body 均为 JSON 字符串
- 必填参数必须提供，可选参数按需提供
- 日期格式参考接口参数中的 format 说明（如 yyyy-MM-dd HH:mm:ss）
- 路径参数用 path_params 传入，会被替换到 URL 的 {{xxx}} 占位符中

【回答规则】
- 数据来自接口实时返回，如实呈现，不编造
- 接口连接失败或返回空数据时，如实告知并建议检查服务状态
- 无匹配接口时，明确告知用户哪些接口可用
- 可同时调用多个接口，综合数据回答复杂问题
- 数据用表格或列表呈现，清晰易读
- 回答语言：中文""",
    )
