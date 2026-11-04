"""销售分配：按客户类型分组 + 当日上限 + 轮询。"""
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Lead


def _today_start() -> datetime:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def pick_sales(db: Session, customer_type: str) -> str | None:
    group = "enterprise" if customer_type in ("enterprise", "school") else "personal"
    pool = [s for s in settings.sales_pool if s.get("group") == group]
    if not pool:
        pool = list(settings.sales_pool)
    if not pool:
        return None

    rows = db.execute(
        select(Lead.assigned_to, func.count(Lead.id))
        .where(Lead.assigned_to.is_not(None), Lead.created_at >= _today_start())
        .group_by(Lead.assigned_to)
    ).all()
    today_count = {userid: count for userid, count in rows}

    # 优先取当日负载最低且未超上限的销售
    candidates = [
        s for s in pool
        if today_count.get(s["userid"], 0) < int(s.get("daily_limit", 999))
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda s: (today_count.get(s["userid"], 0), s["userid"]))
    return candidates[0]["userid"]
