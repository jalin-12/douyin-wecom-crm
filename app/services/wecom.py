"""企业微信 API 封装：获取 token、联系我活码、欢迎语、打标签。"""
import logging
import time

import httpx

from app.config import settings

logger = logging.getLogger("crm.wecom")
BASE = "https://qyapi.weixin.qq.com/cgi-bin"
TIMEOUT = httpx.Timeout(10.0)


class WeComError(RuntimeError):
    pass


class WeComClient:
    def __init__(self) -> None:
        self._token = ""
        self._token_expire_at = 0.0

    async def get_token(self, force: bool = False) -> str:
        if settings.wecom_mock:
            return "mock-token"
        if not force and self._token and time.time() < self._token_expire_at:
            return self._token
        if not settings.wecom_corp_id or not settings.wecom_corp_secret:
            raise WeComError("缺少 WECOM_CORP_ID / WECOM_CORP_SECRET")

        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                f"{BASE}/gettoken",
                params={"corpid": settings.wecom_corp_id, "corpsecret": settings.wecom_corp_secret},
            )
            data = resp.json()
        if data.get("errcode") != 0:
            raise WeComError(f"gettoken 失败: {data}")
        self._token = data["access_token"]
        self._token_expire_at = time.time() + max(int(data.get("expires_in", 7200)) - 120, 60)
        return self._token

    async def _post(self, path: str, payload: dict) -> dict:
        token = await self.get_token()
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(f"{BASE}/{path}", params={"access_token": token}, json=payload)
            data = resp.json()
        if data.get("errcode") != 0:
            raise WeComError(f"{path} 失败: {data}")
        return data

    async def create_contact_way(self, userids: list[str], state: str) -> str:
        """创建“联系我”活码，返回可直接分配的 config_url。"""
        if settings.wecom_mock:
            return f"https://work.weixin.qq.com/ca/mock-contact?state={state}"
        if not userids:
            raise WeComError("没有可用的销售企微 userid")

        data = await self._post(
            "externalcontact/add_contact_way",
            {
                "type": 1,
                "scene": 2,
                "state": state,
                "user": userids,
                "skip_verify": True,
                "remarks": "图书卡采购/授权咨询",
            },
        )
        return data["contact_way"]["config_url"]

    async def send_welcome_msg(self, welcome_code: str, text: str) -> None:
        if settings.wecom_mock:
            logger.info("[mock] welcome_msg -> %s: %s", welcome_code, text)
            return
        await self._post("externalcontact/send_welcome_msg", {"welcome_code": welcome_code, "text": {"content": text}})

    async def mark_tag(self, userid: str, external_userid: str, add_tag: list[str], remove_tag: list[str] | None = None) -> None:
        if settings.wecom_mock:
            logger.info("[mock] mark_tag %s/%s +%s", userid, external_userid, add_tag)
            return
        await self._post(
            "externalcontact/mark_tag",
            {
                "userid": userid,
                "external_userid": external_userid,
                "add_tag": add_tag,
                "remove_tag": remove_tag or [],
            },
        )


wecom = WeComClient()
