"""企业微信事件回调：加好友 → 欢迎语 → 打标签 → 阶段推进。"""
import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import Lead, LeadStage, ProcessedEvent
from app.services.intake import WELCOME_TEXT
from app.services.wecom import wecom
from app.services.wecom_crypto import WeComCrypto, parse_xml

router = APIRouter(prefix="/webhook/wecom", tags=["wecom"])
logger = logging.getLogger("crm.wecom.callback")


def _crypto() -> WeComCrypto | None:
    if not settings.wecom_token or not settings.wecom_aes_key:
        return None
    return WeComCrypto(settings.wecom_token, settings.wecom_aes_key, settings.wecom_corp_id)


@router.get("/event")
async def verify_event(msg_signature: str = "", timestamp: str = "", nonce: str = "", echostr: str = ""):
    crypto = _crypto()
    if crypto is None:
        return PlainTextResponse(echostr)
    if not crypto.verify(msg_signature, timestamp, nonce, echostr):
        return PlainTextResponse("invalid signature", status_code=401)
    return PlainTextResponse(crypto.decrypt(echostr))


@router.post("/event")
async def receive_event(
    request: Request,
    msg_signature: str = "",
    timestamp: str = "",
    nonce: str = "",
    db: Session = Depends(get_db),
):
    raw = (await request.body()).decode("utf-8")
    crypto = _crypto()
    if crypto is not None:
        encrypted = parse_xml(raw).get("Encrypt", "")
        if not crypto.verify(msg_signature, timestamp, nonce, encrypted):
            return PlainTextResponse("invalid signature", status_code=401)
        raw = crypto.decrypt(encrypted)

    data = parse_xml(raw)
    event = data.get("Event", "")
    change = data.get("ChangeType", "")
    external_userid = data.get("ExternalUserID", "")
    userid = data.get("UserID", "")
    state = data.get("State", "")
    welcome_code = data.get("WelcomeCode", "")

    event_key = f"wecom:{event}:{change}:{external_userid}:{state}"
    if event_key.strip(":") and db.execute(
        select(ProcessedEvent).where(ProcessedEvent.event_key == event_key)
    ).scalar_one_or_none():
        return PlainTextResponse("success")

    lead = None
    if state.startswith("lead_"):
        try:
            lead = db.get(Lead, int(state.split("_", 1)[1]))
        except ValueError:
            lead = None
    if lead is None and data.get("Mobile"):
        lead = db.execute(select(Lead).where(Lead.mobile == data["Mobile"])).scalars().first()

    if lead and event == "change_external_contact":
        lead.wecom_external_userid = external_userid or lead.wecom_external_userid
        if change == "add_external_contact":
            lead.stage = LeadStage.WECHAT_ADDED
            lead.sla_alerted = True
            if welcome_code:
                try:
                    await wecom.send_welcome_msg(welcome_code, WELCOME_TEXT)
                except Exception:  # noqa: BLE001
                    logger.exception("发送欢迎语失败 lead=%s", lead.id)
            try:
                tag = "企业采购" if lead.customer_type in ("enterprise", "school") else "个人咨询"
                await wecom.mark_tag(userid or lead.assigned_to or "", external_userid, [tag])
            except Exception:  # noqa: BLE001
                logger.exception("打标签失败 lead=%s", lead.id)
        elif change == "del_external_contact":
            lead.remark = (lead.remark + "\n客户已删除企微好友").strip()

    db.add(ProcessedEvent(event_key=event_key, kind=event))
    db.commit()
    return PlainTextResponse("success")
