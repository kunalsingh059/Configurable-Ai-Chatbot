"""
Redis-backed rate limiter. Replaces the old in-memory-dict version - see
that version's own docstring (still worth reading in git history) for why:
a plain Python dict only sees requests handled by ITS OWN process, so the
moment you run more than one uvicorn worker (which you need to, for the
horizontal scaling this app is being upgraded for), each worker enforces
the limit independently and the real effective limit becomes
(limit x number of workers). Redis gives every worker the same counter.

FIXED WINDOW, not sliding window: this is a deliberate simplification from
the old sliding-window version. A fixed window (INCR + EXPIRE, one round
trip) is one Redis call; a true sliding window (sorted sets: ZADD +
ZREMRANGEBYSCORE + ZCARD) is three. For a chat rate limit, "burstable at
the edge of a 60s window" is an acceptable tradeoff for 1/3rd the Redis
load per request - this is not a security boundary, just abuse prevention.

FAILS OPEN: if Redis itself is unreachable, we log it and let the request
through rather than 500-ing every chat message because of a transient
Redis blip. Rate limiting is a safety net for cost/abuse control, not a
security control - it should never be the reason the whole product goes
down.
"""

import logging
import os
from fastapi import HTTPException, Request
from redis.exceptions import RedisError
from app.redis_client import get_redis

logger = logging.getLogger("chatbot_platform")


async def check_rate_limit(key: str, max_requests: int, window_seconds: int = 60) -> None:
    """Fixed-window check: raises 429 if `key` has made >= max_requests
    calls in the current window_seconds-wide window. Otherwise records
    this call. Call sites are unchanged (main.py) other than adding
    `await` - this used to be a sync function."""
    redis_key = f"ratelimit:{key}"
    r = get_redis()
    try:
        # INCR on a key that doesn't exist yet creates it at 1 - so
        # "current == 1" means this is the first hit in a fresh window,
        # and that's the only time we need to (re)set the expiry.
        current = await r.incr(redis_key)
        if current == 1:
            await r.expire(redis_key, window_seconds)
    except RedisError as e:
        logger.error(f"Rate limit check failed for '{key}' - Redis unreachable, failing open: {e}")
        return

    if current > max_requests:
        raise HTTPException(
            status_code=429,
            detail="Too many requests - please slow down and try again shortly.",
        )


# ---------------------------------------------------------------------------
# Real client IP behind a reverse proxy - unchanged from before, this part
# never needed Redis (no shared state, just parses one request's headers).
# ---------------------------------------------------------------------------
TRUSTED_PROXY_HOPS = int(os.environ.get("TRUSTED_PROXY_HOPS", "0"))


def get_client_ip(request: Request) -> str:
    direct = request.client.host if request.client else "unknown"
    if TRUSTED_PROXY_HOPS <= 0:
        return direct

    forwarded = request.headers.get("x-forwarded-for", "")
    parts = [p.strip() for p in forwarded.split(",") if p.strip()]
    ip = parts[-TRUSTED_PROXY_HOPS] if len(parts) >= TRUSTED_PROXY_HOPS else direct
    logger.debug(f"client_ip={ip} direct={direct} x_forwarded_for={forwarded!r}")
    return ip