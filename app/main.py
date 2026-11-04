"""FastAPI 应用入口。"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import func, select

from app.config import settings
from app.db import SessionLocal, engine
from app.models import Base, Lead
from app.routers import contact, leads, orders, stats, sync, webhook_douyin, webhook_wecom
from app.services.douyin_sync import sync_loop
from app.services.sla import sla_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    stop_event = asyncio.Event()
    tasks = [asyncio.create_task(sla_loop(stop_event))]
    if settings.douyin_sync_enabled:
        tasks.append(asyncio.create_task(sync_loop(stop_event)))
    logging.getLogger("crm").info(
        "启动完成 | db=%s | wecom_mock=%s | douyin_sync=%s | sla=%s分钟",
        settings.db_url, settings.wecom_mock, settings.douyin_sync_enabled, settings.sla_minutes,
    )
    yield
    stop_event.set()
    await asyncio.gather(*tasks)


app = FastAPI(title="抖音留资 → 企微转化 CRM", version="1.0.0", lifespan=lifespan)
app.include_router(webhook_douyin.router)
app.include_router(webhook_wecom.router)
app.include_router(leads.router)
app.include_router(orders.router)
app.include_router(stats.router)
app.include_router(sync.router)
app.include_router(contact.router)


@app.get("/health")
def health():
    with SessionLocal() as db:
        lead_count = db.execute(select(func.count(Lead.id))).scalar_one()
    return {"ok": True, "leads": lead_count, "wecom_mock": settings.wecom_mock}


@app.get("/")
def index():
    return {
        "name": "douyin-wecom-crm",
        "webhooks": ["POST /webhook/douyin/lead", "GET/POST /webhook/wecom/event"],
        "api": [
            "GET /api/leads", "GET /api/leads/{id}", "PATCH /api/leads/{id}",
            "POST /api/leads/{id}/send-contact-link", "POST /api/orders", "GET /api/stats/funnel",
            "POST /api/sync/douyin", "GET /api/sync/douyin/status",
            "GET /api/contact/qrcode?token=xxx 或 &mobile=xxx",  # 抖音小程序拉活码二维码
        ],
    }
