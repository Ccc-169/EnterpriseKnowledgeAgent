"""
tests/conftest.py — pytest 公共 fixtures

提供:
  - 临时 SQLite 数据库（每个测试一个全新的 DB_PATH）
  - 自动调用 init_db() 建表
  - 测试结束后清理临时文件
"""

import os
import sys
import tempfile

import pytest


# 把项目根目录加入 sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


@pytest.fixture(autouse=True)
def _isolate_module_state():
    """
    每个 test 启动时强制隔离:
      - 清空 KB fingerprint 进程内 lru 缓存（避免 test 间状态污染）
      - reload core.config（让 monkeypatch.setattr("core.config.X", ...) 生效到所有 from core.config import 处）
    """
    # 必须在 import 之前 import 模块
    from data import kb_version
    kb_version.invalidate_kb_fingerprint_cache()

    yield

    # 清理: 再清一次
    kb_version.invalidate_kb_fingerprint_cache()


@pytest.fixture
def temp_db(monkeypatch):
    """
    每个测试一个全新的临时 SQLite DB 文件。
    通过环境变量 DB_PATH 切到临时文件，再调用 init_db 建表。
    """
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setenv("DB_PATH", path)

    # 强制重新加载 core.config 和 core.database，让 DB_PATH 生效
    import importlib
    import core.config
    importlib.reload(core.config)
    import core.database
    importlib.reload(core.database)
    core.database.init_db()

    yield path

    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


@pytest.fixture
def fake_ragflow_docs(monkeypatch):
    """
    替换 compute_kb_fingerprint 内的 RAGFlow 请求，返回指定的文档列表。
    """
    state = {"docs": []}

    def _set(docs):
        state["docs"] = docs

    def _fake_get(*args, **kwargs):
        from unittest.mock import MagicMock
        resp = MagicMock()
        resp.raise_for_status = lambda: None
        resp.json.return_value = {"data": {"docs": state["docs"]}}
        return resp

    monkeypatch.setattr("requests.get", _fake_get)
    return _set
