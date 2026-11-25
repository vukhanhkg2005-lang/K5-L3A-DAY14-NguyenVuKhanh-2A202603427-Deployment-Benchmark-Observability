"""
Rate limiting (tiêu chí 7).

Sliding window 60 giây lưu trong Redis sorted set (chia sẻ giữa mọi worker/instance
và vẫn giữ state sau khi restart). Vượt giới hạn → HTTP 429 kèm Retry-After.
"""
import time
import uuid
from collections import defaultdict, deque

from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

WINDOW_SECONDS = 60.0
_local_windows: dict[str, deque[float]] = defaultdict(deque)


def check_rate_limit(key: str) -> None:
    limit = settings.rate_limit_per_minute
    now = time.time()
    cutoff = now - WINDOW_SECONDS

    if r is not None:
        redis_key = f"ratelimit:{key}"
        try:
            pipe = r.pipeline()
            pipe.zremrangebyscore(redis_key, 0, cutoff)
            pipe.zcard(redis_key)
            _, count = pipe.execute()

            if count >= limit:
                oldest = r.zrange(redis_key, 0, 0, withscores=True)
                retry_after = 60
                if oldest:
                    retry_after = max(1, int(WINDOW_SECONDS - (now - oldest[0][1])) + 1)
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded",
                    headers={"Retry-After": str(retry_after)},
                )

            member = f"{now}:{uuid.uuid4().hex}"
            pipe = r.pipeline()
            pipe.zadd(redis_key, {member: now})
            pipe.expire(redis_key, int(WINDOW_SECONDS) + 5)
            pipe.execute()
            return
        except HTTPException:
            raise
        except Exception:
            pass

    # Fallback in-memory khi chạy local không có Redis
    window = _local_windows[key]
    while window and window[0] <= cutoff:
        window.popleft()
    if len(window) >= limit:
        retry_after = max(1, int(WINDOW_SECONDS - (now - window[0])) + 1)
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )
    window.append(now)
