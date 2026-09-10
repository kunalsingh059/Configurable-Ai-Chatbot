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

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Header, HTTPException

from app.db import admin_users_collection

logger = logging.getLogger("chatbot_platform")

JWT_SECRET = os.environ.get("JWT_SECRET")
if not JWT_SECRET:
    raise RuntimeError(
        "JWT_SECRET is not set. Add a long random string to your .env - "
        "generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
    )
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24

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


async def get_tenant_from_api_key(
    x_api_key: str = Header(None),
    origin: str = Header(None),
    referer: str = Header(None),
) -> str:
    """
    Dependency for /chat. Resolves which tenant an API key belongs to, and
    rejects the request if that business owner has been deactivated - this
    is what makes deactivation stop a live chatbot immediately, not just
    block the admin panel.

    Also checks the request's Origin/Referer against that business's
    allowed_domains (if configured) - this is what stops a leaked
    api_key from being used on someone else's website, since the key
    itself is always visible in client-side HTML by design.
    """
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")

    user = await admin_users_collection.find_one({"api_key": x_api_key})
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid API key")
    if not user.get("is_active", False):
        raise HTTPException(status_code=403, detail="This chatbot is currently unavailable")

    allowed_domains = user.get("allowed_domains") or []
    if allowed_domains:
        request_origin = origin or referer or ""
        host = request_origin.split("//")[-1].split("/")[0].split(":")[0]
        if not any(host == d or host.endswith("." + d) for d in allowed_domains):
            raise HTTPException(
                status_code=403,
                detail="This chatbot is not authorized for this website.",
            )

    return user["tenant_id"]