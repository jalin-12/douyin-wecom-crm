"""抖音小程序 → CRM 活码二维码查询接口。

给小雪花挂载的抖音小程序用，按 lead_token（推荐，安全不暴露手机号）或 mobile 匹配线索，
返回该线索对应的企微活码二维码（base64）+ 活码 URL + 销售展示名。
"""
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import Lead

logger = logging.getLogger("crm.contact")
router = APIRouter(prefix="/api/contact", tags=["contact"])


def _check_internal_key(x_internal_key: Annotated[str | None, Header()] = None) -> None:
    """开发环境默认跳过鉴权，生产环境强制校验 X-Internal-Key。"""
    if settings.mock_internal_key:
        return
    if not settings.internal_api_key:
        logger.warning("生产环境请设置 INTERNAL_API_KEY")
        return
    if x_internal_key != settings.internal_api_key:
        raise HTTPException(status_code=401, detail="X-Internal-Key 不匹配")


@router.get("/qrcode")
def get_contact_qrcode(
    token: str | None = Query(default=None, description="线索安全 token，抖音小程序优先用这个"),
    mobile: str | None = Query(default=None, description="用户手机号（抖音小程序授权后可传，fallback 用）"),
    db: Session = Depends(get_db),
    _: None = Depends(_check_internal_key),
) -> dict:
    """返回匹配线索的企微活码二维码和元信息。

    抖音小程序前端用法：
        <image :src="'data:image/png;base64,' + qrcode_base64" />
    """
    lead: Lead | None = None

    # 优先用 token 精确匹配（安全、唯一）
    if token:
        lead = db.execute(select(Lead).where(Lead.lead_token == token)).scalar_one_or_none()
    elif mobile:
        # 手机号匹配：取最新一条已分配且有活码的线索（同手机号可能多次留资）
        lead = db.execute(
            select(Lead)
            .where(Lead.mobile == mobile, Lead.contact_way_url != "")
            .order_by(Lead.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()

    if not lead:
        raise HTTPException(status_code=404, detail="未找到匹配的线索")
    if not lead.contact_way_url:
        raise HTTPException(status_code=400, detail="该线索的企微活码还在生成，请稍后再试")

    # 如果二维码缓存丢了（理论上不会，除非数据库直接被改），现场再生成一次补缓存
    qrcode_b64 = lead.contact_qrcode
    if not qrcode_b64:
        logger.warning("lead=%s 二维码缓存缺失，现场补生成", lead.id)
        from app.services.qrcode_gen import gen_qrcode_base64
        qrcode_b64 = gen_qrcode_base64(lead.contact_way_url)
        lead.contact_qrcode = qrcode_b64
        db.commit()

    return {
        "ok": True,
        "lead_id": lead.id,
        "sales_name": lead.sales_name or lead.assigned_to or "专属顾问",
        "qrcode_base64": qrcode_b64,
        "link": lead.contact_way_url,
        "lead_token": lead.lead_token,
    }
