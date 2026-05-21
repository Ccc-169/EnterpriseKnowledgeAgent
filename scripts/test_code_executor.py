"""冒烟测试：验证 code_executor 进程池预热改造"""
import requests
import time
import json

# 复用 TCP 连接，消除建连开销
_http = requests.Session()

URL = "http://localhost:8001/execute"
BATCH_URL = "http://localhost:8001/execute_batch"


def test_basic_pandas():
    print("=== 测试1: 基础 pandas 执行 ===")
    code = (
        "import pandas as pd\n"
        "df = pd.DataFrame({'a': [1,2,3], 'b': [4,5,6]})\n"
        "result = {'status': 'success', 'summary': f'行数={len(df)}', 'data': df.to_dict()}\n"
        "print(json.dumps(result, ensure_ascii=False, default=str))\n"
    )
    t0 = time.time()
    r = _http.post(URL, json={"code": code, "data_path": "dummy.xlsx"})
    t1 = time.time()
    res = r.json()
    print(f"  耗时: {t1 - t0:.4f}s")
    print(f"  status: {res['status']}")
    assert res["status"] == "success", f"期望 success，实际 {res['status']}"
    print("  PASS\n")


def test_data_path_injection():
    print("=== 测试2: DATA_PATH 注入 ===")
    code = (
        "result = {'status': 'success', 'summary': 'DATA_PATH=' + str(DATA_PATH)}\n"
        "print(json.dumps(result, ensure_ascii=False))\n"
    )
    t0 = time.time()
    r = _http.post(URL, json={"code": code, "data_path": "C:/test/data.xlsx"})
    t1 = time.time()
    res = r.json()
    print(f"  耗时: {t1 - t0:.4f}s")
    print(f"  output: {res['output'][:80]}")
    assert "C:/test/data.xlsx" in res["output"], "DATA_PATH 未正确注入"
    print("  PASS\n")


def test_error_handling():
    print("=== 测试3: 错误处理 ===")
    code = "raise ValueError('测试异常')\n"
    t0 = time.time()
    r = _http.post(URL, json={"code": code, "data_path": "test.xlsx"})
    t1 = time.time()
    res = r.json()
    print(f"  耗时: {t1 - t0:.4f}s")
    print(f"  status: {res['status']}")
    assert res["status"] == "error", f"期望 error，实际 {res['status']}"
    assert "ValueError" in res.get("error", ""), "错误信息中应包含 ValueError"
    print("  PASS\n")


def test_batch_execute():
    print("=== 测试4: /execute_batch ===")
    code_a = "print(json.dumps({'a': 1}))"
    code_b = "print(json.dumps({'b': 2}))"
    r = _http.post(BATCH_URL, json={"codes": [code_a, code_b], "data_path": "test.xlsx"})
    res = r.json()
    print(f"  status: {res['status']}")
    print(f"  outputs: {res.get('outputs', [])}")
    assert res["status"] == "success"
    assert len(res.get("outputs", [])) == 2, "应返回 2 个输出"
    print("  PASS\n")


def test_multi_file_data_path():
    print("=== 测试5: 多文件 DATA_PATH (list) ===")
    code = (
        "result = {'status': 'success', 'is_list': isinstance(DATA_PATH, list), 'count': len(DATA_PATH)}\n"
        "print(json.dumps(result, ensure_ascii=False))\n"
    )
    paths = ["C:/data/1月.xlsx", "C:/data/2月.xlsx"]
    r = _http.post(URL, json={"code": code, "data_path": paths})
    res = r.json()
    print(f"  status: {res['status']}")
    print(f"  output: {res['output']}")
    assert res["status"] == "success"
    assert '"is_list": true' in res["output"], "DATA_PATH 应为 list 类型"
    print("  PASS\n")


if __name__ == "__main__":
    test_basic_pandas()
    test_data_path_injection()
    test_error_handling()
    test_batch_execute()
    test_multi_file_data_path()
    _http.close()
    print("=== 全部测试通过 ===")
