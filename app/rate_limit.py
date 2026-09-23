"""
Minimal in-memory rate limiter - deliberately no Redis/external dependency.

CAVEAT: single-process only. This dict lives in one Python process's memory,
same as SESSIONS in main.py - if you ever run multiple uvicorn workers or
multiple instances behind a load balancer, each one enforces the limit
independently, so the *effective* limit becomes (limit x number of workers).
Fine for a single-instance MVP launch; move to Redis (INCR + EXPIRE) if you
scale beyond one process, same as the SESSIONS TODO.
"""

import logging
import os
import time
from collections import defaultdict
from fastapi import HTTPException, Request

logger = logging.getLogger("chatbot_platform")

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


# ---------------------------------------------------------------------------
# Real client IP behind a reverse proxy
# ---------------------------------------------------------------------------
# On Render (and any host with a load balancer in front of the app),
# request.client.host is the PROXY's address, not the visitor's - so every
# per-IP limit would be shared by all visitors at once. The proxy puts the
# visitor's address in X-Forwarded-For instead.
#
# X-Forwarded-For can also be written by the visitor themselves, so it is only
# trusted by position: each proxy in front of the app APPENDS the address it
# saw, so with N trusted proxies the real client is the N-th entry counted
# from the RIGHT. Anything further left is client-supplied and ignored.
#
# TRUSTED_PROXY_HOPS = how many proxies sit in front of the app.
#   0 (default) = ignore X-Forwarded-For, use the direct connection address
#                 (correct for local dev / no proxy - identical to old behavior).
# Too LOW a value makes many visitors share one IP (over-limits real users);
# too HIGH a value lets a visitor spoof their IP. Verify it after deploying:
# set LOG_LEVEL=DEBUG, call the API from two different networks (e.g. Wi-Fi and
# mobile data) and confirm the logged client_ip values differ.
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