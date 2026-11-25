"""
Cost guard (tiêu chí 8).

Cộng dồn chi phí LLM (tính theo token) vào Redis; vượt DAILY_BUDGET_USD hoặc
MONTHLY_BUDGET_USD → HTTP 402.
"""
import time

from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

# Giá USD / 1K tokens (tham khảo gpt-4o-mini)
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006

_local_cost_day = ""
_local_cost_total = 0.0


def _daily_key() -> str:
    return f"cost:daily:{time.strftime('%Y-%m-%d', time.gmtime())}"


def _monthly_key() -> str:
    return f"cost:monthly:{time.strftime('%Y-%m', time.gmtime())}"


def _get_current_costs() -> tuple[float, float]:
    global _local_cost_day, _local_cost_total
    if r is not None:
        try:
            daily_val = float(r.get(_daily_key()) or 0.0)
            monthly_val = float(r.get(_monthly_key()) or 0.0)
            return daily_val, monthly_val
        except Exception:
            pass

    today = time.strftime("%Y-%m-%d", time.gmtime())
    if _local_cost_day != today:
        _local_cost_day = today
        _local_cost_total = 0.0
    return _local_cost_total, _local_cost_total


def check_budget() -> None:
    """Gọi TRƯỚC khi gọi LLM. Hết budget → raise HTTPException(status_code=402)."""
    daily_cost, monthly_cost = _get_current_costs()
    if daily_cost >= settings.daily_budget_usd or monthly_cost >= settings.monthly_budget_usd:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "Budget exceeded",
                "daily_cost_usd": round(daily_cost, 6),
                "daily_budget_usd": settings.daily_budget_usd,
                "monthly_cost_usd": round(monthly_cost, 6),
                "monthly_budget_usd": settings.monthly_budget_usd,
            },
        )


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí của request vào tổng, trả về chi phí request."""
    global _local_cost_day, _local_cost_total
    cost = (
        (input_tokens / 1000.0) * PRICE_INPUT_PER_1K
        + (output_tokens / 1000.0) * PRICE_OUTPUT_PER_1K
    )

    if r is not None:
        try:
            d_key = _daily_key()
            m_key = _monthly_key()
            pipe = r.pipeline()
            pipe.incrbyfloat(d_key, cost)
            pipe.expire(d_key, 172800)
            pipe.incrbyfloat(m_key, cost)
            pipe.expire(m_key, 35 * 86400)
            pipe.execute()
            return cost
        except Exception:
            pass

    today = time.strftime("%Y-%m-%d", time.gmtime())
    if _local_cost_day != today:
        _local_cost_day = today
        _local_cost_total = 0.0
    _local_cost_total += cost
    return cost
