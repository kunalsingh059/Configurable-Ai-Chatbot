"""
Mongo doesn't enforce a schema the way SQL tables do, so these Pydantic
models exist purely for validation and API request/response shaping —
not as an ORM layer. Mongo documents are just Python dicts under the hood.
"""

import re
from urllib.parse import urlparse
from pydantic import BaseModel, Field, EmailStr, field_validator, model_validator
from typing import Optional
from datetime import datetime

# Shared password policy - used by both registration and password-reset.
# Not trying to be a full strength-meter, just ruling out "123" / "aaaaaaaa":
# minimum length, at least one letter, at least one digit.
PASSWORD_MIN_LENGTH = 8


def _validate_password_strength(password: str) -> str:
    if len(password) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"Password must be at least {PASSWORD_MIN_LENGTH} characters long")
    if not re.search(r"[A-Za-z]", password):
        raise ValueError("Password must contain at least one letter")
    if not re.search(r"[0-9]", password):
        raise ValueError("Password must contain at least one number")
    return password


# tenant_id doubles as a URL-safe/slug identifier (used in widget config,
# possibly subdomains later) - keep it to lowercase letters, numbers and
# hyphens only, no leading/trailing hyphen.
TENANT_ID_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"


class ToolModel(BaseModel):
    tenant_id: str = "default"
    name: str
    description: str
    method: str = "GET"
    url_template: str
    headers: dict = {}
    params_schema: dict
    response_fields: list[str] = []

    @field_validator("url_template")
    @classmethod
    def validate_url_template(cls, v: str) -> str:
        v = v.strip()
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("URL template must start with http:// or https://")
        return v


class FeedbackModel(BaseModel):
    """User rating (up/down) and optional comment for a specific chatbot response."""
    session_id: str = Field(..., min_length=1, max_length=200)
    message_id: str = Field(..., min_length=1, max_length=200)
    rating: str = Field(..., pattern="^(up|down|none)$")
    comment: Optional[str] = Field(None, max_length=500)
    user_question: Optional[str] = Field(None, max_length=1000)
    bot_answer: Optional[str] = Field(None, max_length=5000)


class UnansweredStatusUpdateModel(BaseModel):
    status: str = Field(..., pattern="^(open|resolved|ignored)$")


class TenantLimitsModel(BaseModel):
    """Quotas / rate limits for a tenant to protect server costs and prevent abuse."""
    daily_message_limit: Optional[int] = Field(None, ge=1, le=1000000, description="Max messages per day (null for unlimited)")
    monthly_message_limit: Optional[int] = Field(None, ge=1, le=10000000, description="Max messages per month (null for unlimited)")


HEX_COLOR_PATTERN = r"^#(?:[0-9a-fA-F]{3}){1,2}$"

class BotConfigModel(BaseModel):
    """Per-tenant chatbot appearance and personality configuration."""
    bot_name: Optional[str] = Field(None, max_length=100)
    welcome_message: Optional[str] = Field(None, max_length=300)
    primary_color: Optional[str] = Field(None, pattern=HEX_COLOR_PATTERN)
    avatar_url: Optional[str] = Field(None, max_length=500)
    tone: Optional[str] = Field("friendly", pattern="^(friendly|professional|casual)$")
    quick_replies: list[str] = Field(default_factory=list, max_length=6)
    reply_in_user_language: bool = True
    handoff_enabled: bool = False

    @field_validator("quick_replies")
    @classmethod
    def validate_quick_replies(cls, v: list[str]) -> list[str]:
        cleaned = []
        for item in v:
            item_str = item.strip()
            if item_str:
                if len(item_str) > 40:
                    raise ValueError(f"Quick reply '{item_str[:15]}...' exceeds 40 characters")
                cleaned.append(item_str)
        return cleaned[:6]

    @field_validator("avatar_url")
    @classmethod
    def validate_avatar_url(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return None
        v = v.strip()
        if not v.startswith("https://"):
            raise ValueError("Avatar URL must begin with https://")
        return v


class HandoffRequestModel(BaseModel):
    """Customer request to contact human support or leave a lead (T9)."""
    session_id: str = Field(..., min_length=1, max_length=200)
    name: str = Field(..., min_length=1, max_length=100)
    email: Optional[str] = Field(None, max_length=150)
    phone: Optional[str] = Field(None, max_length=30)
    message: Optional[str] = Field("", max_length=1000)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name cannot be empty")
        return v

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return None
        v = v.strip()
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v):
            raise ValueError("Invalid email format")
        return v

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return None
        v = v.strip()
        cleaned = re.sub(r"[\s\-\(\)\+]", "", v)
        if len(cleaned) < 5 or not cleaned.isdigit():
            raise ValueError("Invalid phone number format")
        return v

    @model_validator(mode="after")
    def check_contact_method(self):
        if not self.email and not self.phone:
            raise ValueError("Either email or phone number must be provided")
        return self


