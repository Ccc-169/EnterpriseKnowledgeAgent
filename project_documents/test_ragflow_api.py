"""
RAGFlow API 可用性测试脚本
对应 Dify_api.md 中的三个接口：
  1. 语义检索          POST /api/v1/retrieval
  2. 获取知识库文档列表  GET  /api/v1/datasets/{dataset_id}/documents
  3. 获取知识库列表     GET  /api/v1/datasets

直接运行即可（Key 和 dataset_id 已内置）：
  python test_ragflow_api.py

也可覆盖查询词：
  python test_ragflow_api.py --query "请假流程"
"""

import argparse
import json
import requests

BASE_URL   = "http://192.168.1.155/api/v1"
API_KEY    = "ragflow-FbmsGD7UpAzkWcVkanAJJAOrkG8S5tutyCEWvwaYAIA"
DATASET_ID = "89f0e612657011f19718d72a24560379"
TIMEOUT    = 30


def make_headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def print_sep(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)


def print_result(resp: requests.Response):
    print(f"状态码: {resp.status_code}")
    try:
        data = resp.json()
        print(json.dumps(data, ensure_ascii=False, indent=2)[:2000])
        if len(resp.text) > 2000:
            print("... (输出已截断)")
    except Exception:
        print(resp.text[:1000])


# ── 测试 1：获取知识库列表 ────────────────────────────────────────────────────

def test_list_datasets(api_key: str) -> str | None:
    """
    对应 Dify: GET /datasets
    RAGFlow:   GET /api/v1/datasets
    返回第一个 dataset 的 id，供后续测试使用。
    """
    print_sep("测试 1 / 3：获取知识库列表  GET /api/v1/datasets")
    try:
        resp = requests.get(
            f"{BASE_URL}/datasets",
            headers=make_headers(api_key),
            params={"page": 1, "page_size": 10},
            timeout=TIMEOUT,
        )
        print_result(resp)
        if resp.status_code == 200:
            data = resp.json()
            datasets = data.get("data", [])
            if datasets:
                first_id = datasets[0].get("id")
                first_name = datasets[0].get("name", "")
                print(f"\n✓ 成功，共返回 {len(datasets)} 个知识库")
                print(f"  第一个知识库：{first_name}（id={first_id}）")
                return first_id
            else:
                print("\n⚠ 接口正常，但暂无知识库")
                return None
        else:
            print(f"\n✗ 请求失败（HTTP {resp.status_code}）")
            return None
    except requests.exceptions.ConnectionError:
        print(f"\n✗ 无法连接到 {BASE_URL}，请确认服务器地址和端口")
        return None
    except Exception as e:
        print(f"\n✗ 异常：{e}")
        return None


# ── 测试 2：获取知识库文档列表 ───────────────────────────────────────────────

def test_list_documents(api_key: str, dataset_id: str):
    """
    对应 Dify: GET /datasets/{dataset_id}/documents
    RAGFlow:   GET /api/v1/datasets/{dataset_id}/documents
    """
    print_sep(f"测试 2 / 3：获取文档列表  GET /api/v1/datasets/{{dataset_id}}/documents")
    print(f"  dataset_id = {dataset_id}")
    try:
        resp = requests.get(
            f"{BASE_URL}/datasets/{dataset_id}/documents",
            headers=make_headers(api_key),
            params={"page": 1, "page_size": 10},
            timeout=TIMEOUT,
        )
        print_result(resp)
        if resp.status_code == 200:
            data = resp.json()
            docs = data.get("data", {}).get("docs", data.get("data", []))
            if isinstance(docs, list):
                print(f"\n✓ 成功，返回 {len(docs)} 条文档")
            else:
                print("\n✓ 请求成功")
        else:
            print(f"\n✗ 请求失败（HTTP {resp.status_code}）")
    except requests.exceptions.ConnectionError:
        print(f"\n✗ 无法连接到 {BASE_URL}")
    except Exception as e:
        print(f"\n✗ 异常：{e}")


# ── 测试 3：语义检索 ──────────────────────────────────────────────────────────

def test_retrieval(api_key: str, dataset_id: str, query: str):
    """
    对应 Dify: POST /datasets/{dataset_id}/retrieve
    RAGFlow:   POST /api/v1/retrieval
    注意：RAGFlow 检索不绑定单个 dataset，通过 dataset_ids 列表传入。
    """
    print_sep("测试 3 / 3：语义检索  POST /api/v1/retrieval")
    print(f"  dataset_ids = [{dataset_id}]")
    print(f"  query       = {query}")
    payload = {
        "question": query,
        "dataset_ids": [dataset_id],
        "page": 1,
        "page_size": 5,
        "similarity_threshold": 0.2,
        "vector_similarity_weight": 0.3,
        "keyword": False,
        "highlight": False,
    }
    try:
        resp = requests.post(
            f"{BASE_URL}/retrieval",
            headers=make_headers(api_key),
            json=payload,
            timeout=TIMEOUT,
        )
        print_result(resp)
        if resp.status_code == 200:
            data = resp.json()
            chunks = data.get("data", {}).get("chunks", [])
            print(f"\n✓ 成功，返回 {len(chunks)} 个检索片段")
            if chunks:
                print(f"  第一条片段预览（前100字）：{str(chunks[0].get('content', ''))[:100]}")
        else:
            print(f"\n✗ 请求失败（HTTP {resp.status_code}）")
    except requests.exceptions.ConnectionError:
        print(f"\n✗ 无法连接到 {BASE_URL}")
    except Exception as e:
        print(f"\n✗ 异常：{e}")


# ── 主流程 ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="RAGFlow API 可用性测试")
    parser.add_argument("--query", default="公司规章制度", help="检索测试用的查询词")
    args = parser.parse_args()

    print(f"目标服务器：{BASE_URL}")
    print(f"API Key：{API_KEY[:12]}{'*' * (len(API_KEY) - 12)}")
    print(f"Dataset ID：{DATASET_ID}")

    # 测试 1：获取知识库列表
    test_list_datasets(API_KEY)

    # 测试 2：文档列表
    test_list_documents(API_KEY, DATASET_ID)

    # 测试 3：语义检索
    test_retrieval(API_KEY, DATASET_ID, args.query)

    print("\n" + "="*60)
    print("  全部测试完成")
    print("="*60)


if __name__ == "__main__":
    main()
