"""线索查询、阶段推进、补发加微链接。"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Lead, LeadStage
from app.schemas import LeadOut, LeadListOut, LeadPatch, SendLinkOut
from app.services.intake import _find_sales_name
from app.services.qrcode_gen import gen_qrcode_base64
from app.services.wecom import wecom

router = APIRouter(prefix="/api/leads", tags=["leads"])

LATER_STAGES = (LeadStage.CONTACTED, LeadStage.WECHAT_ADDED, LeadStage.QUALIFIED, LeadStage.QUOTED, LeadStage.WON)


@router.get("", response_model=LeadListOut)
def list_leads(
    db: Session = Depends(get_db),
    stage: Optional[str] = Query(None),
    assigned_to: Optional[str] = Query(None),
    mobile: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    stmt = select(Lead)
    if stage:
        stmt = stmt.where(Lead.stage == stage)
    if assigned_to:
        stmt = stmt.where(Lead.assigned_to == assigned_to)
    if mobile:
        stmt = stmt.where(Lead.mobile.contains(mobile))

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    items = db.execute(stmt.order_by(Lead.created_at.desc()).limit(limit).offset(offset)).scalars().all()
    return {"total": total, "items": items}


@router.get("/{lead_id}", response_model=LeadOut)
def get_lead(lead_id: int, db: Session = Depends(get_db)):
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(404, "线索不存在")
    return lead


@router.patch("/{lead_id}", response_model=LeadOut)
def update_lead(lead_id: int, body: LeadPatch, db: Session = Depends(get_db)):
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(404, "线索不存在")

    if body.stage:
        if body.stage not in LeadStage.ALL:
            raise HTTPException(400, f"非法阶段，可选: {', '.join(LeadStage.ALL)}")
        lead.stage = body.stage
        if body.stage in LATER_STAGES:
            lead.sla_alerted = True
        if body.stage == LeadStage.LOST and not body.lost_reason:
            raise HTTPException(400, "流失必须填写 lost_reason")

    if body.assigned_to is not None:
        lead.assigned_to = body.assigned_to
    if body.remark is not None:
        lead.remark = body.remark
    if body.lost_reason is not None:
        lead.lost_reason = body.lost_reason
    if body.wecom_external_userid is not None:
        lead.wecom_external_userid = body.wecom_external_userid

    db.commit()
    db.refresh(lead)
    return lead


@router.post("/{lead_id}/send-contact-link", response_model=SendLinkOut)
async def send_contact_link(lead_id: int, db: Session = Depends(get_db)):
    """手动补发活码：如果线索还没活码则创建，否则直接返回现有活码+token+二维码。"""
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(404, "线索不存在")
    if not lead.assigned_to:
        raise HTTPException(400, "线索未分配销售，请先分配")

    # 活码不存在 → 按 intake 的标准流程创建（活码 + token + 二维码缓存）
    if not lead.contact_way_url:
        state = f"lead_{lead.id}"
        lead.contact_way_url = await wecom.create_contact_way([lead.assigned_to], state)
        lead.contact_way_state = state
        lead.stage = LeadStage.ASSIGNED

    # 确保有 token（可能历史线索没有）
    if not lead.lead_token:
        lead.lead_token = str(uuid.uuid4())

    # 确保有二维码缓存
    if not lead.contact_qrcode:
        lead.contact_qrcode = gen_qrcode_base64(lead.contact_way_url)

    # 确保有销售展示名
    if not lead.sales_name:
        lead.sales_name = _find_sales_name(lead.assigned_to)

    db.commit()
    db.refresh(lead)

    return {
        "lead_id": lead.id,
        "contact_way_url": lead.contact_way_url,
        "lead_token": lead.lead_token,
        "contact_qrcode": lead.contact_qrcode,
        "sales_name": lead.sales_name,
    }
