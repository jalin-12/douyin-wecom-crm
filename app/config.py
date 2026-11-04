"""运行配置：全部来自环境变量，未配置时使用安全的开发默认值。"""
import json
import os
from dataclasses import dataclass, field


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


DEFAULT_SALES_POOL = [
    {"userid": "sale_enterprise_1", "group": "enterprise", "daily_limit": 20},
    {"userid": "sale_personal_1", "group": "personal", "daily_limit": 30},
]


def _sales_pool() -> list[dict]:
    raw = os.getenv("SALES_POOL", "").strip()
    if not raw:
        return list(DEFAULT_SALES_POOL)
    pool = json.loads(raw)
    if not isinstance(pool, list):
        raise ValueError("SALES_POOL 必须是 JSON 数组")
    return pool


@dataclass(frozen=True)
class Settings:
    db_url: str = field(default_factory=lambda: os.getenv("DB_URL", "sqlite:///./data/crm.db"))

    # 抖音来客留资组件回调
    douyin_webhook_secret: str = field(default_factory=lambda: os.getenv("DOUYIN_WEBHOOK_SECRET", ""))
    mock_douyin: bool = field(default_factory=lambda: _bool("MOCK_DOUYIN", True))

    # 抖音开放平台「生活服务商家应用」——线索查询（拉取）
    douyin_client_key: str = field(default_factory=lambda: os.getenv("DOUYIN_CLIENT_KEY", ""))
    douyin_client_secret: str = field(default_factory=lambda: os.getenv("DOUYIN_CLIENT_SECRET", ""))
    douyin_account_id: str = field(default_factory=lambda: os.getenv("DOUYIN_ACCOUNT_ID", ""))
    douyin_root_account_id: str = field(default_factory=lambda: os.getenv("DOUYIN_ROOT_ACCOUNT_ID", ""))
    douyin_open_id: str = field(default_factory=lambda: os.getenv("DOUYIN_OPEN_ID", ""))
    douyin_sync_enabled: bool = field(default_factory=lambda: _bool("DOUYIN_SYNC_ENABLED", False))
    douyin_sync_interval_seconds: int = field(default_factory=lambda: _int("DOUYIN_SYNC_INTERVAL_SECONDS", 300))
    douyin_sync_lookback_minutes: int = field(default_factory=lambda: _int("DOUYIN_SYNC_LOOKBACK_MINUTES", 60))
    douyin_lag_minutes: int = field(default_factory=lambda: _int("DOUYIN_LAG_MINUTES", 10))

    # 企业微信自建应用
    wecom_corp_id: str = field(default_factory=lambda: os.getenv("WECOM_CORP_ID", ""))
    wecom_corp_secret: str = field(default_factory=lambda: os.getenv("WECOM_CORP_SECRET", ""))
    wecom_agent_id: str = field(default_factory=lambda: os.getenv("WECOM_AGENT_ID", ""))
    wecom_token: str = field(default_factory=lambda: os.getenv("WECOM_TOKEN", ""))
    wecom_aes_key: str = field(default_factory=lambda: os.getenv("WECOM_AES_KEY", ""))
    wecom_mock: bool = field(default_factory=lambda: _bool("WECOM_MOCK", True))

    # 短信：console 仅打印，http 走真实短信网关
    sms_provider: str = field(default_factory=lambda: os.getenv("SMS_PROVIDER", "console"))
    sms_http_url: str = field(default_factory=lambda: os.getenv("SMS_HTTP_URL", ""))
    sms_http_token: str = field(default_factory=lambda: os.getenv("SMS_HTTP_TOKEN", ""))
    sms_template: str = field(
        default_factory=lambda: os.getenv(
            "SMS_TEMPLATE",
            "【图书卡】您的专属顾问已在企业微信等您，点击链接添加：{link}",
        )
    )

    sla_minutes: int = field(default_factory=lambda: _int("SLA_MINUTES", 5))
    sla_scan_seconds: int = field(default_factory=lambda: _int("SLA_SCAN_SECONDS", 60))
    internal_api_key: str = field(default_factory=lambda: os.getenv("INTERNAL_API_KEY", ""))
    mock_internal_key: bool = field(default_factory=lambda: _bool("MOCK_INTERNAL_KEY", True))
    sales_pool: list[dict] = field(default_factory=_sales_pool)


settings = Settings()
