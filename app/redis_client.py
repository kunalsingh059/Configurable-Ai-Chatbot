"""
Single shared async Redis connection pool, used for two things that used to
be plain in-process Python dicts (SESSIONS in main.py, _hits in rate_limit.py):

  1. Chat session storage (conversation history per session_id)
  2. Rate limiting counters

Both moved to Redis for the same reason: an in-process dict is invisible to
every OTHER process. Run two uvicorn workers, or two instances behind a load
balancer, and each one enforces rate limits independently (the real limit
becomes limit x process count) and a user's session can silently "disappear"
if their next request lands on a different worker. Redis fixes both by
giving every worker/instance the same source of truth.

redis-py's asyncio client handles pooling internally - one client instance
is safe to share across all requests/coroutines, so we create it once and
reuse it (same pattern as db.py's Motor client).
"""

import os
import redis.asyncio as redis

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")

_redis: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(
            REDIS_URL,
            decode_responses=True,
            # Same reasoning as db.py's Motor timeouts: fail fast on a
            # network/Redis problem instead of hanging the request on
            # whatever the library's own default would be.
            socket_connect_timeout=5,
            socket_timeout=5,
            health_check_interval=30,
        )
    return _redis


async def ping() -> bool:
    """Used by /health - see main.py."""
    try:
        return await get_redis().ping()
    except Exception:
        return False