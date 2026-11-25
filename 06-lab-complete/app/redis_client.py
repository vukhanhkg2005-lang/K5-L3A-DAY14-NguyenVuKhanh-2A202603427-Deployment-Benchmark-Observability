"""
Kết nối Redis dùng chung cho rate limiter và cost guard.

App vẫn khởi động được khi Redis chưa sẵn sàng (không ping lúc import).
"""
from typing import Optional

import redis

from app.config import settings

r: Optional[redis.Redis] = (
    redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )
    if settings.redis_url
    else None
)


def redis_healthy() -> bool:
    """Ping Redis cho GET /ready; lỗi kết nối hoặc chưa cấu hình → False."""
    if r is None:
        return False
    try:
        return bool(r.ping())
    except Exception:
        return False


def close_redis() -> None:
    """Đóng connection pool khi shutdown."""
    if r is not None:
        try:
            r.close()
        except Exception:
            pass
