# data/interface_service.py — 系统接口索引、导入、删除与权限管理服务
"""
混合存储架构：
  1. 文件层（Source of Truth）：data_interface/ 下的 JSON 文件
  2. 数据库索引层：data_interfaces 表 — 运行时快速查询
  3. 权限层：user_interface_access 表 — 细粒度接口权限控制

启动时自动扫描 data_interface/ 目录并同步到数据库索引。
"""
import json
import os
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional

import requests
from core.database import get_db

# ── 常量 ───────────────────────────────────────────────
_DATA_INTERFACE_DIR = Path(__file__).parent.parent / "data_interface"

# 常见的 OpenAPI 端点探测顺序
_STANDARD_SWAGGER_PATHS = [
    "/v3/api-docs",
    "/v2/api-docs",
    "/swagger.json",
    "/api-docs",
]


# ═══════════════════════════════════════════════════════
#  扫描与索引
# ═══════════════════════════════════════════════════════

def _parse_openapi_endpoints(spec: dict) -> list[dict]:
    """从 OpenAPI 规范中提取所有端点信息。"""
    endpoints = []
    base_path = spec.get("servers", [{}])[0].get("url", "") if "servers" in spec else ""

    for path, methods in spec.get("paths", {}).items():
        if not isinstance(methods, dict):
            continue
        for method, detail in methods.items():
            if method.upper() not in ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"):
                continue
            if not isinstance(detail, dict):
                continue

            # 提取 tags
            tags = detail.get("tags", [])
            # 提取参数
            params = []
            for p in detail.get("parameters", []):
                params.append({
                    "name": p.get("name", ""),
                    "in": p.get("in", "query"),
                    "required": p.get("required", False),
                    "type": p.get("schema", {}).get("type", "string") if p.get("schema") else "string",
                    "description": p.get("description", ""),
                })

            # 提取请求体（如有）
            req_body = None
            if "requestBody" in detail:
                rb = detail["requestBody"]
                rb_content = rb.get("content", {})
                if "application/json" in rb_content:
                    schema = rb_content["application/json"].get("schema", {})
                    req_body = {"type": "json", "schema": schema}
                elif "application/x-www-form-urlencoded" in rb_content:
                    schema = rb_content["application/x-www-form-urlencoded"].get("schema", {})
                    req_body = {"type": "form", "schema": schema}

            endpoints.append({
                "path": path,
                "method": method.upper(),
                "summary": detail.get("summary", ""),
                "description": detail.get("description", ""),
                "operationId": detail.get("operationId", ""),
                "tags": tags,
                "parameters": params,
                "requestBody": req_body,
                "base_url": base_path,
            })

    return endpoints


def _validate_openapi_spec(data: dict) -> tuple[bool, str]:
    """验证是否为合法的 OpenAPI/Swagger 规范。"""
    if not isinstance(data, dict):
        return False, "JSON 必须是对象类型"
    if "openapi" not in data and "swagger" not in data:
        return False, "缺少 openapi 或 swagger 字段，不是有效的 OpenAPI 规范"
    if "paths" not in data:
        return False, "缺少 paths 字段"
    if not isinstance(data.get("paths"), dict):
        return False, "paths 字段必须是对象类型"
    # 检查至少有一个合法路径
    valid_count = 0
    for path, methods in data["paths"].items():
        if isinstance(methods, dict):
            for m in methods:
                if m.upper() in ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"):
                    valid_count += 1
    if valid_count == 0:
        return False, "paths 中没有找到有效的 HTTP 方法端点"
    return True, ""


def _get_service_name_from_spec(spec: dict) -> str:
    """从 OpenAPI 规范中提取服务名。"""
    info = spec.get("info", {})
    title = info.get("title", "unnamed")
    # 清理服务名
    for ch in '<>:"/\\|?*':
        title = title.replace(ch, "-")
    return title.strip() or "unnamed"


def _tag_safe_name(tag_name: str) -> str:
    """将 tag 名转为安全的文件名。"""
    for ch in '<>:"/\\|?*':
        tag_name = tag_name.replace(ch, "-")
    return tag_name.strip() or "default"


