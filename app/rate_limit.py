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

# Every unique key ever passed to check_rate_limit (an IP, a username, a
# session_id) leaves a permanent entry in _hits for the lifetime of the
# process, even once its timestamp list has fully emptied out - nothing
# previously removed the key itself, only stale timestamps INSIDE a key's
# list on that key's own next access. A key that's never accessed again
# (a one-time visitor) just sits there forever. This mirrors SESSIONS'
# _cleanup_idle_sessions pattern in main.py to fix that.
_last_cleanup = 0.0
# Conservative upper bound - every current caller uses the default 60s
# window (see main.py's check_rate_limit call sites), so anything older
# than this is safe to consider dead regardless of which key it belongs to.
_CLEANUP_STALE_AFTER_SECONDS = 300


def _cleanup_stale_entries() -> None:
    """Runs at most once every 5 minutes. Trims stale timestamps from every
    key's list (same logic check_rate_limit already does on access) and
    then drops any key that's now empty, so a one-time visitor's rate-limit
    entry doesn't live in memory forever."""
    global _last_cleanup
    now = time.time()
    if now - _last_cleanup < 300:
        return
    _last_cleanup = now

    cutoff = now - _CLEANUP_STALE_AFTER_SECONDS
    empty_keys = []
    for key, hits in _hits.items():
        while hits and hits[0] < cutoff:
            hits.pop(0)
        if not hits:
            empty_keys.append(key)
    for key in empty_keys:
        del _hits[key]


def check_rate_limit(key: str, max_requests: int, window_seconds: int = 60) -> None:
    """Sliding-window check: raises 429 if `key` has made >= max_requests
    calls in the last `window_seconds`. Otherwise records this call."""
    _cleanup_stale_entries()
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