class LeadStatusUpdateModel(BaseModel):
    status: str = Field(..., pattern="^(new|contacted|closed)$")



class ToolTestModel(BaseModel):
    """Body for the 'test this tool live' admin action - same shape as a
    tool's request-building fields, minus the params_schema (the admin
    supplies actual sample params directly instead of a schema to
    validate against, since this is a one-off manual run, not something
    the LLM is calling)."""
    method: str = "GET"
    url_template: str
    headers: dict = {}
    params: dict = {}
    response_fields: list[str] = []


class DocumentModel(BaseModel):
    tenant_id: str = "default"
    name: str
    content: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class RegisterModel(BaseModel):
    """Self-registration for a business owner. They always start inactive -
    role and is_active are never taken from the request, only set server-side,
    so nobody can register themselves as an already-active super_admin."""
    tenant_id: str = Field(..., min_length=3, max_length=50, pattern=TENANT_ID_PATTERN)  # business identifier, e.g. "tasty-bites"
    business_name: Optional[str] = Field(None, max_length=100)  # display name; auto-derived from tenant_id if omitted (see derive_business_name)
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr  # used only for password-reset emails
    password: str = Field(..., min_length=PASSWORD_MIN_LENGTH, max_length=128)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, v: str) -> str:
        # Collapse repeated whitespace and trim ends, so "  Vikas   Bhamotriya "
        # doesn't sneak through as a distinct username from "Vikas Bhamotriya".
        v = re.sub(r"\s+", " ", v).strip()
        if not v:
            raise ValueError("Username cannot be blank")
        return v

    @field_validator("password")
    @classmethod
    def check_password_strength(cls, v: str) -> str:
        return _validate_password_strength(v)

    @field_validator("business_name")
    @classmethod
    def strip_business_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        return v or None


class LoginModel(BaseModel):
    # Deliberately loose (no pattern/EmailStr) - this validates an existing
    # credential, not new input, so we don't want to reject legitimate older
    # accounts that predate stricter rules. Auth itself is checked in main.py.
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1, max_length=128)


class BusinessNameModel(BaseModel):
    business_name: str = Field(..., min_length=1, max_length=100)


# Domains many unrelated people can publish sites under. Allowing e.g.
# "vercel.app" would authorize EVERY site hosted on vercel.app (including an
# attacker's), because a listed domain also matches its subdomains - so these
# must be entered as a full address instead (mysite.vercel.app).
_SHARED_SUFFIXES = {
    "vercel.app", "netlify.app", "onrender.com", "github.io", "pages.dev",
    "workers.dev", "herokuapp.com", "web.app", "firebaseapp.com",
    "azurewebsites.net", "cloudfront.net", "amazonaws.com", "ngrok.io",
    "ngrok-free.app", "trycloudflare.com", "surge.sh", "glitch.me", "repl.co",
    "co.in", "net.in", "org.in", "ac.in", "gov.in", "co.uk", "org.uk",
    "com.au", "co.jp", "com.br",
}
_HOSTNAME_RE = re.compile(
    r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*"
)


