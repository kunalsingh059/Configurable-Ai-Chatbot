from dotenv import load_dotenv
load_dotenv()  # must run before groq_client.py / auth.py read env vars

from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from bson import ObjectId
from pymongo.errors import DuplicateKeyError

import os
import time
import json
import asyncio
import logging

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    force=True,  # uvicorn configures logging on its own startup before this
    # runs - basicConfig() silently no-ops if logging is already configured
    # unless force=True is passed, which was very likely swallowing every
    # logger.info()/logger.error() call in this app up to now.
)
logger = logging.getLogger("chatbot_platform")
from app.db import client, tools_collection, documents_collection, admin_users_collection
from app.models import ToolModel, ToolTestModel, DocumentModel, RegisterModel, LoginModel, BusinessNameModel, ForgotPasswordModel, ResetPasswordModel, AllowedDomainsModel, derive_business_name, serialize_tool, serialize_document
from app.dynamic_tools import get_tenant_tools, execute_tool, format_tool_result_for_llm
from app.crypto import encrypt_headers
from app.mock_llm import run_mock_chat_turn_stream
from app.groq_client import run_groq_chat_turn_stream
from app.documents import extract_text, get_tenant_documents, ingest_document_chunks, delete_document_chunks
from app.embeddings import warm_up as warm_up_embeddings
from app.email_service import send_password_reset_email
from app.rate_limit import check_rate_limit, get_client_ip
from app.redis_client import get_redis, ping as redis_ping
from redis.exceptions import RedisError
from redis.asyncio.lock import Lock
import groq
from app.auth import (
    hash_password, verify_password, generate_api_key, create_access_token,
    create_reset_token, verify_reset_token,
    get_current_business_owner, get_current_super_admin, get_tenant_from_api_key,
    REQUIRE_ALLOWED_DOMAINS,
)

# Which LLM powers the chat: "mock" (free, fake reasoning - dev/test ONLY)
# or "groq" (real reasoning, the only real provider this app supports).
# LLM_PROVIDER has NO default on purpose - a missing/invalid value must fail
# startup loudly rather than silently falling back to anything, mock
# included. That silent-mock fallback used to be the default behavior here,
# which is exactly the "app boots fine, customers get fake canned answers,
# nobody notices" failure mode this now prevents.
_RAW_LLM_PROVIDER = os.environ.get("LLM_PROVIDER")
LLM_PROVIDER = (_RAW_LLM_PROVIDER or "").lower()

if not _RAW_LLM_PROVIDER:
    raise RuntimeError(
        "LLM_PROVIDER is not set in .env - refusing to start. Set "
        "LLM_PROVIDER=groq (and GROQ_API_KEY) for real answers, or "
        "explicitly LLM_PROVIDER=mock for local dev/testing only."
    )
elif LLM_PROVIDER == "mock":
    # Legitimate for local dev/testing, but only because it was explicitly
    # opted into above (no default can land here) - still loud about it so
    # it's never mistaken for a real deploy.
    logger.warning(
        "LLM_PROVIDER=mock - the chatbot is running on FAKE canned "
        "responses, not a real model. This must never be set in production."
    )
elif LLM_PROVIDER == "groq":
    if not os.environ.get("GROQ_API_KEY"):
        # Fail at startup, not on the first person's chat message - same
        # principle as the SUPERADMIN_USERNAME/PASSWORD check below, just
        # for a config error that would otherwise only surface as a 500.
        raise RuntimeError(
            "LLM_PROVIDER=groq but GROQ_API_KEY is not set in .env - the "
            "app cannot start without it."
        )
else:
    raise RuntimeError(
        f"LLM_PROVIDER={_RAW_LLM_PROVIDER!r} is not a supported value - "
        "use 'groq' (production) or 'mock' (dev/test only)."
    )

# Where admin-vue's reset-password page lives - the emailed link points
# here with ?token=... appended. Defaults to local dev; set this in .env
# to your real admin-vue URL once deployed.
FRONTEND_RESET_URL = os.environ.get("FRONTEND_RESET_URL", "http://localhost:5174/reset-password")

# Max document upload size in MB - configurable via .env, defaults to 10MB.
MAX_UPLOAD_SIZE_MB = int(os.environ.get("MAX_UPLOAD_SIZE_MB", "10"))

