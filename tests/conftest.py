import os
from pathlib import Path

TEST_DB = Path("/tmp/crm_test.db")
if TEST_DB.exists():
    TEST_DB.unlink()

os.environ["DB_URL"] = f"sqlite:///{TEST_DB}"
os.environ["WECOM_MOCK"] = "true"
os.environ["MOCK_DOUYIN"] = "true"
os.environ["SMS_PROVIDER"] = "console"
os.environ["SLA_MINUTES"] = "5"
os.environ["DOUYIN_WEBHOOK_SECRET"] = ""
os.environ["INTERNAL_API_KEY"] = ""
os.environ["SALES_POOL"] = (
    '[{"userid":"sale_enterprise_1","group":"enterprise","daily_limit":20},'
    '{"userid":"sale_personal_1","group":"personal","daily_limit":30}]'
)

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c
