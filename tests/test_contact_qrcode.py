"""测试新链路：线索入库 → 活码+token+二维码自动生成 → contact 接口查询"""
import base64

import pytest

from app.db import SessionLocal
from app.models import Lead


def test_contact_qrcode_by_token(client):
    """核心链路：留资 → 活码+token+二维码缓存 → 按 token 查询成功"""
    # 1. 推送抖音线索
    payload = {
        "clue_id": "dy-token-test-001",
        "name": "张经理",
        "telephone": "13700137000",
        "customer_type": "企业",
        "purchase_qty": "15",
        "company": "测试公司A",
        "city": "深圳",
    }
    lead_body = client.post("/webhook/douyin/lead", json=payload).json()
    assert lead_body["stage"] == "ASSIGNED"
    assert "lead_token" in lead_body, f"入库响应应带 lead_token，实际：{lead_body.keys()}"
    assert "contact_qrcode" in lead_body, "入库响应应带 contact_qrcode"

    lead_token = lead_body["lead_token"]
    lead_id = lead_body["lead_id"]

    # 2. 数据库里验证 token 和二维码已写入
    with SessionLocal() as db:
        lead = db.get(Lead, lead_id)
        assert lead is not None
        assert lead.lead_token == lead_token
        assert lead.contact_qrcode, "contact_qrcode 不应为空"
        assert len(lead.contact_qrcode) > 500, "二维码 base64 长度应足够大"
        assert lead.sales_name, f"sales_name 不应为空，assigned_to={lead.assigned_to}"

    # 3. contact 接口按 token 查询
    resp = client.get("/api/contact/qrcode", params={"token": lead_token})
    assert resp.status_code == 200, resp.text
    qr = resp.json()
    assert qr["ok"] is True
    assert qr["lead_id"] == lead_id
    assert qr["lead_token"] == lead_token
    assert qr["sales_name"]  # 有展示名
    assert qr["qrcode_base64"] == lead_body["contact_qrcode"]  # 和入库时一致
    assert "mock-contact" in qr["link"]  # mock 活码 URL
    # 二维码可解码（不是坏的 base64）
    decoded = base64.b64decode(qr["qrcode_base64"])
    assert decoded[:8] == b"\x89PNG\r\n\x1a\n", "返回的应是 PNG 格式"


def test_contact_qrcode_by_mobile(client):
    """按手机号 fallback 查询"""
    payload = {
        "clue_id": "dy-mobile-test-001",
        "name": "李老师",
        "telephone": "13700137999",
        "customer_type": "个人",
        "purchase_qty": "2",
        "company": "",
        "city": "北京",
    }
    lead_body = client.post("/webhook/douyin/lead", json=payload).json()
    lead_id = lead_body["lead_id"]

    resp = client.get("/api/contact/qrcode", params={"mobile": "13700137999"})
    assert resp.status_code == 200, resp.text
    qr = resp.json()
    assert qr["lead_id"] == lead_id
    assert qr["qrcode_base64"]


def test_contact_qrcode_not_found(client):
    """token 不存在 → 404"""
    resp = client.get("/api/contact/qrcode", params={"token": "nonexistent-token-12345"})
    assert resp.status_code == 404
    assert "未找到匹配" in resp.json()["detail"]


def test_contact_qrcode_missing_params(client):
    """token 和 mobile 都没传 → 找不到"""
    resp = client.get("/api/contact/qrcode")
    assert resp.status_code == 404


def test_contact_qrcode_no_link(client):
    """活码还没生成（lead.contact_way_url 为空）→ 400"""
    with SessionLocal() as db:
        lead = Lead(
            douyin_lead_id="dy-no-link-test",
            name="无活码测试",
            mobile="13700137888",
            customer_type="personal",
            quantity=1,
            intent_score=30,
            stage="NEW",  # 不是 ASSIGNED，没分配销售
            raw={},
        )
        db.add(lead)
        db.commit()
        db.flush()
        lead_token = str(__import__("uuid").uuid4())
        lead.lead_token = lead_token  # 手动加 token，但没活码
        db.commit()

    resp = client.get("/api/contact/qrcode", params={"token": lead_token})
    assert resp.status_code == 400
    assert "活码还在生成" in resp.json()["detail"]


def test_contact_qrcode_qrcode_cache_rebuild(client):
    """二维码缓存被手动清掉后，接口会现场补生成"""
    payload = {
        "clue_id": "dy-rebuild-test",
        "name": "重建缓存",
        "telephone": "13700137777",
        "customer_type": "enterprise",
        "purchase_qty": "8",
        "company": "测试重建公司",
        "city": "广州",
    }
    lead_body = client.post("/webhook/douyin/lead", json=payload).json()
    lead_id = lead_body["lead_id"]
    lead_token = lead_body["lead_token"]

    # 手动把 contact_qrcode 清掉
    with SessionLocal() as db:
        lead = db.get(Lead, lead_id)
        lead.contact_qrcode = ""
        db.commit()

    # 接口应该现场补生成，200 返回
    resp = client.get("/api/contact/qrcode", params={"token": lead_token})
    assert resp.status_code == 200, resp.text
    qr = resp.json()
    assert qr["qrcode_base64"], "补生成后应有二维码"

    # 数据库里也应该被补写回去
    with SessionLocal() as db:
        lead = db.get(Lead, lead_id)
        assert lead.contact_qrcode, "数据库里应被补写"


def test_intake_produces_token_and_qrcode(client):
    """直接测 intake_lead 新逻辑：入库后必有 token 和二维码"""
    from app.services.intake import ingest_lead
    import asyncio

    with SessionLocal() as db:
        lead, dup = asyncio.run(ingest_lead(db, {
            "douyin_lead_id": "direct-intake-test",
            "name": "直接入库",
            "mobile": "13600136000",
            "customer_type": "enterprise",
            "quantity": 20,
            "company": "直接入库公司",
            "raw": {"source": "test"},
        }))
        assert dup is False
        assert lead.lead_token, "lead_token 应自动生成"
        assert len(lead.lead_token) == 36, "lead_token 应为 uuid4 长度"
        assert lead.contact_qrcode, "contact_qrcode 应自动生成"
        assert lead.contact_way_url, "contact_way_url 应自动生成"
        assert lead.sales_name in ("sale_enterprise_1",), f"sales_name 应匹配 enterprise 组，实际 {lead.sales_name}"
        # contact_way_state 应带 lead id
        assert f"lead_{lead.id}" in lead.contact_way_state


def test_contact_endpoint_registered(client):
    """根接口里应列出新的 contact 路由"""
    root = client.get("/").json()
    api_list = root["api"]
    assert any("contact/qrcode" in a for a in api_list), f"根接口应列出 contact 路由，实际：{api_list}"
