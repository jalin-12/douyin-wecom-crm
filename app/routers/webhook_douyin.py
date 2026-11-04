"""抖音来客留资回调入口。"""
import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.services.douyin import parse_lead
from app.services.intake import ingest_lead

router = APIRouter(prefix="/webhook/douyin", tags=["douyin"])
logger = logging.getLogger("crm.douyin")


def _verify(raw: bytes, signature: str) -> bool:
    if not settings.douyin_webhook_secret:
        return True
    expected = hmac.new(settings.douyin_webhook_secret.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


@router.post("/lead")
async def douyin_lead(request: Request, db: Session = Depends(get_db)):
    raw = await request.body()
    try:
        payload = json.loads(raw or b"{}")
    except json.JSONDecodeError:
        return JSONResponse({"code": 400, "msg": "invalid json"}, status_code=400)

    # 开放平台配置回调地址时的校验请求，需原样返回 challenge
    if payload.get("event") == "verify_webhook":
        return {"challenge": (payload.get("content") or {}).get("challenge")}

    if not _verify(raw, request.headers.get("x-signature", "")):
        return JSONResponse({"code": 401, "msg": "invalid signature"}, status_code=401)

    data = parse_lead(payload)
    if not data["mobile"]:
        logger.warning("留资缺少手机号: %s", payload)
        return JSONResponse({"code": 0, "msg": "ignored: no mobile"}, status_code=200)

    lead, duplicate = await ingest_lead(db, data)
    return {
        "code": 0,
        "duplicate": duplicate,
        "lead_id": lead.id,
        "stage": lead.stage,
        "assigned_to": lead.assigned_to,
        "sales_name": lead.sales_name,
        "intent_score": lead.intent_score,
        "contact_way_url": lead.contact_way_url,
        "lead_token": lead.lead_token,
        "contact_qrcode": lead.contact_qrcode,
    }
