"""
AUTH LAYER

Two account types share one `admin_users` collection, distinguished by a
`role` field:

  - "business_owner" - a client (restaurant, pathology lab, etc). Has a
    tenant_id, an api_key (for their chatbot widget), and starts with
    is_active=False until the super admin approves them.
  - "super_admin"    - your team. No tenant_id, no api_key, is_active=True
    from creation. Manages business_owner accounts (activate/deactivate).

Both log in through the SAME /auth/login endpoint - the JWT that comes back
encodes which role you are, and the frontend (admin.html) shows the right
dashboard based on that.

Deactivating a business_owner blocks BOTH their admin login AND their live
chat widget immediately - both checks below look at the same is_active flag,
so there's exactly one place that controls "is this business allowed to use
the platform right now."
"""

import os
import secrets
import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Header, HTTPException, Request

from app.db import admin_users_collection
from app.rate_limit import check_rate_limit, get_client_ip

logger = logging.getLogger("chatbot_platform")

JWT_SECRET = os.environ.get("JWT_SECRET")
if not JWT_SECRET:
    raise RuntimeError(
        "JWT_SECRET is not set. Add a long random string to your .env - "
        "generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
    )
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24

# Max requests per minute from ONE real client IP to the public (API-key)
# endpoints - /chat and /widget/config share this bucket. Sits in front of the
# per-session and per-business limits in main.py: those are keyed on values a
# scripted client controls (session_id) or shared by all of a business's
# customers, so on their own one abuser could exhaust a whole business's quota.
PUBLIC_IP_RATE_LIMIT_PER_MINUTE = int(os.environ.get("PUBLIC_IP_RATE_LIMIT_PER_MINUTE", "60"))

# false (default): a business that hasn't listed any allowed websites yet is
#   unrestricted - existing accounts keep working after this update.
# true: such a business is REFUSED until it lists at least one website. Turn
#   this on in production once every business has configured its site.
REQUIRE_ALLOWED_DOMAINS = os.environ.get("REQUIRE_ALLOWED_DOMAINS", "false").strip().lower() in ("1", "true", "yes")

_ph = PasswordHasher()


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        _ph.verify(password_hash, password)
        return True
    except VerifyMismatchError:
        return False


def generate_api_key() -> str:
    return "sk_" + secrets.token_hex(24)


