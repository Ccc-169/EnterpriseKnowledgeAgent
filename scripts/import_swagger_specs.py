# scripts/import_swagger_specs.py
"""
从 Swagger 页面自动导入 OpenAPI 规范到 data_interface/ 目录。

用法:
    # 从单个 Swagger URL 导入（SpringDoc 默认路径）
    python scripts/import_swagger_specs.py http://192.168.1.160:18889

    # 从多个 Swagger URL 导入
    python scripts/import_swagger_specs.py http://192.168.1.160:18889 http://192.168.1.160:18890

    # 指定自定义 OpenAPI 路径
    python scripts/import_swagger_specs.py http://192.168.1.160:18889 --path /custom-api-docs

    # 从 Swagger UI 页面抓取所有 JSON 链接并导入
    python scripts/import_swagger_specs.py http://192.168.1.160:18889 --crawl-ui

    # 按服务名分组保存到子目录
    python scripts/import_swagger_specs.py http://192.168.1.160:18889 --group-by-service

    # 从本地文件导入
    python scripts/import_swagger_specs.py --file ./my-swagger.json

原理:
    对于每个 BASE_URL，尝试以下顺序查找 OpenAPI 规范端点：
    1. 如果指定 --crawl-ui，先从 Swagger UI 页面抓取所有 JSON 链接
    2. {BASE_URL}/v3/api-docs            — SpringDoc / springfox 新版本
    3. {BASE_URL}/v2/api-docs            — Springfox 旧版本
    4. {BASE_URL}/swagger.json           — 通用 Swagger
    5. {BASE_URL}/api-docs               — 常见自定义路径
    6. --path 指定的自定义路径

    下载后按服务名保存为 JSON 文件到 data_interface/ 目录。
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

# ── 默认输出目录 ──────────────────────────────────────
_DEFAULT_OUTPUT = Path(__file__).parent.parent / "data_interface"

# ── 常见的 OpenAPI 规范端点路径 ────────────────────────
_STANDARD_PATHS = [
    "/v3/api-docs",
    "/v2/api-docs",
    "/swagger.json",
    "/api-docs",
]


def _normalize_url(url: str) -> str:
    """清理 URL，去掉末尾斜杠。"""
    return url.rstrip("/")


def try_fetch_spec(base_url: str, path: str, timeout: int = 10) -> dict | None:
    """尝试从某个路径获取 OpenAPI 规范。"""
    full_url = urljoin(base_url, path)
    print(f"  → 尝试: {full_url} ... ", end="", flush=True)
    try:
        resp = requests.get(full_url, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            # 验证是否真的是 OpenAPI 规范
            if "openapi" in data or "swagger" in data:
                print("[OK] 成功")
                return data
            else:
                print("[FAIL] 返回了 JSON 但不是 OpenAPI 规范")
        else:
            print(f"[FAIL] HTTP {resp.status_code}")
    except requests.exceptions.ConnectionError:
        print("[FAIL] 连接失败")
    except requests.exceptions.Timeout:
        print(f"[FAIL] 超时 ({timeout}s)")
    except Exception as e:
        print(f"[FAIL] {e}")
    return None


def _safe_filename(name: str) -> str:
    """将服务名转换为安全的文件名。"""
    # 移除路径分隔符和非法字符
    safe = name.replace("/", "-").replace("\\", "-").replace(":", "-")
    safe = "".join(c for c in safe if c not in '<>:"/\\|?*')
    return safe.strip() or "unnamed"


def save_spec(spec: dict, output_dir: Path, group_by_service: bool = False, *, doc_title: str = "", tag_desc: str = ""):
    """
    保存 OpenAPI 规范到文件。
    
    Args:
        spec: OpenAPI 规范字典
        output_dir: 输出目录
        group_by_service: True 时按文档标题分组到子目录
        doc_title: 文档标题（来自 /api/document 接口）
        tag_desc: tag 描述（用于文件名）
    """
    info_title = spec.get("info", {}).get("title", "unnamed")
    version = spec.get("info", {}).get("version", "")

    # 确定保存路径
    if group_by_service and doc_title:
        # 用文档标题作为目录名
        save_dir = output_dir / _safe_filename(doc_title)
    else:
        save_dir = output_dir

    save_dir.mkdir(parents=True, exist_ok=True)

    # 确定文件名：优先用 tag 描述，否则用 info.title
    if tag_desc:
        filename = f"{_safe_filename(tag_desc)}.json"
    else:
        filename = f"{_safe_filename(info_title)}.json"

    filepath = save_dir / filename

    filepath.write_text(
        json.dumps(spec, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  [OK] 已保存: {filepath}")



def _fetch_document_list(base_url: str, timeout: int = 10) -> list[dict]:
    """
    调用 /api/document 获取文档列表（openapi-ui 自定义系统）。
    
    返回文档列表，每个元素包含 filename, title, version, tags 等。
    """
    api_url = urljoin(base_url, "/api/document")
    try:
        print(f"  → 尝试获取文档列表: {api_url} ... ", end="", flush=True)
        resp = requests.get(api_url, timeout=timeout)
        if resp.status_code != 200:
            print(f"[FAIL] HTTP {resp.status_code}")
            return []
        data = resp.json()
        if isinstance(data, dict) and data.get("success") and "data" in data:
            docs = data["data"]
            print(f"[OK] 找到 {len(docs)} 个文档")
            return docs
        elif isinstance(data, list):
            print(f"[OK] 找到 {len(data)} 个文档")
            return data
        else:
            print("[FAIL] 返回格式不符合预期")
            return []
    except requests.exceptions.ConnectionError:
        print("[FAIL] 连接失败")
    except requests.exceptions.Timeout:
        print(f"[FAIL] 超时 ({timeout}s)")
    except Exception as e:
        print(f"[FAIL] {e}")
    return []


def _crawl_swagger_ui(base_url: str, timeout: int = 10) -> list[tuple[str, str, str, str]]:
    """
    从 Swagger UI 页面抓取所有 JSON 链接。
    
    返回 [(json_url, tag_name, tag_desc, doc_title), ...] 列表。
    """
    # 优先尝试 openapi-ui 的 /api/document 接口
    docs = _fetch_document_list(base_url, timeout)
    if docs:
        results = []
        seen = set()
        for doc in docs:
            filename = doc.get("filename", "")
            doc_title = doc.get("title", "")
            if not filename:
                continue
            tags = doc.get("tags", [])
            if tags:
                # 按 tag 拆分下载
                for tag_info in tags:
                    tag_name = tag_info.get("name", "")
                    tag_desc = tag_info.get("description", tag_name)
                    query = tag_info.get("query", "")
                    if query:
                        json_url = urljoin(base_url, f"/api/document/content/{query}")
                    else:
                        json_url = urljoin(base_url, f"/api/document/content/{filename}?tag={tag_name}")
                    key = (json_url, tag_desc)
                    if key not in seen:
                        seen.add(key)
                        results.append((json_url, tag_name, tag_desc, doc_title))
            else:
                # 无 tag，下载完整文件
                json_url = urljoin(base_url, f"/api/document/content/{filename}")
                key = (json_url, doc_title)
                if key not in seen:
                    seen.add(key)
                    results.append((json_url, "", doc_title or doc_title, doc_title))
        return results

    # 回退：尝试从 HTML 页面抓取
    ui_paths = ["/swagger-ui.html", "/swagger/index.html", "/swagger-ui/", "/"]
    for ui_path in ui_paths:
        ui_url = urljoin(base_url, ui_path)
        try:
            print(f"  → 尝试抓取 UI 页面: {ui_url} ... ", end="", flush=True)
            resp = requests.get(ui_url, timeout=timeout)
            if resp.status_code != 200:
                print(f"[FAIL] HTTP {resp.status_code}")
                continue
            print("[OK]")
            
            html = resp.text
            results = []
            patterns = [
                r'(/api/document/content/[^"\'\s<>]+\.json[^"\'\s<>]*)',
                r'["\']([^"\']*\.json\?[^"\']*)["\']',
                r'url\s*:\s*["\']([^"\']*\.json[^"\']*)["\']',
            ]
            
            seen = set()
            for pattern in patterns:
                for match in re.finditer(pattern, html):
                    url = match.group(1)
                    if url.startswith("/"):
                        full = urljoin(base_url, url)
                    elif url.startswith("http"):
                        full = url
                    else:
                        full = urljoin(base_url + "/", url)
                    
                    if full not in seen:
                        seen.add(full)
                        tag = ""
                        tag_match = re.search(r'[?&]tag=([^&]+)', full)
                        if tag_match:
                            tag = tag_match.group(1)
                        results.append((full, tag, tag, ""))
            
            return results
            
        except requests.exceptions.ConnectionError:
            print("[FAIL] 连接失败")
        except requests.exceptions.Timeout:
            print(f"[FAIL] 超时 ({timeout}s)")
        except Exception as e:
            print(f"[FAIL] {e}")
    
    return []


def import_from_url(
    base_url: str,
    output_dir: Path,
    custom_path: str = None,
    group_by_service: bool = False,
    timeout: int = 10,
    crawl_ui: bool = False,
) -> int:
    """从 Swagger URL 导入 OpenAPI 规范。返回成功导入的数量。"""
    base_url = _normalize_url(base_url)
    print(f"\n[LOC] 正在从 {base_url} 导入...")
    success_count = 0

    # 如果指定了 --crawl-ui，先从页面抓取 JSON 链接
    if crawl_ui:
        print("  [SEARCH] 启用 UI 页面抓取模式...")
        json_links = _crawl_swagger_ui(base_url, timeout)
        if json_links:
            print(f"  发现 {len(json_links)} 个 JSON 链接:")
            for url, tag_name, tag_desc, doc_title in json_links:
                display = tag_desc or doc_title or tag_name or "unknown"
                print(f"    - [{display}] {url}")
                spec = try_fetch_spec(url, "", timeout)
                if spec:
                    save_spec(spec, output_dir, group_by_service, doc_title=doc_title, tag_desc=tag_desc)
                    success_count += 1
            if success_count > 0:
                return success_count
            print("  [WARN] 抓取到的链接都未能下载成功，尝试标准路径...")
        else:
            print("  [WARN] 未从 UI 页面抓取到 JSON 链接，尝试标准路径...")

    # 如果指定了自定义路径，优先尝试
    if custom_path:
        spec = try_fetch_spec(base_url, custom_path, timeout)
        if spec:
            save_spec(spec, output_dir, group_by_service)
            return 1
        print(f"  [WARN] 自定义路径 {custom_path} 失败，尝试标准路径...")

    # 依次尝试标准路径
    for path in _STANDARD_PATHS:
        spec = try_fetch_spec(base_url, path, timeout)
        if spec:
            save_spec(spec, output_dir, group_by_service)
            return 1

    print(f"\n  [FAIL] 未能从 {base_url} 找到 OpenAPI 规范。")
    print("  请确认：")
    print("    1. 该服务已启动且可访问")
    print("    2. Swagger/OpenAPI 端点已启用")
    print("    3. 尝试用 --path 参数指定自定义路径")
    print("    4. 如果是自定义 Swagger UI，尝试加 --crawl-ui 参数")
    return 0


def import_from_file(filepath: str, output_dir: Path, group_by_service: bool = False):
    """从本地 JSON 文件导入 OpenAPI 规范。"""
    path = Path(filepath)
    if not path.exists():
        print(f"[FAIL] 文件不存在: {filepath}")
        return False

    try:
        spec = json.loads(path.read_text(encoding="utf-8"))
        if "openapi" not in spec and "swagger" not in spec:
            print(f"[FAIL] {filepath} 不是有效的 OpenAPI 规范文件")
            return False
        save_spec(spec, output_dir, group_by_service)
        return True
    except Exception as e:
        print(f"[FAIL] 读取 {filepath} 失败: {e}")
        return False


# ── 主入口 ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="从 Swagger 页面自动导入 OpenAPI 规范到 data_interface/",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 从默认路径导入（标准 SpringDoc/Swagger）
  python import_swagger_specs.py http://192.168.1.160:18889

  # 从自定义 Swagger UI 页面抓取所有 JSON
  python import_swagger_specs.py http://192.168.1.160:18889 --crawl-ui

  # 从多个服务导入
  python import_swagger_specs.py http://192.168.1.160:18889 http://192.168.1.160:18890

  # 指定自定义 OpenAPI 路径
  python import_swagger_specs.py http://192.168.1.160:18889 --path /my-api-docs

  # 按服务分组到子目录
  python import_swagger_specs.py http://192.168.1.160:18889 --group-by-service

  # 从本地文件导入
  python import_swagger_specs.py --file ./downloaded_swagger.json

  # 同时从 URL 和文件导入
  python import_swagger_specs.py http://192.168.1.160:18889 --file ./backup.json
        """,
    )
    parser.add_argument(
        "urls", nargs="*",
        help="Swagger 服务的基础 URL（可多个）",
    )
    parser.add_argument(
        "--file", "-f", action="append", default=[],
        help="本地 OpenAPI JSON 文件路径（可多次使用）",
    )
    parser.add_argument(
        "--path", "-p",
        help="自定义 OpenAPI 规范端点路径（如 /custom-api-docs）",
    )
    parser.add_argument(
        "--output", "-o", default=str(_DEFAULT_OUTPUT),
        help=f"输出目录（默认: {_DEFAULT_OUTPUT}）",
    )
    parser.add_argument(
        "--group-by-service", action="store_true",
        help="按服务名/标签分组保存到子目录",
    )
    parser.add_argument(
        "--timeout", "-t", type=int, default=10,
        help="HTTP 请求超时秒数（默认: 10）",
    )
    parser.add_argument(
        "--crawl-ui", action="store_true",
        help="从 Swagger UI 页面抓取所有 JSON 链接（适用于自定义 Swagger 系统）",
    )

    args = parser.parse_args()
    output_dir = Path(args.output)

    # 检查是否至少提供了一个来源
    if not args.urls and not args.file:
        parser.print_help()
        print("\n[FAIL] 请提供至少一个 Swagger URL 或 --file 参数。")
        sys.exit(1)

    success_count = 0

    # 从 URL 导入
    for url in args.urls:
        success_count += import_from_url(
            url, output_dir, args.path, args.group_by_service, args.timeout, args.crawl_ui
        )

    # 从本地文件导入
    for filepath in args.file:
        if import_from_file(filepath, output_dir, args.group_by_service):
            success_count += 1

    print(f"\n{'='*50}")
    print(f"完成：成功导入 {success_count} 个规范文件到 {output_dir.resolve()}")
    if success_count > 0:
        print("重新启动 API 智能体后即可使用新的接口。")


if __name__ == "__main__":
    main()
