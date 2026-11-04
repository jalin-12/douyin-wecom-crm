"""抖音开放平台线索查询：解密与拉取入库。"""
import base64

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from app.config import settings
from app.services.douyin_openapi import decrypt_mobile, map_clue


def _encrypt(plain: str, secret: str) -> str:
    payload = plain.encode()
    pad = 16 - len(payload) % 16
    payload += bytes([pad]) * pad
    cipher = Cipher(algorithms.AES(secret.encode()), modes.CBC(secret[16:].encode()))
    encryptor = cipher.encryptor()
    return base64.b64encode(encryptor.update(payload) + encryptor.finalize()).decode()


def test_decrypt_mobile():
    secret = "12345678901234566543210987654321"
    cipher_text = _encrypt("13600136000", secret)
    assert decrypt_mobile(cipher_text, secret) == "13600136000"
    assert decrypt_mobile("13600136000", secret) == "13600136000"


def test_map_clue_fields():
    clue = {
        "clue_id": "c-1",
        "name": "李老师",
        "telephone": "13500135000",
        "city_name": "杭州",
        "poi_name": "某某教育集团",
        "remark_dict": {"客户类型": "企业", "采购数量": "30", "单位名称": "某某教育集团"},
    }
    data = map_clue(clue)
    assert data["douyin_lead_id"] == "c-1"
    assert data["mobile"] == "13500135000"
    assert data["company"] == "某某教育集团"
    assert data["customer_type"] == "enterprise"
    assert data["quantity"] == 30


def test_sync_douyin(client):
    settings_mock = settings.mock_douyin
    assert settings_mock is True

    first = client.post("/api/sync/douyin")
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["created"] == 1
    assert body["fetched"] == 1

    leads = client.get("/api/leads", params={"mobile": "13600136000"}).json()
    assert leads["total"] == 1
    lead = leads["items"][0]
    assert lead["douyin_lead_id"] == "mock-clue-001"
    assert lead["customer_type"] == "enterprise"
    assert lead["quantity"] == 20
    assert lead["assigned_to"] == "sale_enterprise_1"

    second = client.post("/api/sync/douyin").json()
    assert second["created"] == 0
    assert second["duplicate"] == 1

    status = client.get("/api/sync/douyin/status").json()
    assert status["cursor"] != ""
