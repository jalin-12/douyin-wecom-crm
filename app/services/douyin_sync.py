"""按时间窗拉取抖音客资中心线索并送入主流程。"""
import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models import SyncState, utcnow
from app.services.douyin_openapi import TIME_FMT, douyin_api, map_clue
from app.services.intake import ingest_lead

logger = logging.getLogger("crm.douyin.sync")
CURSOR_NAME = "douyin_clue_end"


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in (TIME_FMT, "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ValueError(f"时间格式错误：{value}，应为 yyyy-MM-dd HH:mm:ss")


def _get_state(db: Session) -> SyncState | None:
    return db.execute(select(SyncState).where(SyncState.name == CURSOR_NAME)).scalar_one_or_none()


async def sync_once(db: Session, start: str | None = None, end: str | None = None) -> dict:
    now = datetime.now()
    end_dt = parse_time(end) or (now - timedelta(minutes=settings.douyin_lag_minutes))

    start_dt = parse_time(start)
    if start_dt is None:
        state = _get_state(db)
        start_dt = (
            datetime.strptime(state.value, TIME_FMT)
            if state and state.value
            else end_dt - timedelta(minutes=settings.douyin_sync_lookback_minutes)
        )

    if start_dt >= end_dt:
        return {
            "created": 0, "duplicate": 0, "skipped": 0, "fetched": 0,
            "start_time": start_dt.strftime(TIME_FMT), "end_time": end_dt.strftime(TIME_FMT),
            "msg": "时间窗为空，未拉取",
        }

    clues = await douyin_api.pull(start_dt, end_dt)

    created = duplicate = skipped = 0
    for clue in clues:
        data = map_clue(clue)
        if not data["mobile"]:
            skipped += 1
            logger.warning("线索无手机号，跳过: %s", clue.get("clue_id"))
            continue
        _, dup = await ingest_lead(db, data)
        duplicate += int(dup)
        created += int(not dup)

    state = _get_state(db)
    if state is None:
        state = SyncState(name=CURSOR_NAME)
        db.add(state)
    state.value = end_dt.strftime(TIME_FMT)
    state.updated_at = utcnow()
    db.commit()

    result = {
        "created": created,
        "duplicate": duplicate,
        "skipped": skipped,
        "fetched": len(clues),
        "start_time": start_dt.strftime(TIME_FMT),
        "end_time": end_dt.strftime(TIME_FMT),
    }
    logger.info("抖音线索同步完成: %s", result)
    return result


async def sync_loop(stop_event) -> None:
    import asyncio

    while not stop_event.is_set():
        try:
            with SessionLocal() as db:
                await sync_once(db)
        except Exception:  # noqa: BLE001 后台任务不退出
            logger.exception("抖音线索同步异常")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=settings.douyin_sync_interval_seconds)
        except asyncio.TimeoutError:
            continue
