"""数据模型：线索、订单、回调幂等记录。"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    """统一使用“无时区 UTC”，避免 SQLite 读写时区不一致。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class LeadStage:
    NEW = "NEW"                      # 已留资，待分配
    ASSIGNED = "ASSIGNED"            # 已分配销售，已下发加微链接
    CONTACTED = "CONTACTED"          # 销售已电话/短信触达
    WECHAT_ADDED = "WECHAT_ADDED"    # 客户已加企微
    QUALIFIED = "QUALIFIED"          # 需求确认（企业批量/授权咨询）
    QUOTED = "QUOTED"                # 已报价
    WON = "WON"                      # 已成交（平台订单已支付）
    LOST = "LOST"                    # 流失

    ALL = (NEW, ASSIGNED, CONTACTED, WECHAT_ADDED, QUALIFIED, QUOTED, WON, LOST)


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    douyin_lead_id: Mapped[str | None] = mapped_column(String(128), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(64), default="")
    mobile: Mapped[str] = mapped_column(String(20), index=True, default="")
    company: Mapped[str] = mapped_column(String(128), default="")
    customer_type: Mapped[str] = mapped_column(String(16), default="personal")  # enterprise/school/personal
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    city: Mapped[str] = mapped_column(String(64), default="")
    source: Mapped[str] = mapped_column(String(64), default="douyin_lead_form")

    intent_score: Mapped[int] = mapped_column(Integer, default=0)
    stage: Mapped[str] = mapped_column(String(16), default=LeadStage.NEW, index=True)
    assigned_to: Mapped[str | None] = mapped_column(String(64), index=True)
    sales_name: Mapped[str] = mapped_column(String(64), default="")
    contact_way_url: Mapped[str] = mapped_column(String(512), default="")
    contact_way_state: Mapped[str] = mapped_column(String(64), default="")
    contact_qrcode: Mapped[str] = mapped_column(Text, default="")  # 企微活码 PNG 的 base64
    lead_token: Mapped[str | None] = mapped_column(String(36), unique=True, index=True)  # 抖音小程序安全匹配 token

    sla_deadline: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    sla_alerted: Mapped[bool] = mapped_column(Boolean, default=False)
    wecom_external_userid: Mapped[str] = mapped_column(String(128), default="")
    lost_reason: Mapped[str] = mapped_column(String(256), default="")
    remark: Mapped[str] = mapped_column(Text, default="")

    raw: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    orders: Mapped[list["Order"]] = relationship(back_populates="lead")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    mobile: Mapped[str] = mapped_column(String(20), index=True)
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    redeem_code: Mapped[str] = mapped_column(String(128), default="")
    lead_id: Mapped[int | None] = mapped_column(ForeignKey("leads.id"), index=True)
    paid_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    lead: Mapped[Lead | None] = relationship(back_populates="orders")


class SyncState(Base):
    """拉取类接口的游标，避免重复拉取。"""

    __tablename__ = "sync_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    value: Mapped[str] = mapped_column(String(64), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class ProcessedEvent(Base):
    """第三方回调幂等表：同一事件只处理一次。"""

    __tablename__ = "processed_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_key: Mapped[str] = mapped_column(String(191), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