def _scan_json_files(base_dir: Path) -> list[dict]:
    """扫描目录下所有 JSON 文件并返回文件信息列表。"""
    results = []
    if not base_dir.exists():
        return results

    for json_file in sorted(base_dir.rglob("*.json")):
        rel_path = json_file.relative_to(base_dir)
        parts = rel_path.parts

        if len(parts) >= 2:
            service_name = parts[0]  # 第一层目录 = 服务名
            file_name = parts[-1].replace(".json", "")
        else:
            # 跳过根目录下的 JSON 文件，提示用户移动到子目录
            print(f"[WARN] 跳过根目录文件: {json_file}，请移动到 data_interface/<服务名>/ 子目录下")
            continue

        results.append({
            "service_name": service_name,
            "file_name": file_name,
            "spec_file_path": str(json_file),
            "file_mtime": json_file.stat().st_mtime,
        })

    return results


def sync_data_interfaces_index(force: bool = False) -> int:
    """
    扫描 data_interface/ 目录，将接口信息同步到数据库索引表。
    - 首次启动时全量扫描
    - 后续只扫描修改时间有变化的文件
    - 返回新增/更新的接口数量
    """
    conn = get_db()
    indexed = 0

    try:
        files_info = _scan_json_files(_DATA_INTERFACE_DIR)
        if not files_info:
            return 0

        for fi in files_info:
            spec_path = Path(fi["spec_file_path"])
            if not spec_path.exists():
                continue

            # 检查文件是否已索引且未变化
            if not force:
                existing = conn.execute(
                    "SELECT MAX(file_mtime) as mtime FROM data_interfaces "
                    "WHERE spec_file_path = ?",
                    (fi["spec_file_path"],),
                ).fetchone()
                if existing and existing["mtime"] is not None and abs(existing["mtime"] - fi["file_mtime"]) < 0.01:
                    continue

            # 解析 JSON
            try:
                spec = json.loads(spec_path.read_text(encoding="utf-8"))
            except Exception:
                continue

            # 验证
            valid, _ = _validate_openapi_spec(spec)
            if not valid:
                continue

            # 删除该文件在索引中的旧记录
            conn.execute(
                "DELETE FROM data_interfaces WHERE spec_file_path = ?",
                (fi["spec_file_path"],),
            )

            # 提取端点
            endpoints = _parse_openapi_endpoints(spec)
            for ep in endpoints:
                tags_json = json.dumps(ep.get("tags", []), ensure_ascii=False)
                params_json = json.dumps(ep.get("parameters", []), ensure_ascii=False)

                try:
                    conn.execute(
                        """INSERT INTO data_interfaces
                        (service_name, file_name, path, method, summary, operation_id,
                         parameters, tags, spec_file_path, file_mtime, enabled)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                        (
                            fi["service_name"],
                            fi["file_name"],
                            ep["path"],
                            ep["method"],
                            ep.get("summary", ""),
                            ep.get("operationId", ""),
                            params_json,
                            tags_json,
                            fi["spec_file_path"],
                            fi["file_mtime"],
                        ),
                    )
                    indexed += 1
                except Exception:
                    # unique constraint 冲突则跳过
                    pass

        conn.commit()
    finally:
        conn.close()

    return indexed


# ═══════════════════════════════════════════════════════
#  查询接口
# ═══════════════════════════════════════════════════════

def _is_admin(user_role: str) -> bool:
    return user_role == "admin"


def get_interface_tree(user_id: int, user_role: str) -> dict:
    """
    返回当前用户有权访问的服务→接口树结构。

    格式:
    {
      "services": [
        {
          "name": "基础信息管理",
          "files": [
            {
              "name": "人员管理",
              "interfaces": [
                {
                  "id": 1, "path": "/api/user/list", "method": "GET",
                  "summary": "获取用户列表", "operationId": "...",
                  "tags": [...], "parameters": [...], "granted": true
                }
              ]
            }
          ]
        }
      ]
    }
    """
    conn = get_db()
    try:
        if _is_admin(user_role):
            # 管理员看到所有接口，全部 granted
            rows = conn.execute(
                "SELECT id, service_name, file_name, path, method, summary, "
                "operation_id, parameters, tags, enabled "
                "FROM data_interfaces ORDER BY service_name, file_name, path, method"
            ).fetchall()
        else:
            # 普通用户只看到被授权的接口
            rows = conn.execute(
                "SELECT di.id, di.service_name, di.file_name, di.path, di.method, "
                "di.summary, di.operation_id, di.parameters, di.tags, di.enabled, "
                "COALESCE(ua.granted, 0) as granted "
                "FROM data_interfaces di "
                "LEFT JOIN user_interface_access ua ON ua.interface_id = di.id AND ua.user_id = ? "
                "WHERE di.enabled = 1 AND (ua.id IS NULL OR ua.granted = 1) "
                "ORDER BY di.service_name, di.file_name, di.path, di.method",
                (user_id,),
            ).fetchall()

        # 构建树
        services_map = {}
        for row in rows:
            data = dict(row)
            sn = data["service_name"]
            fn = data["file_name"]
            if sn not in services_map:
                services_map[sn] = {}
            if fn not in services_map[sn]:
                services_map[sn][fn] = []
            services_map[sn][fn].append({
                "id": data["id"],
                "path": data["path"],
                "method": data["method"],
                "summary": data["summary"],
                "operationId": data["operation_id"],
                "tags": json.loads(data["tags"]) if data["tags"] else [],
                "parameters": json.loads(data["parameters"]) if data["parameters"] else [],
                "granted": data.get("granted", True),
                "enabled": bool(data.get("enabled", 1)),
            })

        services = []
        for sn in sorted(services_map.keys()):
            files = []
            for fn in sorted(services_map[sn].keys()):
                files.append({
                    "name": fn,
                    "interfaces": services_map[sn][fn],
                })
            services.append({"name": sn, "files": files})

        return {"services": services}
    finally:
        conn.close()


def get_interface_detail(interface_id: int) -> Optional[dict]:
    """获取单个接口的完整参数定义。"""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT di.* FROM data_interfaces di WHERE di.id = ?",
            (interface_id,),
        ).fetchone()
        if not row:
            return None

        data = dict(row)
        # 尝试从原始文件中读取完整信息
        spec_path = Path(data["spec_file_path"])
        full_spec = {}
        if spec_path.exists():
            try:
                spec = json.loads(spec_path.read_text(encoding="utf-8"))
                full_spec = spec.get("info", {})
                # 传递 servers 信息，用于前端自动填写目标地址
                full_spec["servers"] = spec.get("servers", [])
                # 找到对应端点的完整定义
                paths = spec.get("paths", {})
                ep_def = paths.get(data["path"], {}).get(data["method"].lower(), {})
                full_spec["endpoint_detail"] = ep_def
            except Exception:
                pass

        data["spec_info"] = full_spec
        data["parameters"] = json.loads(data["parameters"]) if data["parameters"] else []
        data["tags"] = json.loads(data["tags"]) if data["tags"] else []
        return data
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════
#  导入接口
# ═══════════════════════════════════════════════════════

def import_from_swagger_url(base_url: str, service_name: str = "", timeout: int = 15) -> dict:
    """
    从前端传入的 Swagger URL 导入接口。

    流程:
    1. 探测 Swagger 端点
    2. 下载 OpenAPI JSON
    3. 后端验证
    4. 保存到 data_interface/ 并按 service_name 归类
    5. 同步到数据库索引

    返回 {"ok": True, "imported": N, "service_name": "...", "message": "..."}
    """
    base_url = base_url.rstrip("/")

    # 1. 探测端点
    spec_data = None
    detected_path = None
    for path in _STANDARD_SWAGGER_PATHS:
        full_url = f"{base_url}{path}"
        try:
            resp = requests.get(full_url, timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict) and ("openapi" in data or "swagger" in data):
                    spec_data = data
                    detected_path = path
                    break
        except Exception:
            continue

    if spec_data is None:
        return {"ok": False, "message": f"无法从 {base_url} 探测到有效的 OpenAPI 端点，已尝试: {', '.join(_STANDARD_SWAGGER_PATHS)}"}

    # 2. 验证
    valid, msg = _validate_openapi_spec(spec_data)
    if not valid:
        return {"ok": False, "message": f"OpenAPI 规范验证失败: {msg}"}

    # 3. 确定服务名和文件名
    if not service_name:
        service_name = _get_service_name_from_spec(spec_data)

    file_name = _tag_safe_name(_get_service_name_from_spec(spec_data))

    # 4. 保存文件
    save_dir = _DATA_INTERFACE_DIR / service_name
    save_dir.mkdir(parents=True, exist_ok=True)

    filepath = save_dir / f"{file_name}.json"
    filepath.write_text(
        json.dumps(spec_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 5. 同步到索引
    endpoints = _parse_openapi_endpoints(spec_data)
    conn = get_db()
    try:
        # 清除该文件的旧索引
        conn.execute(
            "DELETE FROM data_interfaces WHERE spec_file_path = ?",
            (str(filepath),),
        )
        imported = 0
        for ep in endpoints:
            try:
                conn.execute(
                    """INSERT INTO data_interfaces
                    (service_name, file_name, path, method, summary, operation_id,
                     parameters, tags, spec_file_path, file_mtime, enabled)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                    (
                        service_name,
                        file_name,
                        ep["path"],
                        ep["method"],
                        ep.get("summary", ""),
                        ep.get("operationId", ""),
                        json.dumps(ep.get("parameters", []), ensure_ascii=False),
                        json.dumps(ep.get("tags", []), ensure_ascii=False),
                        str(filepath),
                        filepath.stat().st_mtime,
                    ),
                )
                imported += 1
            except Exception:
                pass
        conn.commit()
    finally:
        conn.close()

    return {
        "ok": True,
        "imported": imported,
        "service_name": service_name,
        "file_name": file_name,
        "message": f"成功从 {base_url}{detected_path} 导入 {imported} 个接口到 [{service_name}/{file_name}]",
    }


