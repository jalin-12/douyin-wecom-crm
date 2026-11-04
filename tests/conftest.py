"""测试配置 - import app 之前设好环境变量，用 file DB 不依赖 patch。"""
import os
import tempfile

# ===== 关键：在 import app 之前就固定好所有环境变量 =====
# DB 用 file SQLite（:memory: 在单例 engine 下会导致后续操作找不到表）
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["DB_URL"] = f"sqlite:///{_tmp.name}"
os.environ["WECOM_MOCK"] = "true"
os.environ["MOCK_DOUYIN"] = "true"
os.environ["SMS_PROVIDER"] = "console"
os.environ["SLA_MINUTES"] = "5"
os.environ["DOUYIN_WEBHOOK_SECRET"] = ""
os.environ["INTERNAL_API_KEY"] = ""
os.environ["MOCK_INTERNAL_KEY"] = "true"
os.environ["SALES_POOL"] = (
    '[{"userid":"sale_enterprise_1","group":"enterprise","daily_limit":20},'
    '{"userid":"sale_personal_1","group":"personal","daily_limit":30}]'
)

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session", autouse=True)
def _cleanup_db_session():
    """整个测试 session 共享同一个 DB 文件（简单、可靠、不需要 patch）。

    注意：这意味着测试之间数据会累积。每个测试在开头自己用唯一 ID 避免冲突。
    """
    yield
    # session 结束后清理
    try:
        os.unlink(_tmp.name)
    except OSError:
        pass


@pytest.fixture(scope="session")
def client():
    """session 级别的 TestClient，DB 在 lifespan 里 create_all 一次。"""
    from app.main import app
    with TestClient(app) as c:
        yield c
