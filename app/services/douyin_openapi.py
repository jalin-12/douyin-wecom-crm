"""抖音开放平台「线索管理」：client_token + 线索查询 + 手机号解密。

官方接口：GET https://open.douyin.com/goodlife/v1/open_api/crm/clue/query/
凭证：POST https://open.douyin.com/oauth/client_token/（有效期 2 小时）
"""
import base64
import json
import logging
import time
from datetime import datetime, timedelta

import httpx
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from app.config import settings
from app.services.douyin import MOBILE_RE, _first, _to_int, detect_customer_type, flatten

logger = logging.getLogger("crm.douyin.openapi")
BASE = "https://open.douyin.com"
_CLUE_URL = f"{BASE}/goodlife/v1/open_api/crm/clue/query/"
_TOKEN_URL = f"{BASE}/oauth/client_token/"
TIMEOUT = httpx.Timeout(15.0)
TIME_FMT = "%Y-%m-%d %H:%M:%S"

# MOCK_DOUYIN=true 时用于本地联调，不走真实接口
MOCK_CLUES = [
    {
        "clue_id": "mock-clue-001",
        "name": "赵老师",
        "telephone": "13600136000",
        "city_name": "杭州",
        "poi_name": "杭州某某教育集团",
        "remark_dict": {"客户类型": "企业", "采购数量": "20", "单位名称": "杭州某某教育集团"},
    }
]


class DouyinAPIError(RuntimeError):
    pass


def _align_secret(secret: str) -> str:
    """按官方规则把 client_secret 补齐/裁剪到 32 位。"""
    if len(secret) < 32:
        right = (32 - len(secret)) // 2
        left = 32 - len(secret) - right
        return "#" * left + secret + "#" * right
    if len(secret) > 32:
        right = (len(secret) - 32) // 2
        left = len(secret) - 32 - right
        return secret[left:left + 32]
    return secret


def decrypt_mobile(cipher_text: str, secret: str | None = None) -> str:
    """解密 telephone；已是明文或已掩码则原样返回。"""
    if not cipher_text:
        return ""
    if MOBILE_RE.fullmatch(cipher_text):
        return cipher_text

    secret = secret or settings.douyin_client_secret
    if not secret:
        return cipher_text
    key = _align_secret(secret)
    try:
        raw = base64.b64decode(cipher_text)
        # 抖音规则：secret 作 Key，右侧 16 位作 IV
        cipher = Cipher(algorithms.AES(key.encode()), modes.CBC(key[16:].encode()))
        decryptor = cipher.decryptor()
        plain = decryptor.update(raw) + decryptor.finalize()
        pad = plain[-1]
        if 1 <= pad <= 32:
            plain = plain[:-pad]
        text = plain.decode("utf-8").strip()
        match = MOBILE_RE.search(text)
        return match.group() if match else text
    except Exception:  # noqa: BLE001 掩码/异常数据保持原样
        return cipher_text


def _remark(clue: dict) -> dict:
    remark = clue.get("remark_dict") or {}
    if isinstance(remark, str):
        try:
            remark = json.loads(remark)
        except json.JSONDecodeError:
            remark = {"备注": remark}
    return remark if isinstance(remark, dict) else {"备注": str(remark)}


def map_clue(clue: dict) -> dict:
    """把 clue_data 一条记录映射为 ingest_lead 需要的结构。"""
    remark = _remark(clue)
    flat = flatten(remark)
    company = (
        _first(flat, ("单位名称", "单位", "公司", "学校", "company", "org"))
        or clue.get("poi_name", "")
        or clue.get("intention_life_account_name", "")
    )
    explicit_type = _first(flat, ("客户类型", "单位类型", "客户类型", "customer_type", "类型"))
    qty_text = _first(flat, ("采购数量", "采购量", "数量", "套数", "人数", "quantity", "qty"))

    return {
        "douyin_lead_id": clue.get("clue_id") or None,
        "name": clue.get("name", ""),
        "mobile": decrypt_mobile(clue.get("telephone", "")),
        "company": company,
        "customer_type": detect_customer_type(explicit_type, company),
        "quantity": _to_int(qty_text),
        "city": clue.get("city_name", ""),
        "raw": clue,
    }


class DouyinOpenAPI:
    def __init__(self) -> None:
        self._token = ""
        self._expire_at = 0.0

    async def client_token(self, force: bool = False) -> str:
        if settings.mock_douyin:
            return "mock-token"
        if not force and self._token and time.time() < self._expire_at:
            return self._token
        if not settings.douyin_client_key or not settings.douyin_client_secret:
            raise DouyinAPIError("缺少 DOUYIN_CLIENT_KEY / DOUYIN_CLIENT_SECRET")

        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(
                _TOKEN_URL,
                json={
                    "client_key": settings.douyin_client_key,
                    "client_secret": settings.douyin_client_secret,
                    "grant_type": "client_credential",
                },
            )
        payload = resp.json()
        data = payload.get("data") or {}
        if data.get("error_code") != 0:
            raise DouyinAPIError(f"client_token 失败: {data.get('description')} ({data.get('error_code')})")

        self._token = data["access_token"]
        self._expire_at = time.time() + max(int(data.get("expires_in", 7200)) - 300, 60)
        return self._token

    async def query_page(self, start: datetime, end: datetime, page: int, page_size: int = 100) -> tuple[list[dict], dict]:
        if settings.mock_douyin:
            return (MOCK_CLUES if page == 1 else []), {"total": len(MOCK_CLUES), "page_number": page}

        if not settings.douyin_account_id:
            raise DouyinAPIError("缺少 DOUYIN_ACCOUNT_ID（来客品牌账户 ID）")

        params = {
            "account_id": settings.douyin_account_id,
            "start_time": start.strftime(TIME_FMT),
            "end_time": end.strftime(TIME_FMT),
            "page": page,
            "page_size": page_size,
        }
        if settings.douyin_open_id:
            params["open_id"] = settings.douyin_open_id

        headers = {
            "access-token": await self.client_token(),
            "content-type": "application/json",
        }
        if settings.douyin_root_account_id:
            headers["Rpc-Transit-Life-Account"] = settings.douyin_root_account_id

        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(_CLUE_URL, params=params, headers=headers)
        payload = resp.json()
        data = payload.get("data") or {}
        if data.get("error_code") not in (0, None) or (payload.get("extra") or {}).get("error_code") not in (0, None):
            raise DouyinAPIError(f"线索查询失败: {data.get('description') or payload.get('extra')}")
        return data.get("clue_data") or [], data.get("page") or {}

    async def pull(self, start: datetime, end: datetime, max_pages: int = 20) -> list[dict]:
        clues: list[dict] = []
        for page in range(1, max_pages + 1):
            batch, info = await self.query_page(start, end, page)
            clues.extend(batch)
            total = int(info.get("total") or 0)
            if not batch or len(batch) < 100 or page * 100 >= total:
                break
        return clues


douyin_api = DouyinOpenAPI()