def import_from_json_content(json_content: str, service_name: str = "") -> dict:
    """
    从前端上传的 JSON 内容导入接口。

    返回 {"ok": True, "imported": N, "service_name": "...", "message": "..."}
    """
    # 1. 解析 JSON
    try:
        spec_data = json.loads(json_content)
    except json.JSONDecodeError as e:
        return {"ok": False, "message": f"JSON 解析失败: {e}"}

    # 2. 验证
    valid, msg = _validate_openapi_spec(spec_data)
    if not valid:
        return {"ok": False, "message": f"OpenAPI 规范验证失败: {msg}"}

    # 3. 确定服务名
    if not service_name:
        service_name = _get_service_name_from_spec(spec_data)

    file_name = _tag_safe_name(_get_service_name_from_spec(spec_data))

    # 4. 保存文件
    save_dir = _DATA_INTERFACE_DIR / service_name
    save_dir.mkdir(parents=True, exist_ok=True)

    filepath = save_dir / f"{file_name}.json"
    filepath.write_text(
        json.dumps(spec_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 5. 同步到索引
    endpoints = _parse_openapi_endpoints(spec_data)
    conn = get_db()
    try:
        conn.execute(
            "DELETE FROM data_interfaces WHERE spec_file_path = ?",
            (str(filepath),),
        )
        imported = 0
        for ep in endpoints:
            try:
                conn.execute(
                    """INSERT INTO data_interfaces
                    (service_name, file_name, path, method, summary, operation_id,
                     parameters, tags, spec_file_path, file_mtime, enabled)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                    (
                        service_name,
                        file_name,
                        ep["path"],
                        ep["method"],
                        ep.get("summary", ""),
                        ep.get("operationId", ""),
                        json.dumps(ep.get("parameters", []), ensure_ascii=False),
                        json.dumps(ep.get("tags", []), ensure_ascii=False),
                        str(filepath),
                        filepath.stat().st_mtime,
                    ),
                )
                imported += 1
            except Exception:
                pass
        conn.commit()
    finally:
        conn.close()

    return {
        "ok": True,
        "imported": imported,
        "service_name": service_name,
        "file_name": file_name,
        "message": f"成功导入 {imported} 个接口到 [{service_name}/{file_name}]",
    }


# ═══════════════════════════════════════════════════════
#  删除接口
# ═══════════════════════════════════════════════════════

def delete_single_interface(interface_id: int) -> dict:
    """
    从索引中删除单个接口记录。
    注意：不会修改原始 JSON 文件（接口定义保留在文件中），
    仅从索引中移除，使该接口不再暴露给前端。
    """
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, spec_file_path, path, method FROM data_interfaces WHERE id = ?",
            (interface_id,),
        ).fetchone()
        if not row:
            return {"ok": False, "message": "接口不存在"}

        conn.execute("DELETE FROM data_interfaces WHERE id = ?", (interface_id,))
        conn.commit()
        return {"ok": True, "message": "接口已从索引中删除"}
    finally:
        conn.close()


def delete_interface_file(service_name: str, file_name: str) -> dict:
    """
    删除一个接口文件及其数据库索引。
    1. 删除 data_interface/{service_name}/{file_name}.json
    2. 从 data_interfaces 表中删除该文件的所有记录
    3. 若目录为空则删除目录
    """
    filepath = _DATA_INTERFACE_DIR / service_name / f"{file_name}.json"

    if not filepath.exists():
        # 尝试查找匹配的文件
        parent_dir = _DATA_INTERFACE_DIR / service_name
        if parent_dir.exists():
            for f in parent_dir.glob("*.json"):
                if f.stem == file_name:
                    filepath = f
                    break

    if not filepath.exists():
        return {"ok": False, "message": f"文件不存在: {service_name}/{file_name}.json"}

    # 删除文件
    try:
        filepath.unlink()
    except Exception as e:
        return {"ok": False, "message": f"删除文件失败: {e}"}

    # 删除索引
    conn = get_db()
    try:
        conn.execute(
            "DELETE FROM data_interfaces WHERE spec_file_path = ?",
            (str(filepath),),
        )
        conn.commit()
    finally:
        conn.close()

    # 清理空目录
    try:
        parent_dir = filepath.parent
        if parent_dir != _DATA_INTERFACE_DIR and parent_dir.exists():
            remaining = list(parent_dir.iterdir())
            if not remaining:
                parent_dir.rmdir()
    except Exception:
        pass

    return {"ok": True, "message": f"已删除接口文件 [{service_name}/{file_name}]"}


def delete_service_directory(service_name: str) -> dict:
    """
    删除整个服务目录及其所有数据。
    1. 删除 data_interface/{service_name}/ 整个目录
    2. 从 data_interfaces 表中删除该服务的所有记录
    """
    service_dir = _DATA_INTERFACE_DIR / service_name
    if not service_dir.exists() or not service_dir.is_dir():
        return {"ok": False, "message": f"服务目录不存在: {service_name}"}

    # 删除目录
    try:
        shutil.rmtree(service_dir)
    except Exception as e:
        return {"ok": False, "message": f"删除目录失败: {e}"}

    # 删除索引
    conn = get_db()
    try:
        conn.execute(
            "DELETE FROM data_interfaces WHERE service_name = ?",
            (service_name,),
        )
        conn.commit()
    finally:
        conn.close()

    return {"ok": True, "message": f"已删除服务 [{service_name}] 及其所有接口"}


def list_all_services() -> list[str]:
    """返回所有已索引的服务名列表。"""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT DISTINCT service_name FROM data_interfaces ORDER BY service_name"
        ).fetchall()
        return [row["service_name"] for row in rows]
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════
#  用户接口权限管理
# ═══════════════════════════════════════════════════════

def get_user_interface_permissions(user_id: int) -> dict:
    """
    获取指定用户对所有已索引接口的权限状态。

    返回:
    {
      "user_id": 3,
      "services": [
        {
          "name": "基础信息管理",
          "files": [
            {
              "name": "人员管理",
              "interfaces": [
                {"id": 1, "path": "/api/user/list", "method": "GET", "summary": "...", "granted": true}
              ]
            }
          ]
        }
      ]
    }
    """
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT di.id, di.service_name, di.file_name, di.path, di.method, "
            "di.summary, COALESCE(ua.granted, 0) as granted "
            "FROM data_interfaces di "
            "LEFT JOIN user_interface_access ua ON ua.interface_id = di.id AND ua.user_id = ? "
            "WHERE di.enabled = 1 "
            "ORDER BY di.service_name, di.file_name, di.path, di.method",
            (user_id,),
        ).fetchall()

        services_map = {}
        for row in rows:
            data = dict(row)
            sn = data["service_name"]
            fn = data["file_name"]
            if sn not in services_map:
                services_map[sn] = {}
            if fn not in services_map[sn]:
                services_map[sn][fn] = []
            services_map[sn][fn].append({
                "id": data["id"],
                "path": data["path"],
                "method": data["method"],
                "summary": data["summary"],
                "granted": bool(data["granted"]),
            })

        services = []
        for sn in sorted(services_map.keys()):
            files = []
            for fn in sorted(services_map[sn].keys()):
                files.append({"name": fn, "interfaces": services_map[sn][fn]})
            services.append({"name": sn, "files": files})

        return {"user_id": user_id, "services": services}
    finally:
        conn.close()


def set_user_interface_permissions(user_id: int, granted_ids: list[int], revoked_ids: list[int]) -> dict:
    """
    批量设置用户的接口权限。

    Args:
        user_id: 目标用户 ID
        granted_ids: 需要授权的接口 ID 列表
        revoked_ids: 需要撤销授权的接口 ID 列表

    返回 {"ok": True, "granted": N, "revoked": M}
    """
    conn = get_db()
    try:
        g_count = 0
        r_count = 0

        for iid in granted_ids:
            conn.execute(
                """INSERT INTO user_interface_access (user_id, interface_id, granted)
                VALUES (?, ?, 1)
                ON CONFLICT(user_id, interface_id) DO UPDATE SET granted = 1, updated_at = CURRENT_TIMESTAMP""",
                (user_id, iid),
            )
            g_count += 1

        for iid in revoked_ids:
            conn.execute(
                """INSERT INTO user_interface_access (user_id, interface_id, granted)
                VALUES (?, ?, 0)
                ON CONFLICT(user_id, interface_id) DO UPDATE SET granted = 0, updated_at = CURRENT_TIMESTAMP""",
                (user_id, iid),
            )
            r_count += 1

        conn.commit()
        return {"ok": True, "granted": g_count, "revoked": r_count}
    finally:
        conn.close()


def set_user_all_interface_access(user_id: int, granted: bool) -> dict:
    """
    为一键操作：授予/撤销用户对所有接口的访问权限。

    Args:
        user_id: 目标用户 ID
        granted: True = 授予全部, False = 撤销全部
    """
    conn = get_db()
    try:
        value = 1 if granted else 0
        all_ifaces = conn.execute("SELECT id FROM data_interfaces WHERE enabled = 1").fetchall()

        for row in all_ifaces:
            conn.execute(
                """INSERT INTO user_interface_access (user_id, interface_id, granted)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, interface_id) DO UPDATE SET granted = ?, updated_at = CURRENT_TIMESTAMP""",
                (user_id, row["id"], value, value),
            )

        conn.commit()
        return {"ok": True, "message": f"已{'授予' if granted else '撤销'} {len(all_ifaces)} 个接口的访问权限"}
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════
#  接口测试（代理请求）
# ═══════════════════════════════════════════════════════

def test_interface(interface_id: int, params: dict = None, body: dict = None,
                   base_url_override: str = "", timeout: int = 30) -> dict:
    """
    代理发送接口测试请求并返回响应。

    Args:
        interface_id: 数据库中的接口 ID
        params: 参数字典 {name: value, ...}
        body: 请求体（用于 POST/PUT/PATCH）
        base_url_override: 用户手动指定的 base_url，为空则从 spec 中读取
        timeout: 请求超时秒数

    Returns:
        {
            "ok": True/False,
            "request": { "url": "...", "method": "...", "params": {...}, "body": {...} },
            "response": {
                "status_code": 200,
                "headers": {...},
                "body": ...,
                "elapsed_ms": 123
            },
            "message": "..."
        }
    """
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM data_interfaces WHERE id = ?",
            (interface_id,),
        ).fetchone()
        if not row:
            return {"ok": False, "message": "接口不存在"}
    finally:
        conn.close()

    data = dict(row)
    spec_path = Path(data["spec_file_path"])
    if not spec_path.exists():
        return {"ok": False, "message": f"接口配置文件不存在: {spec_path}"}

    # 读取 spec 获取 base_url
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except Exception:
        return {"ok": False, "message": "接口配置文件解析失败"}

    # 确定 base_url
    base_url = base_url_override.strip().rstrip("/") if base_url_override else ""
    if not base_url:
        servers = spec.get("servers", [])
        if servers:
            base_url = (servers[0].get("url", "") or "").rstrip("/")
    if not base_url:
        return {"ok": False, "message": "未配置基础 URL。请在界面中手动填写或检查 spec 的 servers 字段。"}

    path = data["path"]
    method = data["method"].upper()

    # 构建完整 URL
    full_url = f"{base_url}{path}"

    # 分离 query 参数和 header 参数等 + 校验必填参数
    query_params = {}
    headers_override = {}
    missing_required = []
    if params is not None:
        params = params
    else:
        params = {}

    # 从 spec 中获取参数位置信息
    for ep in _parse_openapi_endpoints(spec):
        if ep["path"] == path and ep["method"] == method:
            for p in ep.get("parameters", []):
                pname = p["name"]
                user_val = params.get(pname, "").strip() if isinstance(params.get(pname, ""), str) else params.get(pname, None)
                if user_val is None or user_val == "":
                    if p.get("required"):
                        missing_required.append(f"{pname} ({p.get('in', 'query')})")
                    continue
                if p.get("in") == "query":
                    query_params[pname] = user_val
                elif p.get("in") == "header":
                    headers_override[pname] = str(user_val)
                elif p.get("in") == "path":
                    full_url = full_url.replace(f"{{{pname}}}", str(user_val))
            break

    if missing_required:
        return {
            "ok": False,
            "message": f"缺少必填参数: {', '.join(missing_required)}",
            "request": _build_req_info(method, full_url, query_params, body),
        }

    # 默认 headers
    req_headers = {
        "Accept": "application/json",
        "User-Agent": "HNGD-KnowledgeAgent/1.0",
    }
    if headers_override:
        req_headers.update(headers_override)

    # 发送请求
    try:
        if method in ("POST", "PUT", "PATCH") and body is not None:
            req_headers["Content-Type"] = "application/json"
            resp = requests.request(
                method=method,
                url=full_url,
                params=query_params,
                json=body,
                headers=req_headers,
                timeout=timeout,
            )
        else:
            resp = requests.request(
                method=method,
                url=full_url,
                params=query_params,
                headers=req_headers,
                timeout=timeout,
            )
    except requests.exceptions.Timeout:
        return {"ok": False, "message": f"请求超时（{timeout}秒）", "request": _build_req_info(method, full_url, query_params, body)}
    except requests.exceptions.ConnectionError as e:
        return {"ok": False, "message": f"连接失败: {e}", "request": _build_req_info(method, full_url, query_params, body)}
    except Exception as e:
        return {"ok": False, "message": f"请求异常: {e}", "request": _build_req_info(method, full_url, query_params, body)}

    # 解析响应
    response_body = None
    try:
        response_body = resp.json()
    except Exception:
        try:
            response_body = resp.text
        except Exception:
            response_body = "(无法解析响应体)"

    return {
        "ok": True,
        "request": _build_req_info(method, full_url, query_params, body),
        "response": {
            "status_code": resp.status_code,
            "headers": dict(resp.headers),
            "body": response_body,
            "elapsed_ms": round(resp.elapsed.total_seconds() * 1000),
        },
        "message": f"收到 {resp.status_code} 响应",
    }


def _build_req_info(method: str, url: str, params: dict = None, body: dict = None) -> dict:
    """构建请求信息摘要。"""
    info = {"method": method, "url": url}
    if params:
        info["params"] = params
    if body is not None:
        info["body"] = body
    return info