def create_access_token(user: dict) -> str:
    payload = {
        "sub": user["username"],
        "role": user["role"],
        "tenant_id": user.get("tenant_id"),  # None for super_admin
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_reset_token(user: dict) -> str:
    """
    Short-lived (30 min), single-purpose token emailed as a password reset
    link. Deliberately a SEPARATE token type from create_access_token - the
    "purpose" claim means even if someone got hold of a reset link, they
    could never use it as a login session, and vice versa.

    Also embeds the user's current reset_token_version ("v") - this is what
    makes the token one-time-use. A bare JWT can't be revoked once issued
    (it's just a signed blob, nothing to delete server-side), so instead
    every successful password reset increments reset_token_version in the
    DB. verify_reset_token compares the token's "v" against the current DB
    value - once they diverge, the token is dead, even though it hasn't
    expired yet. This also means requesting a new reset link invalidates
    any older unused link for that account, which is the right behavior.
    """
    payload = {
        "sub": user["username"],
        "purpose": "password_reset",
        "v": user.get("reset_token_version", 0),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


async def verify_reset_token(token: str) -> tuple[str, int]:
    """Returns (username, token_version) the token was issued for, or
    raises HTTPException. Async because it needs to check the token's
    version against the current DB value - see create_reset_token's
    docstring for why.

    This is a fast-fail pre-check with a clear user-facing message
    (expired/invalid/already-used) - it is NOT itself the atomic
    consumption guarantee. The caller (reset_password in main.py) still
    needs to re-check the version in its update filter, since two
    concurrent requests could both pass this check before either one's
    update lands. Returning token_version is what lets that final update
    be atomic instead of relying on this check alone."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=400, detail="This reset link has expired. Please request a new one.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=400, detail="This reset link is invalid.")

    if payload.get("purpose") != "password_reset":
        raise HTTPException(status_code=400, detail="This reset link is invalid.")

    username = payload["sub"]
    token_version = payload.get("v", 0)
    user = await admin_users_collection.find_one({"username": username})
    if user is None:
        raise HTTPException(status_code=400, detail="This reset link is invalid.")

    if token_version != user.get("reset_token_version", 0):
        logger.info(
            f"Reset token rejected for '{username}': token was issued for "
            f"version {token_version}, but current version is "
            f"{user.get('reset_token_version', 0)} - this token is stale "
            "(likely an older/already-used email link, not the most "
            "recently requested one)."
        )
        raise HTTPException(
            status_code=400,
            detail="This reset link has already been used or is no longer valid. Please request a new one.",
        )

    return username, token_version


def _decode_token(authorization: str) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = authorization[len("Bearer "):]
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired, please log in again")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid authentication token")


async def get_current_business_owner(authorization: str = Header(None)) -> str:
    """
    Dependency for /admin/tools and /admin/documents. Returns the tenant_id
    from the token - never trusts a tenant_id sent by the caller. Also
    re-checks is_active on every request (not just at login), so a business
    owner deactivated mid-session is locked out immediately, not just on
    their next login.
    """
    payload = _decode_token(authorization)
    if payload.get("role") != "business_owner":
        raise HTTPException(status_code=403, detail="Business owner account required")

    user = await admin_users_collection.find_one({"username": payload["sub"]})
    if user is None or not user.get("is_active", False):
        raise HTTPException(status_code=403, detail="Account is deactivated")

    return payload["tenant_id"]


async def get_current_super_admin(authorization: str = Header(None)) -> dict:
    """Dependency for /superadmin/* endpoints."""
    payload = _decode_token(authorization)
    if payload.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Super admin account required")
    return payload


def _host_from_origin(value: str | None) -> str | None:
    """Hostname of an origin like "https://www.shop.com:8443", or None if it
    isn't a plain http(s) origin (e.g. the literal string "null" that
    sandboxed frames send, or garbage)."""
    if not value:
        return None
    try:
        parsed = urlparse(value.strip())
        host = parsed.hostname
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https") or not host:
        return None
    return host.lower()


def _host_is_allowed(host: str, allowed_domains: list[str]) -> bool:
    # "shop.com" allows shop.com and any subdomain (www.shop.com, ...), but
    # NOT "evilshop.com" or "shop.com.evil.com" - hence the leading dot.
    return any(host == d or host.endswith("." + d) for d in allowed_domains)


async def get_tenant_from_api_key(
    request: Request,
    x_api_key: str = Header(None),
    x_embed_origin: str = Header(None),
) -> str:
    """
    Dependency for /chat and /widget/config. Resolves which tenant an API key
    belongs to, and rejects the request if that business owner has been
    deactivated - this is what makes deactivation stop a live chatbot
    immediately, not just block the admin panel.

    WHY THE KEY ALONE CAN'T BE THE PROTECTION: the api_key sits in the client's
    page HTML by design, so anyone can copy it. What stops a copied key from
    working on someone else's site is this check of WHERE the widget is
    embedded:

      - The widget runs inside an iframe, so the browser's own Origin header on
        its API calls is the WIDGET's domain, which says nothing about which
        website embedded it.
      - Instead the widget reads the embedding page's origin from the
        browser-supplied event.origin of embed.js's postMessage (page scripts
        can't forge that) and sends it as X-Embed-Origin.
      - Another site that embeds our widget, or opens it directly with the key,
        therefore reports ITS OWN origin and is refused here. A page on another
        site calling this API directly is stopped by CORS in main.py.

    LIMIT: a non-browser client (curl, a server script) can send any header
    it likes, so this stops re-use of a copied key from other websites, not a
    determined scripted attacker. Against that, the per-IP / per-session /
    per-business rate limits and key regeneration are the defenses.
    """
    # Throttle per real client IP FIRST - before any DB lookup - so garbage
    # keys and floods can't be used to hammer the database either.
    check_rate_limit(f"public-ip:{get_client_ip(request)}", PUBLIC_IP_RATE_LIMIT_PER_MINUTE)

    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")

    user = await admin_users_collection.find_one({"api_key": x_api_key})
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid API key")
    if not user.get("is_active", False):
        raise HTTPException(status_code=403, detail="This chatbot is currently unavailable")

    allowed_domains = user.get("allowed_domains") or []
    if allowed_domains:
        host = _host_from_origin(x_embed_origin)
        if host is None or not _host_is_allowed(host, allowed_domains):
            logger.warning(
                f"Blocked widget request for tenant '{user['tenant_id']}' from "
                f"unauthorized site {str(x_embed_origin)[:100]!r}"
            )
            raise HTTPException(
                status_code=403,
                detail="This chatbot is not authorized for this website.",
            )
    elif REQUIRE_ALLOWED_DOMAINS:
        raise HTTPException(
            status_code=403,
            detail="This chatbot has not been authorized for any website yet.",
        )

    return user["tenant_id"]