# Two-tier chat rate limiting - see the /chat endpoint for why both exist.
# Per-customer: generous for one genuine human typing (roughly 1 msg/3sec),
# tight enough to stop a single scripted abuser. Per-business: raised from
# the original 10/min (sized only to stop obvious abuse, not real traffic)
# to something that can actually support many customers of one business
# chatting concurrently - tune this based on your actual Groq plan's
# capacity and what you're comfortable a single business could cost you
# per minute at the ceiling.
CHAT_SESSION_RATE_LIMIT_PER_MINUTE = int(os.environ.get("CHAT_SESSION_RATE_LIMIT_PER_MINUTE", "20"))
# Was defaulting to 300 here - a leftover from before Groq's real free-tier
# limits were known. That default only applies if the env var is ever
# missing on a deploy, but a wrong default should fail SAFE, not fail
# dangerous - so it now matches the safe value in .env.example instead of
# the old placeholder number.
CHAT_RATE_LIMIT_PER_MINUTE = int(os.environ.get("CHAT_RATE_LIMIT_PER_MINUTE", "12"))
# Caps total /chat requests across EVERY tenant combined - see the two
# per-key limits above, which are each scoped to one session/tenant and
# have no idea what any OTHER tenant is doing. Groq's rate limit is on
# your whole API key/org, not per tenant, so two tenants each safely under
# their own limit can still add up to more than Groq allows. This is the
# backstop for that: one shared counter, incremented by every /chat call
# regardless of which business sent it.
#
# Default of 12 (not 20 - a tool-using message costs 2 Groq requests, not
# 1, since one hop decides to call the tool and a second hop writes the
# final answer after the tool result comes back. 20 messages/min x 2 =
# 40 Groq requests/min, OVER the real 30 RPM ceiling - 12 x 2 = 24 leaves
# real headroom for /health checks and any request that only needs 1 hop.
# See console.groq.com/settings/limits for your account's actual current
# number, which is authoritative over this comment.
GLOBAL_CHAT_RATE_LIMIT_PER_MINUTE = int(os.environ.get("GLOBAL_CHAT_RATE_LIMIT_PER_MINUTE", "12"))

FORGOT_PASSWORD_RATE_LIMIT_PER_MINUTE = int(os.environ.get("FORGOT_PASSWORD_RATE_LIMIT_PER_MINUTE", "5"))
REGISTER_RATE_LIMIT_PER_MINUTE = int(os.environ.get("REGISTER_RATE_LIMIT_PER_MINUTE", "5"))
LOGIN_RATE_LIMIT_PER_MINUTE = int(os.environ.get("LOGIN_RATE_LIMIT_PER_MINUTE", "10"))


def parse_object_id(id_str: str) -> ObjectId:
    """ObjectId(some_malformed_string) raises bson.errors.InvalidId, which
    FastAPI doesn't catch - it surfaces as an ugly unhandled 500. Every
    endpoint that takes an :id path param should route it through this
    instead of calling ObjectId() directly, so a bad id cleanly 400s."""
    if not ObjectId.is_valid(id_str):
        raise HTTPException(status_code=400, detail="Invalid id format")
    return ObjectId(id_str)


app = FastAPI(title="Chatbot Platform - MVP")

