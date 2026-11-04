"""平台订单回调：按手机号归因成交，兑换码只在订单侧交付。"""
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import Lead, LeadStage, Order, ProcessedEvent, utcnow
from app.schemas import OrderIn

router = APIRouter(prefix="/api/orders", tags=["orders"])


@router.post("")
def create_order(
    body: OrderIn,
    db: Session = Depends(get_db),
    x_api_key: str = Header("", alias="X-Api-Key"),
):
    if settings.internal_api_key and x_api_key != settings.internal_api_key:
        raise HTTPException(401, "invalid api key")

    exists = db.execute(select(Order).where(Order.order_id == body.order_id)).scalar_one_or_none()
    if exists:
        return {"ok": True, "duplicate": True, "order_id": exists.order_id, "lead_id": exists.lead_id}

    lead = db.execute(
        select(Lead).where(Lead.mobile == body.mobile).order_by(Lead.created_at.desc())
    ).scalars().first()

    order = Order(
        order_id=body.order_id,
        mobile=body.mobile,
        amount=body.amount,
        redeem_code=body.redeem_code,
        lead_id=lead.id if lead else None,
    )
    db.add(order)

    if lead:
        lead.stage = LeadStage.WON
        lead.sla_alerted = True
        lead.remark = (lead.remark + f"\n成交订单 {body.order_id}，金额 {body.amount}").strip()
    db.add(ProcessedEvent(event_key=f"order:{body.order_id}", kind="order"))
    db.commit()

    # 兑换码交付只走平台订单/短信，接口只做归因，不回传码给销售侧
    return {
        "ok": True,
        "duplicate": False,
        "order_id": body.order_id,
        "lead_id": lead.id if lead else None,
        "attributed": lead is not None,
        "mobile_masked": body.mobile[:3] + "****" + body.mobile[-4:],
        "paid_at": utcnow().isoformat(),
    }
