"""端到端：留资 → 分配 → SLA → 加微 → 成交归因 → 漏斗。"""
from datetime import timedelta

from app.db import SessionLocal
from app.models import Lead, utcnow
from app.services.sla import scan_once
from app.services.wecom_crypto import WeComCrypto


def test_full_flow(client):
    payload = {
        "clue_id": "dy-001",
        "name": "王老师",
        "telephone": "13800138000",
        "customer_type": "学校",
        "purchase_qty": "30",
        "company": "杭州实验学校",
        "city": "杭州",
        "form_data": [{"field": "采购用途", "value": "教学办公"}],
    }
    resp = client.post("/webhook/douyin/lead", json=payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 0
    assert body["duplicate"] is False
    assert body["stage"] == "ASSIGNED"
    assert body["assigned_to"] == "sale_enterprise_1"
    assert body["intent_score"] == 90
    assert "mock-contact" in body["contact_way_url"]
    lead_id = body["lead_id"]

    # 重复推送同一 clue_id 不重复分配
    dup = client.post("/webhook/douyin/lead", json=payload).json()
    assert dup["duplicate"] is True and dup["lead_id"] == lead_id

    # 查询线索
    listed = client.get("/api/leads", params={"stage": "ASSIGNED", "mobile": "13800138000"}).json()
    assert listed["total"] == 1
    assert listed["items"][0]["mobile"] == "13800138000"

    # 销售标记已电话触达
    patched = client.patch(f"/api/leads/{lead_id}", json={"stage": "CONTACTED"}).json()
    assert patched["stage"] == "CONTACTED"

    # 企微加好友回调：推进到 WECHAT_ADDED
    xml = f"""<xml>
      <ToUserName><![CDATA[ww]]></ToUserName>
      <FromUserName><![CDATA[sys]]></FromUserName>
      <CreateTime>1700000000</CreateTime>
      <MsgType><![CDATA[event]]></MsgType>
      <Event><![CDATA[change_external_contact]]></Event>
      <ChangeType><![CDATA[add_external_contact]]></ChangeType>
      <UserID><![CDATA[sale_enterprise_1]]></UserID>
      <ExternalUserID><![CDATA[wmABC123]]></ExternalUserID>
      <State><![CDATA[lead_{lead_id}]]></State>
      <WelcomeCode><![CDATA[wc001]]></WelcomeCode>
    </xml>"""
    resp = client.post("/webhook/wecom/event", content=xml)
    assert resp.status_code == 200 and resp.text == "success"
    lead = client.get(f"/api/leads/{lead_id}").json()
    assert lead["stage"] == "WECHAT_ADDED"
    assert lead["wecom_external_userid"] == "wmABC123"

    # 同一事件重复回调幂等
    again = client.post("/webhook/wecom/event", content=xml)
    assert again.status_code == 200

    # 平台订单回调，按手机号归因成交
    order = client.post("/api/orders", json={"order_id": "OD-001", "mobile": "13800138000", "amount": 1999}).json()
    assert order["attributed"] is True and order["lead_id"] == lead_id
    assert order["mobile_masked"] == "138****8000"

    # 重复订单幂等
    dup_order = client.post("/api/orders", json={"order_id": "OD-001", "mobile": "13800138000", "amount": 1999}).json()
    assert dup_order["duplicate"] is True

    funnel = client.get("/api/stats/funnel").json()
    assert funnel["won"] == 1
    assert funnel["today_won"] == 1
    won_stage = next(item for item in funnel["stages"] if item["stage"] == "WON")
    assert won_stage["count"] == 1


def test_webhook_challenge(client):
    resp = client.post(
        "/webhook/douyin/lead",
        json={"event": "verify_webhook", "client_key": "test", "content": {"challenge": 12345}},
    )
    assert resp.status_code == 200
    assert resp.json() == {"challenge": 12345}


def test_sla_timeout_alert():
    with SessionLocal() as db:
        lead = Lead(
            name="李经理",
            mobile="13900139000",
            company="某某商贸",
            customer_type="enterprise",
            quantity=5,
            intent_score=70,
            stage="ASSIGNED",
            assigned_to="sale_personal_1",
            sla_deadline=utcnow() - timedelta(minutes=10),
            raw={},
        )
        db.add(lead)
        db.commit()
        lead_id = lead.id

    alerted = scan_once()
    assert alert_ids(alerted) >= {lead_id}
    with SessionLocal() as db:
        assert db.get(Lead, lead_id).sla_alerted is True


def alert_ids(alerted):
    return {item["lead_id"] for item in alerted}


def test_wecom_crypto_roundtrip():
    key = "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG"[:43]
    crypto = WeComCrypto("tok", key, "ww123")
    encrypted, signature = crypto.encrypt("<xml><Event>ping</Event></xml>", "1700000000", "nonce1")
    assert crypto.verify(signature, "1700000000", "nonce1", encrypted)
    assert crypto.decrypt(encrypted) == "<xml><Event>ping</Event></xml>"
    assert crypto.verify("bad", "1700000000", "nonce1", encrypted) is False
