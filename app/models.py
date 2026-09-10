"""
Mongo doesn't enforce a schema the way SQL tables do, so these Pydantic
models exist purely for validation and API request/response shaping —
not as an ORM layer. Mongo documents are just Python dicts under the hood.
"""

import re
from pydantic import BaseModel, Field, EmailStr, field_validator
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
    # Optional allowlist of top-level keys to keep from a successful JSON
    # response before it's sent to the LLM. Empty = send everything
    # (subject to the character truncation in format_tool_result_for_llm).
    # Live APIs often return far more than a chat answer needs - Open Food
    # Facts, for example, returns 100+ fields per product - so trimming to
    # just the fields that matter keeps every follow-up turn cheaper and
    # keeps the model from getting distracted by irrelevant data.
    response_fields: list[str] = []


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