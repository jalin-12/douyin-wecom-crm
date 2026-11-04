"""接口出入参模型。"""
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LeadPatch(BaseModel):
    stage: str | None = None
    assigned_to: str | None = None
    remark: str | None = None
    lost_reason: str | None = None
    wecom_external_userid: str | None = None


class OrderIn(BaseModel):
    order_id: str
    mobile: str
    amount: float = 0.0
    redeem_code: str = ""
    paid_at: str | None = None


class LeadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    douyin_lead_id: str | None
    name: str
    mobile: str
    company: str
    customer_type: str
    quantity: int
    city: str
    source: str
    intent_score: int
    stage: str
    assigned_to: str | None
    sales_name: str
    contact_way_url: str
    contact_way_state: str
    contact_qrcode: str
    lead_token: str | None
    wecom_external_userid: str
    remark: str
    created_at: Any
    updated_at: Any


class LeadListOut(BaseModel):
    total: int
    items: list[LeadOut]


class SendLinkOut(BaseModel):
    """手动补发活码：返回活码 URL、token、二维码，供销售在 CRM 里复制给客户。"""
    lead_id: int
    contact_way_url: str
    lead_token: str
    contact_qrcode: str
    sales_name: str
