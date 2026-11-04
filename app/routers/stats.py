"""漏斗与 SLA 统计。"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Lead, LeadStage

router = APIRouter(prefix="/api/stats", tags=["stats"])


def _today_start() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None).replace(hour=0, minute=0, second=0, microsecond=0)


@router.get("/funnel")
def funnel(db: Session = Depends(get_db)):
    rows = db.execute(select(Lead.stage, func.count(Lead.id)).group_by(Lead.stage)).all()
    counts = {stage: 0 for stage in LeadStage.ALL}
    counts.update({stage: count for stage, count in rows})

    total = sum(counts.values())
    won = counts[LeadStage.WON]
    reached_wechat = sum(counts[s] for s in LeadStage.ALL if s in (
        LeadStage.WECHAT_ADDED, LeadStage.QUALIFIED, LeadStage.QUOTED, LeadStage.WON
    ))

    today_new = db.execute(
        select(func.count(Lead.id)).where(Lead.created_at >= _today_start())
    ).scalar_one()
    today_won = db.execute(
        select(func.count(Lead.id)).where(Lead.created_at >= _today_start(), Lead.stage == LeadStage.WON)
    ).scalar_one()
    sla_breached = db.execute(
        select(func.count(Lead.id)).where(Lead.sla_alerted.is_(True), Lead.stage == LeadStage.NEW)
    ).scalar_one()

    return {
        "total": total,
        "stages": [{"stage": stage, "count": counts[stage]} for stage in LeadStage.ALL],
        "won": won,
        "win_rate": round(won / total, 4) if total else 0.0,
        "wechat_add_rate": round(reached_wechat / total, 4) if total else 0.0,
        "today_new": today_new,
        "today_won": today_won,
        "sla_breached_unhandled": sla_breached,
    }
