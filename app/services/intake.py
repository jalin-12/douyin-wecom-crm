"""线索入库主流程：评分 → 分配 → 活码 → token → 二维码缓存。供抖音回调和人工补录用。

路径变更：原来的“活码 → 短信”改成“活码 → 缓存二维码 → 抖音小程序按需拉取”。
"""
import logging
import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Lead, LeadStage, utcnow
from app.services.assignment import pick_sales
from app.services.qrcode_gen import gen_qrcode_base64
from app.services.scoring import calc_intent_score
from app.services.wecom import wecom

logger = logging.getLogger("crm.intake")

WELCOME_TEXT = (
    "您好，我是您的专属顾问。这里只沟通图书卡批量采购、授权范围与开票问题，"
    "兑换码会在平台订单支付后按订单发放，不在聊天里发码。请问您计划采购多少套？"
)


def _find_sales_name(userid: str) -> str:
    """从 SALES_POOL 找销售的展示名，没配 name 就 fallback 到 userid。"""
    for s in settings.sales_pool:
        if s.get("userid") == userid:
            return s.get("name") or userid
    return userid


async def ingest_lead(db: Session, data: dict) -> tuple[Lead, bool]:
    """返回 (lead, 是否重复)。重复线索只刷新原始数据，不重复分配。"""
    douyin_lead_id = data.get("douyin_lead_id")
    if douyin_lead_id:
        exists = db.execute(select(Lead).where(Lead.douyin_lead_id == douyin_lead_id)).scalar_one_or_none()
        if exists:
            exists.raw = data.get("raw") or exists.raw
            db.commit()
            return exists, True

    lead = Lead(
        douyin_lead_id=douyin_lead_id,
        name=data.get("name", ""),
        mobile=data.get("mobile", ""),
        company=data.get("company", ""),
        customer_type=data.get("customer_type", "personal"),
        quantity=int(data.get("quantity", 1)),
        city=data.get("city", ""),
        raw=data.get("raw") or {},
    )
    lead.intent_score = calc_intent_score(lead.customer_type, lead.quantity, lead.mobile, lead.company)
    lead.assigned_to = pick_sales(db, lead.customer_type)
    lead.sales_name = _find_sales_name(lead.assigned_to) if lead.assigned_to else ""
    lead.sla_deadline = utcnow() + timedelta(minutes=settings.sla_minutes)

    db.add(lead)
    db.flush()  # 拿到 lead.id，用于活码 state

    if lead.assigned_to:
        lead.stage = LeadStage.ASSIGNED
        state = f"lead_{lead.id}"
        try:
            lead.contact_way_url = await wecom.create_contact_way([lead.assigned_to], state)
            lead.contact_way_state = state
            # 生成唯一 token 供抖音小程序安全匹配（不暴露手机号）
            lead.lead_token = str(uuid.uuid4())
            # 缓存二维码（活码 URL 固定，缓存一次够用）
            try:
                lead.contact_qrcode = gen_qrcode_base64(lead.contact_way_url)
                logger.info("活码+二维码生成成功 lead=%s token=%s", lead.id, lead.lead_token)
            except Exception:  # noqa: BLE001 二维码失败不阻断主流程
                logger.exception("生成二维码失败 lead=%s", lead.id)
        except Exception:  # noqa: BLE001 活码失败不能阻断线索入库
            logger.exception("创建联系我活码失败 lead=%s", lead.id)

    db.commit()
    db.refresh(lead)
    return lead, False
