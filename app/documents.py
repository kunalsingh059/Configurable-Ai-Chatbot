"""
Lightweight document context - NOT full RAG. Now backed by Mongo.
"""

from io import BytesIO
from pypdf import PdfReader
from app.db import documents_collection
from app.models import serialize_document

MAX_CHARS_PER_DOC = 3000
MAX_TOTAL_CHARS = 8000
# Hard stop on page extraction, independent of character count - a PDF with
# an enormous page count (even if each page is sparse/nearly blank) would
# otherwise force pypdf to walk every single page before extract_text()
# ever gets to apply the character truncation below. This runs BEFORE that
# truncation, bounding the actual CPU work, not just the final stored size.
MAX_PDF_PAGES = 50


def extract_text(filename: str, file_bytes: bytes) -> str:
    """CPU-bound (especially PdfReader/extract_text) - callers on the async
    request path should run this via asyncio.to_thread(), not await it
    directly, or a single large upload blocks the whole event loop (every
    other concurrent request on this process) for however long extraction
    takes. See the /admin/documents upload endpoint in main.py."""
    if filename.lower().endswith(".pdf"):
        reader = PdfReader(BytesIO(file_bytes))
        chunks = []
        total_chars = 0
        for page in reader.pages[:MAX_PDF_PAGES]:
            text = page.extract_text() or ""
            chunks.append(text)
            total_chars += len(text)
            # Stop early once we've clearly got more than enough - anything
            # beyond MAX_CHARS_PER_DOC gets truncated later anyway (see
            # build_documents_context), so there's no point spending CPU
            # extracting pages 40-200 of an oversized PDF just to throw
            # nearly all of it away a moment later.
            if total_chars >= MAX_CHARS_PER_DOC:
                break
        return "\n".join(chunks)
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