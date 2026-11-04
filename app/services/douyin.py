"""抖音来客留资解析：字段名不固定，做递归扁平化 + 别名匹配。"""
import re
from typing import Any

MOBILE_RE = re.compile(r"1[3-9]\d{9}")

MOBILE_KEYS = ("mobile", "phone", "telephone", "tel", "联系方式", "手机号", "手机")
NAME_KEYS = ("name", "contact_name", "username", "姓名", "联系人")
COMPANY_KEYS = ("company", "company_name", "org", "机构", "公司", "单位", "学校名称")
TYPE_KEYS = ("customer_type", "customerType", "客户类型", "单位类型", "类型")
QTY_KEYS = ("quantity", "qty", "count", "num", "采购量", "数量", "套数", "人数")
CITY_KEYS = ("city", "city_name", "城市")
ID_KEYS = ("lead_id", "clue_id", "leads_id", "id", "线索id")


def flatten(obj: Any, prefix: str = "", out: dict[str, Any] | None = None) -> dict[str, Any]:
    """把任意嵌套的回调结构压成 {"a.b.0.c": value}，方便按关键字取值。"""
    if out is None:
        out = {}
    if isinstance(obj, dict):
        for key, value in obj.items():
            flatten(value, f"{prefix}.{key}" if prefix else str(key), out)
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            flatten(value, f"{prefix}.{index}", out)
    else:
        out[prefix.lower()] = obj
    return out


def _first(flat: dict[str, Any], aliases: tuple[str, ...]) -> str:
    """按别名优先级取值；键名包含别名即命中。"""
    for alias in aliases:
        for key, value in flat.items():
            if alias.lower() in key and value not in (None, ""):
                if isinstance(value, (str, int, float)):
                    return str(value).strip()
    return ""


def _to_int(value: str, default: int = 1) -> int:
    match = re.search(r"\d+", value or "")
    return int(match.group()) if match else default


def detect_customer_type(explicit: str, company: str) -> str:
    text = f"{explicit} {company}"
    if any(word in text for word in ("企业", "公司", "商贸", "科技", "集团", "工厂", "机构")):
        return "enterprise"
    if any(word in text for word in ("学校", "学院", "大学", "教育局", "培训", "校区")):
        return "school"
    return "personal"


def parse_lead(payload: dict[str, Any]) -> dict[str, Any]:
    """输出统一结构，raw 保留原始 payload 便于核对字段。"""
    flat = flatten(payload)

    mobile = _first(flat, MOBILE_KEYS)
    if not MOBILE_RE.fullmatch(mobile):
        # 兜底：从所有值里抓一个合法手机号
        for value in flat.values():
            if isinstance(value, str):
                found = MOBILE_RE.search(value)
                if found:
                    mobile = found.group()
                    break

    company = _first(flat, COMPANY_KEYS)
    explicit_type = _first(flat, TYPE_KEYS)
    qty_text = _first(flat, QTY_KEYS)

    return {
        "douyin_lead_id": _first(flat, ID_KEYS) or None,
        "name": _first(flat, NAME_KEYS),
        "mobile": mobile,
        "company": company,
        "customer_type": detect_customer_type(explicit_type, company),
        "quantity": _to_int(qty_text),
        "city": _first(flat, CITY_KEYS),
        "raw": payload,
    }
