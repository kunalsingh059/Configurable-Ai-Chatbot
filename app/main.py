from dotenv import load_dotenv
load_dotenv()  # must run before groq_client.py / auth.py read env vars

from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from bson import ObjectId
from pymongo.errors import DuplicateKeyError

import os
import time
import asyncio
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
from app.db import tools_collection, documents_collection, admin_users_collection
from app.models import ToolModel, ToolTestModel, DocumentModel, RegisterModel, LoginModel, BusinessNameModel, ForgotPasswordModel, ResetPasswordModel, derive_business_name, serialize_tool, serialize_document
from app.dynamic_tools import get_tenant_tools, execute_tool, format_tool_result_for_llm
from app.crypto import encrypt_headers
from app.claude_client import run_chat_turn
from app.mock_llm import run_mock_chat_turn
from app.groq_client import run_groq_chat_turn
from app.documents import extract_text, get_tenant_documents
from app.email_service import send_password_reset_email
from app.rate_limit import check_rate_limit
import groq
import anthropic
from app.auth import (
    hash_password, verify_password, generate_api_key, create_access_token,
    create_reset_token, verify_reset_token,
    get_current_business_owner, get_current_super_admin, get_tenant_from_api_key,
)

# Which LLM powers the chat: "mock" (free, fake reasoning, tests plumbing
# only), "groq" (free tier, real reasoning), or "anthropic" (paid, the
# eventual production choice). Set LLM_PROVIDER in .env.
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "mock").lower()

if LLM_PROVIDER == "mock":
    # Not a hard failure - mock mode is legitimate for local dev/testing -
    # but it's easy to forget to set LLM_PROVIDER in a real deploy and never
    # notice the chatbot is answering with fake canned logic. Make it loud.
    logger.warning(
        "LLM_PROVIDER is not set (or set to 'mock') - the chatbot "
        "is running on FAKE mock responses, not a real model. Set "
        "LLM_PROVIDER=groq (and GROQ_API_KEY) in .env for real answers."
    )
