"""测试固件。

注意：环境变量必须在导入任何 app 模块**之前**设置完成 —— settings 与
engine 都是模块级单例，导入即固化。
"""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

# ---------------------------------------------------------------- 环境隔离
_TEST_DIR = Path(tempfile.mkdtemp(prefix="skilltwin_test_"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TEST_DIR / 'test.db').as_posix()}"
os.environ["LLM_PROVIDER"] = "echo"  # 测试默认不触发任何网络调用
os.environ["DEMO_MODE"] = "live"
os.environ["DEBUG"] = "false"
os.environ["LOG_LEVEL"] = "WARNING"

# 遮蔽 .env 里的真实凭据。测试**绝不允许**打真实接口：
# 既会烧 token，也会让测试结果依赖网络。
# base_url 指向 discard 端口，万一有代码绕过 EchoProvider 也会立刻失败而非静默联网。
os.environ["LLM_API_KEY"] = "test-dummy-key-not-real"
os.environ["LLM_BASE_URL"] = "http://127.0.0.1:9/unused"
os.environ["EMBEDDING_PROVIDER"] = "hash"  # 不加载本地模型，保持测试轻快

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.db import SessionLocal, create_all, drop_all, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema() -> Iterator[None]:
    create_all()
    yield
    drop_all()
    engine.dispose()
    shutil.rmtree(_TEST_DIR, ignore_errors=True)


@pytest.fixture
def db() -> Iterator[Session]:
    """每个用例独立会话，结束后清空数据，保证用例之间互不干扰。"""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        # 按外键依赖倒序清理
        from app.core.db import Base

        for table in reversed(Base.metadata.sorted_tables):
            session.execute(table.delete())
        session.commit()
        session.close()


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c