def normalize_domain(raw: str) -> str:
    """Turns whatever an owner typed - "https://www.MySite.com/menu",
    "mysite.com:3000", "MYSITE.COM" - into a bare lowercase hostname
    ("www.mysite.com"), or raises ValueError. Scheme, port and path are dropped
    because the check compares hostnames only."""
    value = (raw or "").strip().lower()
    if not value:
        raise ValueError("Domain cannot be blank")
    if len(value) > 300:
        raise ValueError("Domain is too long")
    if "://" not in value:
        value = "//" + value  # so urlparse treats it as a host, not a path
    try:
        host = urlparse(value).hostname
    except ValueError:
        host = None
    if not host or len(host) > 253 or not _HOSTNAME_RE.fullmatch(host):
        raise ValueError(f"'{raw.strip()}' is not a valid domain")
    if host != "localhost" and "." not in host:
        # A bare "com" would match every .com website.
        raise ValueError(f"'{raw.strip()}' is not a valid domain - use your full site address, e.g. mysite.com")
    if host in _SHARED_SUFFIXES:
        raise ValueError(
            f"'{host}' is shared by many different websites - enter your own full address instead (e.g. mysite.{host})"
        )
    return host


class AllowedDomainsModel(BaseModel):
    """The websites allowed to show this business's chat widget. An empty list
    means 'no restriction' (unless REQUIRE_ALLOWED_DOMAINS is on - see auth.py)."""
    domains: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("domains")
    @classmethod
    def normalize_all(cls, v: list[str]) -> list[str]:
        cleaned: list[str] = []
        for item in v:
            host = normalize_domain(item)
            if host not in cleaned:
                cleaned.append(host)
        return cleaned


class ForgotPasswordModel(BaseModel):
    email: EmailStr


class ResetPasswordModel(BaseModel):
    token: str
    new_password: str = Field(..., min_length=PASSWORD_MIN_LENGTH, max_length=128)

    @field_validator("new_password")
    @classmethod
    def check_password_strength(cls, v: str) -> str:
        return _validate_password_strength(v)


def derive_business_name(tenant_id: str) -> str:
    """
    Turns a tenant_id like "life-secure-pathology" into a display name like
    "Life Secure Pathology Assistant" - used whenever a business owner
    hasn't set a custom business_name (new registrations that skipped it,
    and any account created before this field existed at all). Fully
    automatic: no manual DB edit or registration step required.
    """
    words = tenant_id.replace("-", " ").replace("_", " ").split()
    title = " ".join(word.capitalize() for word in words) if words else tenant_id
    return f"{title} Assistant" if title else "Support Assistant"


def serialize_tool(doc: dict) -> dict:
    """Mongo's _id is an ObjectId, not JSON-serializable by default -
    convert to a plain string id for API responses.

    SECURITY: headers may contain API keys/Bearer tokens for the business
    owner's own third-party integration - this is the admin-facing (masked)
    serializer, used by GET/POST/PUT /admin/tools. It returns only the
    HEADER NAMES (header_keys), never the encrypted-at-rest values, so a
    stored secret is never sent to the browser. Runtime chat execution uses
    get_tenant_tools_for_execution() instead, which decrypts real values
    server-side only - see dynamic_tools.py."""
    from app.crypto import decrypt_headers  # local import avoids a hard
    # dependency for any code that only needs the other model classes
    header_keys = list(decrypt_headers(doc.get("headers_encrypted")).keys())
    return {
        "id": str(doc["_id"]),
        "tenant_id": doc["tenant_id"],
        "name": doc["name"],
        "description": doc["description"],
        "method": doc.get("method", "GET"),
        "url_template": doc["url_template"],
        "header_keys": header_keys,
        "params_schema": doc["params_schema"],
        "response_fields": doc.get("response_fields", []),
    }


def serialize_document(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "tenant_id": doc["tenant_id"],
        "name": doc["name"],
        "content": doc["content"],
    }