# Comma-separated list of allowed frontend origins, e.g.
# "http://localhost:5173,http://localhost:5174,https://admin.yourdomain.com"
# In dev, falls back to both Vue dev server ports so nothing breaks locally.
_default_dev_origins = "http://localhost:5173,http://localhost:5174"
CORS_ALLOWED_ORIGINS = [
    o.strip() for o in os.environ.get("CORS_ALLOWED_ORIGINS", _default_dev_origins).split(",") if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Something went wrong. Please try again."})

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """FastAPI's default 422 body puts `detail` as a list of error objects,
    e.g. {"detail": [{"loc": [...], "msg": "...", "type": "..."}]}. The
    frontend's ApiError just reads data.detail and displays it directly,
    so it expects a plain string - without this handler it renders
    "[object Object]" instead of the actual validation message. This
    flattens the first (most relevant) error into one readable string."""
    first = exc.errors()[0]
    field = first["loc"][-1] if first["loc"] else "field"
    message = first["msg"]
    # Pydantic prefixes custom @field_validator ValueErrors with "Value error, "
    message = message.removeprefix("Value error, ")
    return JSONResponse(
        status_code=422,
        content={"detail": f"{field}: {message}"},
    )


MAX_MESSAGE_LENGTH = int(os.environ.get("MAX_MESSAGE_LENGTH", "1000"))
# Messages, not turns - each user+assistant exchange is 2 entries. Trimming
# this bounds both memory per session AND the Groq token cost of every
# future message in a long conversation (the full history is resent every turn).
MAX_CONVERSATION_HISTORY = int(os.environ.get("MAX_CONVERSATION_HISTORY", "20"))
SESSION_IDLE_TIMEOUT_MINUTES = int(os.environ.get("SESSION_IDLE_TIMEOUT_MINUTES", "60"))
# Bounds the WHOLE multi-hop tool-calling loop for one chat message, not
# just a single LLM call - see the /chat endpoint for why this matters.
MAX_CHAT_TURN_SECONDS = int(os.environ.get("MAX_CHAT_TURN_SECONDS", "45"))

# ------------------------- Chat session storage (Redis) -------------------------
# Was an in-process dict (SESSIONS) with a manual 5-minutes-or-less cleanup
# sweep. Moved to Redis for two reasons:
#   1. An in-process dict is invisible to every OTHER worker/instance - the
#      moment this app runs on more than one process (which it needs to,
#      for horizontal scaling), a session's next message could land on a
#      different worker with no memory of the conversation so far.
#   2. Redis's own key expiry (`ex=`) replaces the manual cleanup sweep
#      entirely - no need to periodically scan for idle sessions, Redis
#      just evicts the key itself once nobody's touched it for
#      SESSION_IDLE_TIMEOUT_MINUTES.
def _session_redis_key(session_key: str) -> str:
    return f"session:{session_key}"


async def get_session_conversation(session_key: str) -> list[dict]:
    r = get_redis()
    try:
        raw = await r.get(_session_redis_key(session_key))
    except RedisError as e:
        # Fail open on a read: worst case we start this turn with empty
        # history instead of 500-ing the whole chat because Redis hiccuped.
        logger.error(f"Session read failed for '{session_key}' - Redis unreachable, starting fresh: {e}")
        return []
    return json.loads(raw) if raw else []


async def save_session_conversation(session_key: str, conversation: list[dict]) -> None:
    r = get_redis()
    try:
        # `ex=` resets the TTL on every save, so an active conversation
        # never expires mid-use - only a session nobody has messaged in
        # SESSION_IDLE_TIMEOUT_MINUTES gets evicted, same behavior as the
        # old manual cleanup, just enforced by Redis itself.
        await r.set(
            _session_redis_key(session_key),
            json.dumps(conversation),
            ex=SESSION_IDLE_TIMEOUT_MINUTES * 60,
        )
    except RedisError as e:
        # Fail open on a write too - the reply the user already got stays
        # correct, we just risk losing this turn's history if Redis is
        # down for the next message too. Logged loudly so it's visible.
        logger.error(f"Session save failed for '{session_key}' - Redis unreachable: {e}")


def _session_lock_name(session_key: str) -> str:
    return f"lock:session:{session_key}"


# ------------------------- Bootstrap the super admin -------------------------
# There's no public "create a super admin" endpoint on purpose - only your
# team should ever hold that account. Instead, it's created automatically on
# startup from SUPERADMIN_USERNAME / SUPERADMIN_PASSWORD in .env, but only if
# one doesn't already exist yet (so this is safe to run on every restart).
@app.on_event("startup")
async def ensure_indexes():
    """
    Enforces uniqueness at the DB level, not just via find-before-insert
    checks in /auth/register (which have a race window under concurrent
    signups - two requests could both pass the find_one check before
    either insert completes). Runs on every startup; create_index is
    idempotent, so this is a no-op after the first successful run.

    email/tenant_id/api_key use sparse or a partial filter instead of a
    plain unique index because the super admin document doesn't have
    those fields the same way business owners do (email is entirely
    absent; tenant_id/api_key are explicitly None) - a plain unique index
    would treat every future None/missing value as a duplicate of the
    super admin's and reject it.
    """
    try:
        await admin_users_collection.create_index("username", unique=True)
        await admin_users_collection.create_index("email", unique=True, sparse=True)
        await admin_users_collection.create_index(
            "tenant_id", unique=True, partialFilterExpression={"tenant_id": {"$type": "string"}}
        )
        await admin_users_collection.create_index(
            "api_key", unique=True, partialFilterExpression={"api_key": {"$type": "string"}}
        )
        # Non-unique - just speeds up the two queries every single chat
        # message makes (loading a tenant's tools and documents). Doesn't
        # matter yet with a handful of test tools, but matters once real
        # businesses accumulate real data.
        await tools_collection.create_index("tenant_id")
        await documents_collection.create_index("tenant_id")
    except Exception as e:
        # Don't crash startup over this - most likely cause is duplicate
        # data already in the DB from before these indexes existed, which
        # needs manual cleanup, not a blocked boot.
        logger.error(f"Failed to create MongoDB unique indexes (duplicate data may already exist): {e}")

    # One-time (but safe to run every startup - it's a no-op once nothing
    # matches) migration for accounts created before reset_token_version
    # existed. Without this, an existing account's password-reset flow
    # fails on its very first attempt: Mongo's query matching requires the
    # field to actually exist and equal the queried value, unlike Python's
    # .get(key, 0) default - a document with reset_token_version entirely
    # absent never matches {"reset_token_version": 0}, so the atomic
    # update_one in reset_password always reports 0 rows changed.
    try:
        result = await admin_users_collection.update_many(
            {"reset_token_version": {"$exists": False}},
            {"$set": {"reset_token_version": 0}},
        )
        if result.modified_count:
            logger.info(
                f"Migrated {result.modified_count} account(s) missing "
                "reset_token_version (backfilled to 0)."
            )
    except Exception as e:
        logger.error(f"reset_token_version migration failed: {e}")


# Kept at module level so the background task isn't garbage-collected
# mid-load (asyncio only holds weak references to tasks).
_embedding_warmup_task: "asyncio.Task | None" = None


@app.on_event("startup")
async def warm_up_embedding_model():
    # Fire-and-forget on purpose: the server opens its port immediately
    # (Render's port scan doesn't time out) while the ~90MB model loads in
    # a worker thread. A chat/upload that arrives before it finishes just
    # waits on the same single load (see the lock in app/embeddings.py) -
    # it never triggers a second one. warm_up() never raises.
    global _embedding_warmup_task
    _embedding_warmup_task = asyncio.create_task(warm_up_embeddings())


@app.on_event("startup")
async def bootstrap_super_admin():
    # A startup event handler that raises makes the ENTIRE app fail to
    # boot (FastAPI/Starlette's lifespan protocol treats it as a hard
    # startup failure) - so a transient Mongo connectivity issue at the
    # exact moment of process start (e.g. the "No primary available for
    # writes" case you hit) would prevent the app from starting at all,
    # instead of starting and correctly reporting unhealthy via /health.
    # Same reasoning as the index-creation handler above this one.
    try:
        existing = await admin_users_collection.find_one({"role": "super_admin"})
    except Exception as e:
        logger.error(
            f"Could not check/bootstrap super admin - MongoDB unreachable "
            f"at startup: {e}. The app will still start; /health will "
            "correctly report unhealthy until MongoDB is reachable."
        )
        return

    if existing is not None:
        return

    username = os.environ.get("SUPERADMIN_USERNAME")
    password = os.environ.get("SUPERADMIN_PASSWORD")
    if not username or not password:
        logger.warning(
            "No super admin exists yet, and SUPERADMIN_USERNAME/"
            "SUPERADMIN_PASSWORD are not set in .env - add them and restart "
            "to create the super admin account."
        )
        return

    try:
        await admin_users_collection.insert_one({
            "role": "super_admin",
            "username": username,
            "password_hash": hash_password(password),
            "tenant_id": None,
            "api_key": None,
            "is_active": True,
            "reset_token_version": 0,
        })
        logger.info(f"Super admin account created: {username}")
    except Exception as e:
        logger.error(f"Could not create super admin account: {e}")


# ------------------------------ Auth endpoints ------------------------------

@app.post("/auth/register")
async def register_business_owner(payload: RegisterModel, request: Request):
    client_ip = get_client_ip(request)
    # Same pattern as /auth/forgot-password and /auth/login - without this,
    # registration is both a free username/tenant/email enumeration oracle
    # (distinct error messages below reveal which one is taken) and an
    # unlimited signup-spam vector.
    await check_rate_limit(f"register:{client_ip}", REGISTER_RATE_LIMIT_PER_MINUTE)

    existing = await admin_users_collection.find_one({"username": payload.username})
    if existing is not None:
        raise HTTPException(status_code=400, detail="Username already taken")

    existing_tenant = await admin_users_collection.find_one({"tenant_id": payload.tenant_id})
    if existing_tenant is not None:
        raise HTTPException(status_code=400, detail="This Business ID is already taken - please choose a different one.")

    existing_email = await admin_users_collection.find_one({"email": payload.email})
    if existing_email is not None:
        raise HTTPException(status_code=400, detail="An account with this email already exists.")

    try:
        await admin_users_collection.insert_one({
            "role": "business_owner",
            "tenant_id": payload.tenant_id,
            "business_name": payload.business_name or derive_business_name(payload.tenant_id),
            "username": payload.username,
            "email": payload.email,
            "password_hash": hash_password(payload.password),
            "api_key": generate_api_key(),
            "is_active": False,
            "reset_token_version": 0,
        })
    except DuplicateKeyError:
        # The find_one checks above catch almost every case, but there's a
        # race window between "check" and "insert" under concurrent
        # requests - two people could both pass the checks with the same
        # username/tenant_id/email before either insert lands. The unique
        # indexes (see ensure_indexes) are what actually prevent the bad
        # data; this just turns that into a clean 400 instead of a 500.
        raise HTTPException(
            status_code=400,
            detail="That username, business ID, or email is already taken - please try different values.",
        )

    return {
        "message": "Account created. It must be activated by a super admin before you can log in.",
        "username": payload.username,
    }


@app.post("/auth/login")
async def login(payload: LoginModel, request: Request):
    client_ip = get_client_ip(request)
    # Two separate limits: by IP (stops one attacker hammering many
    # accounts) and by username (stops a distributed attack - many IPs -
    # targeting one specific account). Both must pass.
    await check_rate_limit(f"login-ip:{client_ip}", LOGIN_RATE_LIMIT_PER_MINUTE)
    await check_rate_limit(f"login-user:{payload.username}", LOGIN_RATE_LIMIT_PER_MINUTE)

    user = await admin_users_collection.find_one({"username": payload.username})
    if user is None or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    if user["role"] == "business_owner" and not user.get("is_active", False):
        raise HTTPException(status_code=403, detail="Account is pending activation by a super admin")

    token = create_access_token(user)
    return {
        "access_token": token,
        "role": user["role"],
        "tenant_id": user.get("tenant_id"),
        "business_name": user.get("business_name") or (derive_business_name(user["tenant_id"]) if user.get("tenant_id") else None),
        "api_key": user.get("api_key") if user["role"] == "business_owner" else None,
    }


@app.post("/auth/forgot-password")
async def forgot_password(payload: ForgotPasswordModel, request: Request):
    """
    Always returns the same generic message whether or not the email
    exists - this is deliberate ("email enumeration" prevention). If we
    returned a different error for "email not found" vs "email sent",
    anyone could use this endpoint to check which emails are registered
    on the platform.
    """
    client_ip = get_client_ip(request)
    await check_rate_limit(f"forgot-password:{client_ip}", FORGOT_PASSWORD_RATE_LIMIT_PER_MINUTE)
    user = await admin_users_collection.find_one({"email": payload.email})
    if user is not None:
        token = create_reset_token(user)
        reset_link = f"{FRONTEND_RESET_URL}?token={token}"
        try:
            send_password_reset_email(payload.email, reset_link)
        except Exception as e:
            logger.error(f"Failed to send password reset email to {payload.email}: {e}")

    return {"message": "If that email is registered, a password reset link has been sent."}


@app.post("/auth/reset-password")
async def reset_password(payload: ResetPasswordModel):
    username, token_version = await verify_reset_token(payload.token)

    # Atomic: the filter requires reset_token_version to STILL equal what
    # this token was issued for, and the increment happens in the same
    # operation. If two requests race with the same token, only the first
    # to reach Mongo can match this filter - by the time the second's
    # update runs, the version has already moved, so modified_count is 0
    # for it. This closes the check-then-act race that existed when
    # verify_reset_token's check and this update were separate steps.
    result = await admin_users_collection.update_one(
        {"username": username, "reset_token_version": token_version},
        {
            "$set": {"password_hash": hash_password(payload.new_password)},
            "$inc": {"reset_token_version": 1},
        },
    )
    if result.modified_count == 0:
        logger.info(
            f"Reset token for '{username}' passed the pre-check (version "
            f"{token_version}) but the atomic update still found no match - "
            "another request already consumed this exact token in the gap "
            "between the pre-check and this update (classic double-submit/"
            "duplicate-tab race), not a fresh mismatch."
        )
        raise HTTPException(
            status_code=400,
            detail="This reset link has already been used or is no longer valid. Please request a new one.",
        )

    return {"message": "Password updated. You can now log in with your new password."}


# --------------------------- Super admin endpoints ---------------------------
# Manage business owner accounts: list them, activate/deactivate.
# Deactivating sets is_active=False, which both auth.get_current_business_owner
# and auth.get_tenant_from_api_key check on every request - so it takes effect
# immediately, not just on next login.

@app.get("/superadmin/business-owners")
async def list_business_owners(_admin: dict = Depends(get_current_super_admin)):
    cursor = admin_users_collection.find({"role": "business_owner"})
    owners = []
    async for u in cursor:
        owners.append({
            "id": str(u["_id"]),
            "tenant_id": u["tenant_id"],
            "business_name": u.get("business_name", ""),
            "username": u["username"],
            "is_active": u.get("is_active", False),
        })
    return owners

@app.post("/superadmin/business-owners/{owner_id}/activate")
async def activate_business_owner(owner_id: str, _admin: dict = Depends(get_current_super_admin)):
    result = await admin_users_collection.update_one(
        {"_id": parse_object_id(owner_id), "role": "business_owner"},
        {"$set": {"is_active": True}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Business owner not found")
    return {"status": "activated"}


@app.post("/superadmin/business-owners/{owner_id}/deactivate")
async def deactivate_business_owner(owner_id: str, _admin: dict = Depends(get_current_super_admin)):
    result = await admin_users_collection.update_one(
        {"_id": parse_object_id(owner_id), "role": "business_owner"},
        {"$set": {"is_active": False}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Business owner not found")
    return {"status": "deactivated"}


# ---------------------------- Chat endpoint ----------------------------
# tenant_id is resolved from the X-API-Key header, not sent by the widget -
# and get_tenant_from_api_key rejects the call outright if that business
# owner has been deactivated.
class ChatRequest(BaseModel):
    # session_id is widget-generated (Math.random() based) and flows
    # straight into Redis keys (session storage, rate limiter, the session
    # lock below) - bounding its length stops someone from sending an
    # absurdly long string to bloat those keys.
    session_id: str = Field(..., min_length=1, max_length=200)
    message: str = Field(..., min_length=1, max_length=MAX_MESSAGE_LENGTH)


def _sse(payload: dict) -> str:
    """One Server-Sent-Events frame. The widget parses each `data: ` line
    as JSON - see the `type` field on each payload for what it means:
    "token" (a text fragment to append), "tool_start" (model is calling a
    tool - show a "looking that up..." indicator), "done" (final text,
    stream is over), or "error" (stream is over, something failed)."""
    return f"data: {json.dumps(payload)}\n\n"


@app.post("/chat")
async def chat(req: ChatRequest, tenant_id: str = Depends(get_tenant_from_api_key)):
    # Two-tier limiting: per-CUSTOMER first (stops one abusive individual
    # from hammering), then per-BUSINESS overall (an aggregate ceiling that
    # protects total Groq cost even if many different real customers are
    # legitimately chatting at once). Without the per-customer tier, one
    # bad actor could burn through the entire business's shared budget and
    # lock out every other real customer talking to that same business.
    # Both of these must complete (and can raise a normal 429) BEFORE we
    # start streaming - once StreamingResponse begins, the HTTP status is
    # already sent and can't change to a 429 anymore.
    # Checked in order of scope, widest first: the whole platform, then
    # this one conversation, then this one business. Global goes first so
    # a platform-wide saturation event (many businesses active at once)
    # gets caught before spending any of a single tenant's own budget on a
    # request that was never going to reach Groq successfully anyway.
    await check_rate_limit("chat:all-tenants", GLOBAL_CHAT_RATE_LIMIT_PER_MINUTE)
    await check_rate_limit(f"chat-session:{tenant_id}:{req.session_id}", CHAT_SESSION_RATE_LIMIT_PER_MINUTE)
    await check_rate_limit(f"chat:{tenant_id}", CHAT_RATE_LIMIT_PER_MINUTE)

    # Scoped by tenant_id, not just session_id - session_id is a random
    # string the widget generates client-side (Math.random()), so two
    # different tenants' widgets could in principle generate the same one.
    # Without the tenant_id prefix, that collision would leak one tenant's
    # conversation history into another tenant's chat.
    session_key = f"{tenant_id}:{req.session_id}"

    # Distributed lock (was a per-process asyncio.Lock dict - see git
    # history) so two near-simultaneous /chat requests for the SAME
    # session_id, even landing on DIFFERENT worker processes, can't both
    # read the same starting history and have one silently clobber the
    # other's result. timeout is the lock's own TTL (a safety net in case
    # this process crashes mid-turn and never releases it); blocking_timeout
    # is how long a second request will wait before giving up.
    lock = Lock(
        get_redis(),
        name=_session_lock_name(session_key),
        timeout=MAX_CHAT_TURN_SECONDS + 10,
        blocking_timeout=10,
    )
    acquired = await lock.acquire()
    if not acquired:
        raise HTTPException(
            status_code=429,
            detail="A message for this conversation is still being processed. Please wait a moment.",
        )

    conversation = await get_session_conversation(session_key)
    conversation.append({"role": "user", "content": req.message})

    async def event_stream():
        try:
            # LLM_PROVIDER is validated to be exactly "mock" or "groq" at
            # startup (see the fail-closed check above) - nothing else can
            # reach this point, so no silent third fallback.
            if LLM_PROVIDER == "mock":
                gen = run_mock_chat_turn_stream(tenant_id, conversation)
            else:
                gen = run_groq_chat_turn_stream(tenant_id, conversation)

            # Bounds the ENTIRE multi-hop tool-calling loop, not just a
            # single LLM call or a single chunk - without this, up to 5
            # hops x a slow LLM stream x multiple tool calls per hop could
            # add up to several minutes before anything gives up. Applied
            # per-chunk (via wait_for on each __anext__) since you can't
            # wrap an already-started SSE response in a single wait_for -
            # the deadline has to be checked as the stream progresses.
            deadline = time.monotonic() + MAX_CHAT_TURN_SECONDS
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise asyncio.TimeoutError()
                try:
                    event = await asyncio.wait_for(gen.__anext__(), timeout=remaining)
                except StopAsyncIteration:
                    return

                if event["type"] == "done":
                    # Keep only the most recent messages - see MAX_CONVERSATION_HISTORY comment above.
                    updated_conversation = event["conversation"][-MAX_CONVERSATION_HISTORY:]
                    await save_session_conversation(session_key, updated_conversation)
                    yield _sse({"type": "done", "text": event["text"]})
                    return

                yield _sse(event)
        except asyncio.TimeoutError:
            logger.error(f"Chat turn exceeded {MAX_CHAT_TURN_SECONDS}s for tenant {tenant_id}")
            yield _sse({"type": "error", "message": "That took too long to answer. Please try again."})
        except groq.APITimeoutError:
            logger.error(f"LLM provider timed out for tenant {tenant_id}")
            yield _sse({"type": "error", "message": "The AI took too long to respond. Please try again."})
        except groq.APIConnectionError:
            logger.error(f"Could not reach LLM provider for tenant {tenant_id}")
            yield _sse({"type": "error", "message": "The AI service is temporarily unreachable. Please try again shortly."})
        except groq.RateLimitError as e:
            # Broken out from the generic APIStatusError branch below: this
            # is the single biggest source of "slow" responses we saw in
            # testing (30 req/min free-tier ceiling, ~40s of silent
            # SDK-level retry backoff per hit). Surface it immediately and
            # distinctly rather than let it look like a generic failure -
            # the user needs a different reaction (wait ~30-60s) than for
            # "the AI service is down".
            logger.error(f"Groq rate limit hit for tenant {tenant_id}: {e}")
            yield _sse({"type": "error", "message": "We're getting a lot of requests right now - please wait about 30 seconds and try again."})
        except groq.APIStatusError as e:
            # Covers InternalServerError, AuthenticationError, etc - real
            # subclasses of APIStatusError other than RateLimitError above.
            # Log the real status/detail for us; never echo provider
            # internals (which could include request headers/auth info) to
            # the client.
            logger.error(f"LLM provider returned an error for tenant {tenant_id}: {e.status_code} {e}")
            yield _sse({"type": "error", "message": "The AI service returned an error. Please try again."})
        except Exception as e:
            logger.error(f"Unexpected error during chat turn for tenant {tenant_id}: {e}", exc_info=True)
            yield _sse({"type": "error", "message": "Something went wrong answering that. Please try again."})
        finally:
            try:
                await lock.release()
            except Exception:
                pass  # already expired (TTL) or already released - not fatal either way

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # Tells any nginx-style proxy in front of this app (Render's
            # included) not to buffer the response - buffering would defeat
            # the entire point of streaming by holding chunks back until
            # the buffer fills or the connection closes.
            "X-Accel-Buffering": "no",
        },
    )

@app.get("/widget/config")
async def widget_config(tenant_id: str = Depends(get_tenant_from_api_key)):
    """
    Public config the widget calls on load to personalize itself - business
    name, and anything else per-tenant you add later (logo URL, brand color).
    Reuses get_tenant_from_api_key, so a deactivated business's widget can't
    even fetch its own config, same as /chat.
    """
    user = await admin_users_collection.find_one({"tenant_id": tenant_id, "role": "business_owner"})
    business_name = (user.get("business_name") if user else None) or derive_business_name(tenant_id)
    return {
        "tenant_id": tenant_id,
        "business_name": business_name,
    }


@app.get("/admin/business-name")
async def get_business_name(tenant_id: str = Depends(get_current_business_owner)):
    """Lets the dashboard show the current (or auto-derived) name in the settings form."""
    user = await admin_users_collection.find_one({"tenant_id": tenant_id, "role": "business_owner"})
    business_name = (user.get("business_name") if user else None) or derive_business_name(tenant_id)
    return {"business_name": business_name}


@app.patch("/admin/business-name")
async def update_business_name(payload: BusinessNameModel, tenant_id: str = Depends(get_current_business_owner)):
    """
    Lets a business owner set/change the name shown in their widget header
    (ChatHeader.vue) at any time - fixes accounts registered before
    business_name existed, and lets anyone rename later without support
    intervention.
    """
    result = await admin_users_collection.update_one(
        {"tenant_id": tenant_id, "role": "business_owner"},
        {"$set": {"business_name": payload.business_name}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Business owner not found")
    return {"business_name": payload.business_name}

# ----------------- Embed security: allowed websites + API key -----------------
# The widget's API key is visible to anyone who views the client's page source -
# unavoidable for an embeddable widget. What stops a copied key working on
# someone else's site is get_tenant_from_api_key (auth.py), which checks the
# embedding site against the allowed_domains saved here. tenant_id always comes
# from the JWT, never from the request body.

@app.get("/admin/embed-settings")
async def get_embed_settings(tenant_id: str = Depends(get_current_business_owner)):
    user = await admin_users_collection.find_one({"tenant_id": tenant_id, "role": "business_owner"})
    if user is None:
        raise HTTPException(status_code=404, detail="Business owner not found")
    return {
        "api_key": user.get("api_key"),
        "allowed_domains": user.get("allowed_domains") or [],
        "restriction_required": REQUIRE_ALLOWED_DOMAINS,
    }


@app.put("/admin/allowed-domains")
async def update_allowed_domains(payload: AllowedDomainsModel, tenant_id: str = Depends(get_current_business_owner)):
    result = await admin_users_collection.update_one(
        {"tenant_id": tenant_id, "role": "business_owner"},
        {"$set": {"allowed_domains": payload.domains}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Business owner not found")
    logger.info(f"Allowed domains updated for tenant '{tenant_id}': {payload.domains}")
    return {"allowed_domains": payload.domains}


@app.post("/admin/api-key/regenerate")
async def regenerate_api_key(tenant_id: str = Depends(get_current_business_owner)):
    """Replaces the widget API key. The OLD key stops working immediately (every
    request looks the key up in the DB), so a leaked/abused key can be killed
    without waiting for anyone. The owner must paste the new embed snippet on
    their site afterwards."""
    new_key = generate_api_key()
    result = await admin_users_collection.update_one(
        {"tenant_id": tenant_id, "role": "business_owner"},
        {"$set": {"api_key": new_key}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Business owner not found")
    logger.info(f"API key regenerated for tenant '{tenant_id}'")  # never log the key itself
    return {"api_key": new_key}


# ------------------------- Admin CRUD for tools -------------------------
# tenant_id comes from the logged-in business owner's JWT, never from a
# query param - so one business owner can only ever see/edit their own data.

@app.get("/admin/tools")
async def list_tools(tenant_id: str = Depends(get_current_business_owner)):
    return await get_tenant_tools(tenant_id)


@app.post("/admin/tools")
async def create_tool(tool: ToolModel, tenant_id: str = Depends(get_current_business_owner)):
    data = tool.dict()
    data["tenant_id"] = tenant_id  # override whatever the client sent - trust the token
    # Never store plaintext headers - encrypt at rest, drop the plaintext
    # key entirely so it can't accidentally leak via a raw DB dump/backup.
    data["headers_encrypted"] = encrypt_headers(data.pop("headers", {}))
    result = await tools_collection.insert_one(data)
    created = await tools_collection.find_one({"_id": result.inserted_id})
    return serialize_tool(created)


@app.put("/admin/tools/{tool_id}")
async def update_tool(tool_id: str, tool: ToolModel, tenant_id: str = Depends(get_current_business_owner)):
    data = tool.dict()
    data["tenant_id"] = tenant_id
    submitted_headers = data.pop("headers", {})
    object_id = parse_object_id(tool_id)

    if submitted_headers:
        # Admin actually typed new header values - replace what's stored.
        data["headers_encrypted"] = encrypt_headers(submitted_headers)
    else:
        # Empty headers submitted = "I didn't touch this field", not "clear
        # my secrets" - the admin UI never shows real header values back
        # (see serialize_tool), so it can't pre-fill them for editing; an
        # empty submission here just means the field was left blank.
        # $unset from the $set payload so we don't overwrite the existing
        # encrypted value with nothing.
        pass

    result = await tools_collection.update_one(
        {"_id": object_id, "tenant_id": tenant_id}, {"$set": data}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Tool not found")
    updated = await tools_collection.find_one({"_id": object_id})
    return serialize_tool(updated)


@app.delete("/admin/tools/{tool_id}")
async def delete_tool(tool_id: str, tenant_id: str = Depends(get_current_business_owner)):
    result = await tools_collection.delete_one({"_id": parse_object_id(tool_id), "tenant_id": tenant_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Tool not found")
    return {"status": "deleted"}


@app.post("/admin/tools/test")
async def test_tool(payload: ToolTestModel, tenant_id: str = Depends(get_current_business_owner)):
    """Runs a tool's request live with admin-supplied sample params, so a
    business owner can verify a live API integration (URL, params,
    headers/auth, and any response-field filter) actually works before
    saving the tool - or before relying on a customer's chat message to be
    the first real test of it. Goes through the exact same execute_tool()
    the LLM uses at runtime, including the SSRF guard and response-field
    filtering, so a "test passed" result means the real thing will behave
    the same way. Returns both the (already-filtered) result and the exact
    string the LLM would receive, so the admin can see the effect of the
    field filter and truncation before turning a real customer loose on it."""
    tool = {
        "method": payload.method,
        "url_template": payload.url_template,
        "headers": payload.headers,
        "response_fields": payload.response_fields,
    }
    result = await execute_tool(tool, payload.params)
    return {"result": result, "llm_preview": format_tool_result_for_llm(result)}


# ----------------------- Admin CRUD for documents -----------------------

@app.get("/admin/documents")
async def list_documents(tenant_id: str = Depends(get_current_business_owner)):
    return await get_tenant_documents(tenant_id)


@app.post("/admin/documents")
async def upload_document(
    file: UploadFile = File(...),
    tenant_id: str = Depends(get_current_business_owner),
):
    # Read up to (limit + 1) bytes only - never pull an arbitrarily large
    # file fully into memory just to find out afterwards it's too big.
    max_bytes = MAX_UPLOAD_SIZE_MB * 1024 * 1024
    file_bytes = await file.read(max_bytes + 1)
    if len(file_bytes) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large - max {MAX_UPLOAD_SIZE_MB}MB",
        )
    # Runs PDF extraction (CPU-bound) in a worker thread instead of
    # awaiting it directly - extract_text() is synchronous, and calling it
    # inline would block the whole event loop (every other concurrent
    # request this process is handling) for however long extraction takes.
    try:
        text = await asyncio.to_thread(extract_text, file.filename, file_bytes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    doc = DocumentModel(tenant_id=tenant_id, name=file.filename, content=text)
    result = await documents_collection.insert_one(doc.dict())
    created = await documents_collection.find_one({"_id": result.inserted_id})

    # Chunk + embed for retrieval (see app/documents.py). This is additive
    # to documents_collection above, not a replacement for it - that
    # collection still backs the admin list/delete UI and holds the full
    # original text; document_chunks_collection is what /chat actually
    # searches against. Runs synchronously in this request (embedding is
    # CPU work, offloaded to a thread inside ingest_document_chunks so it
    # doesn't block other requests) - fine for an admin upload action,
    # unlike something on the hot /chat path.
    await ingest_document_chunks(tenant_id, result.inserted_id, file.filename, text)

    return serialize_document(created)


@app.delete("/admin/documents/{doc_id}")
async def delete_document(doc_id: str, tenant_id: str = Depends(get_current_business_owner)):
    object_id = parse_object_id(doc_id)
    result = await documents_collection.delete_one({"_id": object_id, "tenant_id": tenant_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Document not found")
    # Without this, a deleted document's chunks keep surfacing in future
    # retrieval and keep getting embedded into every prompt forever.
    await delete_document_chunks(object_id)
    return {"status": "deleted"}


@app.get("/health")
async def health():
    """Real readiness check, not just "the process is running". If Mongo
    is unreachable, this app genuinely cannot serve /chat, /admin/*, or
    auth - reporting "ok" anyway would tell a load balancer/orchestrator
    to keep sending it traffic it can't actually handle. Redis is checked
    too now that sessions/rate-limiting depend on it - unlike Mongo it
    fails open elsewhere (see rate_limit.py, get_session_conversation), so
    a Redis outage alone doesn't 503 here; it's reported separately so
    it's visible in monitoring without taking the whole app "unhealthy"
    for something chat can still limp along without."""
    try:
        # Bounded ping so a Mongo problem can't make /health itself hang -
        # same reasoning as the client-level timeouts in db.py.
        await asyncio.wait_for(client.admin.command("ping"), timeout=3)
    except Exception as e:
        logger.error(f"Health check failed - MongoDB unreachable: {e}")
        raise HTTPException(status_code=503, detail="Database unavailable")

    try:
        redis_ok = await asyncio.wait_for(redis_ping(), timeout=3)
    except Exception:
        # redis_ping() already swallows connection errors and returns False;
        # this catches the TimeoutError wait_for itself raises when it has
        # to cancel a slow/hung connect attempt, which otherwise escaped
        # uncaught and made /health 500 instead of degrading gracefully.
        redis_ok = False
    if not redis_ok:
        logger.error("Health check: Redis unreachable (sessions/rate-limiting degraded)")

    return {"status": "ok", "redis": "ok" if redis_ok else "unreachable"}