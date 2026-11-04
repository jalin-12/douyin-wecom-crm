"""5 分钟首响 SLA：后台扫描超时未联系线索并告警。"""
import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.models import Lead, LeadStage

logger = logging.getLogger("crm.sla")


def _naive_utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def scan_once() -> list[dict]:
    alerted: list[dict] = []
    with SessionLocal() as db:
        stale = db.execute(
            select(Lead).where(
                Lead.sla_alerted.is_(False),
                Lead.sla_deadline.is_not(None),
                Lead.sla_deadline < _naive_utc_now(),
                Lead.stage.in_([LeadStage.NEW, LeadStage.ASSIGNED]),
            )
        ).scalars().all()
        for lead in stale:
            lead.sla_alerted = True
            alerted.append({"lead_id": lead.id, "assigned_to": lead.assigned_to, "mobile": lead.mobile})
            logger.warning("SLA 超时: lead=%s sales=%s mobile=%s", lead.id, lead.assigned_to, lead.mobile)
        db.commit()
    if alerted:
        print(f"[SLA] 超时线索 {len(alerted)} 条，已推送告警: {alerted}")
    return alerted


async def sla_loop(stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            await asyncio.to_thread(scan_once)
        except Exception:  # noqa: BLE001 后台任务不能因为单次异常退出
            logger.exception("SLA 扫描异常")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=settings.sla_scan_seconds)
        except asyncio.TimeoutError:
            continue