elif LLM_PROVIDER == "groq" and not os.environ.get("GROQ_API_KEY"):
    # Fail at startup, not on the first person's chat message - same
    # principle as the SUPERADMIN_USERNAME/PASSWORD check below, just for
    # a config error that would otherwise only surface as a 500 in prod.
    raise RuntimeError(
        "LLM_PROVIDER=groq but GROQ_API_KEY is not set in .env - the app "
        "cannot start without it."
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
CHAT_RATE_LIMIT_PER_MINUTE = int(os.environ.get("CHAT_RATE_LIMIT_PER_MINUTE", "300"))

# Wall-clock ceiling on an ENTIRE chat turn - covers everything: the LLM
# call(s), every tool-call hop (up to 5), and every tool's own HTTP request.
# The per-call timeouts elsewhere (LLM_REQUEST_TIMEOUT_SECONDS, the 10s tool
# timeout in dynamic_tools.py) bound each individual piece, but worst case
# those can still stack up to several minutes; this is the actual backstop
# that guarantees a customer never waits past this no matter what combination
# of slow LLM calls + slow tool calls happens along the way.
OVERALL_CHAT_TIMEOUT_SECONDS = int(os.environ.get("OVERALL_CHAT_TIMEOUT_SECONDS", "45"))
FORGOT_PASSWORD_RATE_LIMIT_PER_MINUTE = int(os.environ.get("FORGOT_PASSWORD_RATE_LIMIT_PER_MINUTE", "5"))
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


# TEMPORARY: in-memory session store. Replace with Redis in Day 5.
# Each value is (last_access_epoch_seconds, conversation_list) - the
# timestamp lets _cleanup_idle_sessions() evict sessions nobody's used in a
# while, so this dict doesn't grow forever over days/weeks of traffic.
SESSIONS: dict[str, tuple[float, list[dict]]] = {}

MAX_MESSAGE_LENGTH = int(os.environ.get("MAX_MESSAGE_LENGTH", "1000"))
# Messages, not turns - each user+assistant exchange is 2 entries. Trimming
# this bounds both memory per session AND the Groq token cost of every
# future message in a long conversation (the full history is resent every turn).
MAX_CONVERSATION_HISTORY = int(os.environ.get("MAX_CONVERSATION_HISTORY", "20"))
SESSION_IDLE_TIMEOUT_MINUTES = int(os.environ.get("SESSION_IDLE_TIMEOUT_MINUTES", "60"))
# Bounds the WHOLE multi-hop tool-calling loop for one chat message, not
# just a single LLM call - see the /chat endpoint for why this matters.
MAX_CHAT_TURN_SECONDS = int(os.environ.get("MAX_CHAT_TURN_SECONDS", "45"))

_last_session_cleanup = 0.0


def _cleanup_idle_sessions() -> None:
    """Evicts sessions idle longer than SESSION_IDLE_TIMEOUT_MINUTES. Runs at
    most once every 5 minutes (not on every request - SESSIONS can hold a
    lot of entries at scale, no need to sweep it on every single message)."""
    global _last_session_cleanup
    now = time.time()
    if now - _last_session_cleanup < 300:
        return
    _last_session_cleanup = now
    cutoff = now - (SESSION_IDLE_TIMEOUT_MINUTES * 60)
    stale_keys = [k for k, (last_access, _) in SESSIONS.items() if last_access < cutoff]
    for k in stale_keys:
        del SESSIONS[k]
        _SESSION_LOCKS.pop(k, None)  # no point keeping a lock for a session that no longer exists


# Per-session lock, created on first use. Guards the read-modify-write of a
# single session's conversation (read history -> call LLM -> write updated
# history back) so two near-simultaneous /chat requests for the SAME
# session_id can't both read the same starting history, run independently,
# and have the second write silently clobber the first's result. Locks are
# per-KEY, not global - different sessions never block each other, only two
# requests for the exact same session do. defaultdict is safe here without
# extra locking of its own: this line never awaits, and the event loop is
# single-threaded, so two "concurrent" tasks can't actually interleave
# inside it.
from collections import defaultdict
_SESSION_LOCKS: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


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


@app.on_event("startup")
async def bootstrap_super_admin():
    existing = await admin_users_collection.find_one({"role": "super_admin"})
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

    await admin_users_collection.insert_one({
        "role": "super_admin",
        "username": username,
        "password_hash": hash_password(password),
        "tenant_id": None,
        "api_key": None,
        "is_active": True,
    })
    logger.info(f"Super admin account created: {username}")


# ------------------------------ Auth endpoints ------------------------------

@app.post("/auth/register")
async def register_business_owner(payload: RegisterModel):
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
    client_ip = request.client.host if request.client else "unknown"
    # Two separate limits: by IP (stops one attacker hammering many
    # accounts) and by username (stops a distributed attack - many IPs -
    # targeting one specific account). Both must pass.
    check_rate_limit(f"login-ip:{client_ip}", LOGIN_RATE_LIMIT_PER_MINUTE)
    check_rate_limit(f"login-user:{payload.username}", LOGIN_RATE_LIMIT_PER_MINUTE)

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
    client_ip = request.client.host if request.client else "unknown"
    check_rate_limit(f"forgot-password:{client_ip}", FORGOT_PASSWORD_RATE_LIMIT_PER_MINUTE)
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
    # straight into in-memory dict keys (SESSIONS, rate limiter, the
    # session lock below) - bounding its length stops someone from sending
    # an absurdly long string to bloat those keys/dicts.
    session_id: str = Field(..., min_length=1, max_length=200)
    message: str = Field(..., min_length=1, max_length=MAX_MESSAGE_LENGTH)


class ChatResponse(BaseModel):
    reply: str


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, tenant_id: str = Depends(get_tenant_from_api_key)):
    # Two-tier limiting: per-CUSTOMER first (stops one abusive individual
    # from hammering), then per-BUSINESS overall (an aggregate ceiling that
    # protects total Groq cost even if many different real customers are
    # legitimately chatting at once). Without the per-customer tier, one
    # bad actor could burn through the entire business's shared budget and
    # lock out every other real customer talking to that same business.
    check_rate_limit(f"chat-session:{tenant_id}:{req.session_id}", CHAT_SESSION_RATE_LIMIT_PER_MINUTE)
    check_rate_limit(f"chat:{tenant_id}", CHAT_RATE_LIMIT_PER_MINUTE)
    _cleanup_idle_sessions()

    # Scoped by tenant_id, not just session_id - session_id is a random
    # string the widget generates client-side (Math.random()), so two
    # different tenants' widgets could in principle generate the same one.
    # Without the tenant_id prefix, that collision would leak one tenant's
    # conversation history into another tenant's chat.
    session_key = f"{tenant_id}:{req.session_id}"

    # Serializes concurrent requests for this exact session - see
    # _SESSION_LOCKS' own docstring above for why this is needed at all.
    async with _SESSION_LOCKS[session_key]:
        _, conversation = SESSIONS.get(session_key, (0.0, []))
        conversation.append({"role": "user", "content": req.message})

        try:
            # Bounds the ENTIRE multi-hop tool-calling loop, not just a
            # single LLM call - without this, up to 5 hops x a 20s LLM
            # timeout x multiple sequential tool calls per hop (10s each)
            # could add up to several minutes before anything fails.
            async def _run_chat_turn():
                if LLM_PROVIDER == "mock":
                    return await run_mock_chat_turn(tenant_id, conversation)
                elif LLM_PROVIDER == "groq":
                    return await run_groq_chat_turn(tenant_id, conversation)
                else:
                    return await run_chat_turn(tenant_id, conversation)

            reply_text, updated_conversation = await asyncio.wait_for(
                _run_chat_turn(), timeout=MAX_CHAT_TURN_SECONDS
            )
        except asyncio.TimeoutError:
            logger.error(f"Chat turn exceeded {MAX_CHAT_TURN_SECONDS}s for tenant {tenant_id}")
            raise HTTPException(
                status_code=504,
                detail="That took too long to answer. Please try again.",
            )
        except (groq.APITimeoutError, anthropic.APITimeoutError):
            logger.error(f"LLM provider timed out for tenant {tenant_id}")
            raise HTTPException(status_code=504, detail="The AI took too long to respond. Please try again.")
        except (groq.APIConnectionError, anthropic.APIConnectionError):
            logger.error(f"Could not reach LLM provider for tenant {tenant_id}")
            raise HTTPException(status_code=503, detail="The AI service is temporarily unreachable. Please try again shortly.")
        except (groq.APIStatusError, anthropic.APIStatusError) as e:
            # Covers RateLimitError, InternalServerError, AuthenticationError,
            # etc - all real subclasses of APIStatusError in both SDKs. Log
            # the real status/detail for us; never echo provider internals
            # (which could include request headers/auth info) to the client.
            logger.error(f"LLM provider returned an error for tenant {tenant_id}: {e.status_code} {e}")
            raise HTTPException(status_code=502, detail="The AI service returned an error. Please try again.")
        except HTTPException:
            raise  # let our own intentional HTTPExceptions (e.g. from execute_tool) pass through untouched
        except Exception as e:
            logger.error(f"Unexpected error during chat turn for tenant {tenant_id}: {e}", exc_info=True)
            raise HTTPException(status_code=502, detail="Something went wrong answering that. Please try again.")

        # Keep only the most recent messages - see MAX_CONVERSATION_HISTORY comment above.
        updated_conversation = updated_conversation[-MAX_CONVERSATION_HISTORY:]

        SESSIONS[session_key] = (time.time(), updated_conversation)
        return ChatResponse(reply=reply_text)

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
    text = await asyncio.to_thread(extract_text, file.filename, file_bytes)
    doc = DocumentModel(tenant_id=tenant_id, name=file.filename, content=text)
    result = await documents_collection.insert_one(doc.dict())
    created = await documents_collection.find_one({"_id": result.inserted_id})
    return serialize_document(created)


@app.delete("/admin/documents/{doc_id}")
async def delete_document(doc_id: str, tenant_id: str = Depends(get_current_business_owner)):
    result = await documents_collection.delete_one({"_id": parse_object_id(doc_id), "tenant_id": tenant_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"status": "deleted"}


@app.get("/health")
async def health():
    return {"status": "ok"}