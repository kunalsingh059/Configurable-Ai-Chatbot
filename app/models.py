"""
Mongo doesn't enforce a schema the way SQL tables do, so these Pydantic
models exist purely for validation and API request/response shaping —
not as an ORM layer. Mongo documents are just Python dicts under the hood.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ToolModel(BaseModel):
    tenant_id: str = "default"
    name: str
    description: str
    method: str = "GET"
    url_template: str
    headers: dict = {}
    params_schema: dict


class DocumentModel(BaseModel):
    tenant_id: str = "default"
    name: str
    content: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class RegisterModel(BaseModel):
    """Self-registration for a business owner. They always start inactive -
    role and is_active are never taken from the request, only set server-side,
    so nobody can register themselves as an already-active super_admin."""
    tenant_id: str  # business identifier, e.g. "tasty-bites"
    business_name: Optional[str] = None  # display name; auto-derived from tenant_id if omitted (see derive_business_name)
    username: str
    email: str  # used only for password-reset emails
    password: str


class LoginModel(BaseModel):
    username: str
    password: str


class BusinessNameModel(BaseModel):
    business_name: str


class ForgotPasswordModel(BaseModel):
    email: str


class ResetPasswordModel(BaseModel):
    token: str
    new_password: str


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
    convert to a plain string id for API responses."""
    return {
        "id": str(doc["_id"]),
        "tenant_id": doc["tenant_id"],
        "name": doc["name"],
        "description": doc["description"],
        "method": doc.get("method", "GET"),
        "url_template": doc["url_template"],
        "headers": doc.get("headers", {}),
        "params_schema": doc["params_schema"],
    }


def serialize_document(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "tenant_id": doc["tenant_id"],
        "name": doc["name"],
        "content": doc["content"],
    }