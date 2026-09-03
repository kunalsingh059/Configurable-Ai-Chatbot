"""
Lightweight document context - NOT full RAG. Now backed by Mongo.
"""

from io import BytesIO
from pypdf import PdfReader
from app.db import documents_collection
from app.models import serialize_document

MAX_CHARS_PER_DOC = 3000
MAX_TOTAL_CHARS = 8000


def extract_text(filename: str, file_bytes: bytes) -> str:
    if filename.lower().endswith(".pdf"):
        reader = PdfReader(BytesIO(file_bytes))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    return file_bytes.decode("utf-8", errors="ignore")


async def get_tenant_documents(tenant_id: str) -> list[dict]:
    cursor = documents_collection.find({"tenant_id": tenant_id})
    return [serialize_document(doc) async for doc in cursor]


async def build_documents_context(tenant_id: str) -> str:
    docs = await get_tenant_documents(tenant_id)
    if not docs:
        return ""

    sections = []
    total = 0
    for doc in docs:
        chunk = (doc.get("content") or "")[:MAX_CHARS_PER_DOC]
        if total + len(chunk) > MAX_TOTAL_CHARS:
            break
        sections.append(f"--- {doc['name']} ---\n{chunk}")
        total += len(chunk)

    if not sections:
        return ""

    return (
        "\n\nYou also have access to these reference documents. Use them to "
        "answer policy/FAQ/general questions when no tool is a better fit:\n\n"
        + "\n\n".join(sections)
    )