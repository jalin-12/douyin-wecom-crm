"""手动/定时触发抖音线索拉取，便于联调与补数据。"""
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import SyncState
from app.services.douyin_sync import CURSOR_NAME, parse_time, sync_once

router = APIRouter(prefix="/api/sync", tags=["sync"])


def _check_key(key: str) -> None:
    if settings.internal_api_key and key != settings.internal_api_key:
        raise HTTPException(401, "invalid api key")


@router.post("/douyin")
async def sync_douyin(
    start: str | None = Query(None, description="开始时间 yyyy-MM-dd HH:mm:ss"),
    end: str | None = Query(None, description="结束时间 yyyy-MM-dd HH:mm:ss"),
    db: Session = Depends(get_db),
    x_api_key: str = Header("", alias="X-Api-Key"),
):
    _check_key(x_api_key)
    try:
        parse_time(start)
        parse_time(end)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return await sync_once(db, start, end)


@router.get("/douyin/status")
def sync_status(db: Session = Depends(get_db)):
    state = db.execute(select(SyncState).where(SyncState.name == CURSOR_NAME)).scalar_one_or_none()
    return {
        "cursor": state.value if state else "",
        "updated_at": state.updated_at.isoformat() if state else None,
        "enabled": settings.douyin_sync_enabled,
        "mock": settings.mock_douyin,
        "lag_minutes": settings.douyin_lag_minutes,
    }
