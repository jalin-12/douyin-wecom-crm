"""短信通道：开发用 console，生产替换为 http 网关。"""
import logging

import httpx

from app.config import settings

logger = logging.getLogger("crm.sms")


class ConsoleSmsProvider:
    name = "console"

    async def send(self, mobile: str, content: str) -> bool:
        logger.info("[SMS][%s] %s", mobile, content)
        print(f"[SMS] -> {mobile}: {content}")
        return True


class HttpSmsProvider:
    name = "http"

    async def send(self, mobile: str, content: str) -> bool:
        if not settings.sms_http_url:
            logger.error("SMS_HTTP_URL 未配置，短信未发送")
            return False
        headers = {"Authorization": f"Bearer {settings.sms_http_token}"} if settings.sms_http_token else {}
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                settings.sms_http_url,
                json={"mobile": mobile, "content": content},
                headers=headers,
            )
        ok = resp.status_code < 300
        if not ok:
            logger.error("短信发送失败 %s: %s", resp.status_code, resp.text[:200])
        return ok


def get_sms_provider():
    if settings.sms_provider.lower() == "http":
        return HttpSmsProvider()
    return ConsoleSmsProvider()
