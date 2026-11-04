"""Fixed-window rate limiting. Uses Redis when reachable, otherwise a per-process fallback."""

import logging
import time
from collections import defaultdict

from fastapi import Request

from app.core.config import get_settings
from app.core.errors import RateLimited

log = logging.getLogger(__name__)

_memory: dict[str, tuple[int, int]] = defaultdict(lambda: (0, 0))
_redis_client = None
_redis_failed_until = 0.0


def _redis():
    global _redis_client, _redis_failed_until
    if time.time() < _redis_failed_until:
        return None
    if _redis_client is None:
        try:
            import redis

            client = redis.Redis.from_url(get_settings().redis_url, socket_connect_timeout=0.5, socket_timeout=0.5)
            client.ping()
            _redis_client = client
        except Exception:  # Redis unavailable: degrade to in-memory, retry later
            log.warning("Redis unavailable for rate limiting; using in-memory fallback")
            _redis_failed_until = time.time() + 30
            return None
    return _redis_client


def reset_rate_limits() -> None:
    """Test helper."""
    global _redis_client
    _memory.clear()
    _redis_client = None


def client_ip(request: Request) -> str:
    # Trust X-Forwarded-For only from the reverse proxy in front of the API (see nginx config).
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def hit(key: str, limit: int, window_seconds: int = 60) -> bool:
    """Record a hit; return True if the request is allowed."""
    bucket = int(time.time() // window_seconds)
    full_key = f"rl:{key}:{bucket}"
    client = _redis()
    if client is not None:
        try:
            pipe = client.pipeline()
            pipe.incr(full_key)
            pipe.expire(full_key, window_seconds + 5)
            count = pipe.execute()[0]
            return count <= limit
        except Exception:
            log.warning("Redis rate limit error; falling back to memory")
    count, b = _memory[full_key]
    count += 1
    _memory[full_key] = (count, bucket)
    if len(_memory) > 50_000:  # crude memory bound
        for k in [k for k, (_, bk) in _memory.items() if bk < bucket][:10_000]:
            _memory.pop(k, None)
    return count <= limit


def rate_limit(name: str, per_minute: int | None = None, *, by_email_field: str | None = None):
    """Dependency factory limiting by client IP for a named bucket."""

    def dependency(request: Request) -> None:
        s = get_settings()
        if not s.rate_limit_enabled:
            return
        limit = per_minute or s.rate_limit_auth_per_minute
        if not hit(f"{name}:{client_ip(request)}", limit):
            raise RateLimited("Too many requests. Please slow down and try again shortly.")

    return dependency
