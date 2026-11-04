"""完整链路端到端冒烟（TestClient，不启真实 socket）。"""
import base64


def test_full_miniapp_path(client):
    """完整链路：留资 → 活码+token+二维码 → 小程序按 token 拉取 → mobile fallback → 手动补发 → 企微回调自动匹配 → 404 拒绝"""

    # Step 1: 抖音留资入库
    payload = {
        "clue_id": "smoke-live-001",
        "name": "王总",
        "telephone": "15500001111",
        "customer_type": "企业",
        "purchase_qty": "25",
        "company": "某某科技有限公司",
        "city": "杭州",
    }
    lead = client.post("/webhook/douyin/lead", json=payload).json()
    assert lead["stage"] == "ASSIGNED"
    assert lead["sales_name"], "sales_name 应自动填充"
    assert lead["lead_token"], "lead_token 应自动生成"
    assert lead["contact_qrcode"], "contact_qrcode 应自动生成"
    token = lead["lead_token"]
    lead_id = lead["lead_id"]
    print(f"[1] ✓ 线索入库 lead_id={lead_id} sales={lead['sales_name']}")

    # Step 2: 按 token 查二维码（抖音小程序真实调用）
    qr = client.get("/api/contact/qrcode", params={"token": token})
    assert qr.status_code == 200 and qr.json()["ok"]
    data = qr.json()
    assert data["lead_id"] == lead_id
    assert len(data["qrcode_base64"]) > 1000
    png = base64.b64decode(data["qrcode_base64"])
    assert png[:8] == b"\x89PNG\r\n\x1a\n", "应返回合法 PNG"
    print(f"[2] ✓ 按 token 查二维码  PNG={len(png)}B")

    # Step 3: 按手机号 fallback
    qr2 = client.get("/api/contact/qrcode", params={"mobile": "15500001111"})
    assert qr2.status_code == 200 and qr2.json()["lead_id"] == lead_id
    print(f"[3] ✓ 按 mobile fallback")

    # Step 4: 手动补发
    resend = client.post(f"/api/leads/{lead_id}/send-contact-link").json()
    assert resend["lead_token"] == token
    assert resend["contact_qrcode"] == lead["contact_qrcode"]
    print(f"[4] ✓ 手动补发 token/二维码一致")

    # Step 5: 企微加好友回调，state=lead_{id} 自动推进
    xml = f"""<xml>
<ToUserName><![CDATA[ww]]></ToUserName>
<FromUserName><![CDATA[sys]]></FromUserName>
<CreateTime>1700000000</CreateTime>
<MsgType><![CDATA[event]]></MsgType>
<Event><![CDATA[change_external_contact]]></Event>
<ChangeType><![CDATA[add_external_contact]]></ChangeType>
<UserID><![CDATA[{lead['assigned_to']}]]></UserID>
<ExternalUserID><![CDATA[wmFAKE999]]></ExternalUserID>
<State><![CDATA[lead_{lead_id}]]></State>
<WelcomeCode><![CDATA[wcTEST]]></WelcomeCode>
</xml>"""
    resp = client.post("/webhook/wecom/event", content=xml)
    assert resp.status_code == 200 and resp.text == "success"

    final = client.get(f"/api/leads/{lead_id}").json()
    assert final["stage"] == "WECHAT_ADDED"
    assert final["wecom_external_userid"] == "wmFAKE999"
    print(f"[5] ✓ 企微回调自动推进 WECHAT_ADDED")

    # Step 6: 错误路径拒绝
    bad = client.get("/api/contact/qrcode", params={"token": "nonexistent-xxx"})
    assert bad.status_code == 404
    bad2 = client.get("/api/contact/qrcode")  # 无参数
    assert bad2.status_code == 404
    print(f"[6] ✓ 错误路径正确拒绝")

    print(f"\n✅ 完整链路 6/6 全部通过")
