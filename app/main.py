from dotenv import load_dotenv
load_dotenv()  # must run before groq_client.py / auth.py read env vars

from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from bson import ObjectId

import os
import logging

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("chatbot_platform")
from app.db import tools_collection, documents_collection, admin_users_collection
from app.models import ToolModel, DocumentModel, RegisterModel, LoginModel, BusinessNameModel, ForgotPasswordModel, ResetPasswordModel, derive_business_name, serialize_tool, serialize_document
from app.dynamic_tools import get_tenant_tools
from app.claude_client import run_chat_turn
from app.mock_llm import run_mock_chat_turn
from app.groq_client import run_groq_chat_turn
from app.documents import extract_text, get_tenant_documents
from app.email_service import send_password_reset_email
from app.rate_limit import check_rate_limit
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

CHAT_RATE_LIMIT_PER_MINUTE = int(os.environ.get("CHAT_RATE_LIMIT_PER_MINUTE", "10"))
FORGOT_PASSWORD_RATE_LIMIT_PER_MINUTE = int(os.environ.get("FORGOT_PASSWORD_RATE_LIMIT_PER_MINUTE", "5"))


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
SESSIONS: dict[str, list[dict]] = {}


# ------------------------- Bootstrap the super admin -------------------------
# There's no public "create a super admin" endpoint on purpose - only your
# team should ever hold that account. Instead, it's created automatically on
# startup from SUPERADMIN_USERNAME / SUPERADMIN_PASSWORD in .env, but only if
# one doesn't already exist yet (so this is safe to run on every restart).
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

    return {
        "message": "Account created. It must be activated by a super admin before you can log in.",
        "username": payload.username,
    }


@app.post("/auth/login")
async def login(payload: LoginModel):
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
    username = await verify_reset_token(payload.token)

    result = await admin_users_collection.update_one(
        {"username": username},
        {
            "$set": {"password_hash": hash_password(payload.new_password)},
            # Bumping this invalidates the token just used (and any other
            # unused reset links for this account) - see auth.py.
            "$inc": {"reset_token_version": 1},
        },
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Account not found")

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
    session_id: str
    message: str


class ChatResponse(BaseModel):
    reply: str


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, tenant_id: str = Depends(get_tenant_from_api_key)):
    check_rate_limit(f"chat:{tenant_id}", CHAT_RATE_LIMIT_PER_MINUTE)

    # Scoped by tenant_id, not just session_id - session_id is a random
    # string the widget generates client-side (Math.random()), so two
    # different tenants' widgets could in principle generate the same one.
    # Without the tenant_id prefix, that collision would leak one tenant's
    # conversation history into another tenant's chat.
    session_key = f"{tenant_id}:{req.session_id}"

    conversation = SESSIONS.get(session_key, [])
    conversation.append({"role": "user", "content": req.message})

    if LLM_PROVIDER == "mock":
        reply_text, updated_conversation = await run_mock_chat_turn(tenant_id, conversation)
    elif LLM_PROVIDER == "groq":
        reply_text, updated_conversation = await run_groq_chat_turn(tenant_id, conversation)
    else:
        reply_text, updated_conversation = await run_chat_turn(tenant_id, conversation)

    SESSIONS[session_key] = updated_conversation
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
    result = await tools_collection.insert_one(data)
    created = await tools_collection.find_one({"_id": result.inserted_id})
    return serialize_tool(created)


@app.put("/admin/tools/{tool_id}")
async def update_tool(tool_id: str, tool: ToolModel, tenant_id: str = Depends(get_current_business_owner)):
    data = tool.dict()
    data["tenant_id"] = tenant_id
    result = await tools_collection.update_one(
        {"_id": parse_object_id(tool_id), "tenant_id": tenant_id}, {"$set": data}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Tool not found")
    updated = await tools_collection.find_one({"_id": parse_object_id(tool_id)})
    return serialize_tool(updated)


@app.delete("/admin/tools/{tool_id}")
async def delete_tool(tool_id: str, tenant_id: str = Depends(get_current_business_owner)):
    result = await tools_collection.delete_one({"_id": parse_object_id(tool_id), "tenant_id": tenant_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Tool not found")
    return {"status": "deleted"}


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
    text = extract_text(file.filename, file_bytes)
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