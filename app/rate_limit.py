"""
Minimal in-memory rate limiter - deliberately no Redis/external dependency.

CAVEAT: single-process only. This dict lives in one Python process's memory,
same as SESSIONS in main.py - if you ever run multiple uvicorn workers or
multiple instances behind a load balancer, each one enforces the limit
independently, so the *effective* limit becomes (limit x number of workers).
Fine for a single-instance MVP launch; move to Redis (INCR + EXPIRE) if you
scale beyond one process, same as the SESSIONS TODO.
"""

import time
from collections import defaultdict
from fastapi import HTTPException

_hits: dict[str, list[float]] = defaultdict(list)


def check_rate_limit(key: str, max_requests: int, window_seconds: int = 60) -> None:
    """Sliding-window check: raises 429 if `key` has made >= max_requests
    calls in the last `window_seconds`. Otherwise records this call."""
    now = time.time()
    hits = _hits[key]
    cutoff = now - window_seconds
    while hits and hits[0] < cutoff:
        hits.pop(0)
    if len(hits) >= max_requests:
        raise HTTPException(
            status_code=429,
            detail="Too many requests - please slow down and try again shortly.",
        )
    hits.append(now)