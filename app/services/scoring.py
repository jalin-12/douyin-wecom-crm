"""意向评分：决定销售跟进优先级。"""
from app.services.douyin import MOBILE_RE


def calc_intent_score(customer_type: str, quantity: int, mobile: str, company: str) -> int:
    if customer_type in ("enterprise", "school"):
        base = 80 if quantity >= 10 else 60
    else:
        base = 40
    if MOBILE_RE.fullmatch(mobile or ""):
        base += 5
    if company:
        base += 5
    return min(base, 100)
