"""
Real RAG, replacing the old "dump up to 8000 raw chars into the system
prompt" approach. At upload time, a document's text is chunked and each
chunk embedded (see app/embeddings.py) and stored in document_chunks_collection.
At chat time, the user's message is embedded and Atlas Vector Search finds
the top-k most relevant chunks across ALL of that tenant's documents,
instead of every document's first ~3000 chars regardless of relevance.

This needs an Atlas Vector Search index named "document_chunks_vector_index"
on document_chunks_collection - see docs/rag-setup.md for the exact index
definition and how to create it in the Atlas UI (a few clicks, no code).
"""

from io import BytesIO
from bson import ObjectId
from pypdf import PdfReader
from app.db import documents_collection, document_chunks_collection
from app.models import serialize_document
from app.chunking import chunk_text
from app.embeddings import embed_texts, embed_text

MAX_PDF_PAGES = 50
MAX_EXTRACTED_CHARS = 200_000

TOP_K = 5  # how many chunks to retrieve per chat message
VECTOR_INDEX_NAME = "document_chunks_vector_index"

ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md"}


def extract_text(filename: str, file_bytes: bytes) -> str:
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {ext or 'unknown'}")

    if filename.lower().endswith(".pdf"):
        reader = PdfReader(BytesIO(file_bytes))
        chunks = []
        total_chars = 0
        for page in reader.pages[:MAX_PDF_PAGES]:
            text = page.extract_text() or ""
            chunks.append(text)
            total_chars += len(text)
            if total_chars >= MAX_EXTRACTED_CHARS:
                break
        return "\n".join(chunks)[:MAX_EXTRACTED_CHARS]
    return file_bytes.decode("utf-8", errors="ignore")[:MAX_EXTRACTED_CHARS]


async def get_tenant_documents(tenant_id: str) -> list[dict]:
    cursor = documents_collection.find({"tenant_id": tenant_id})
    return [serialize_document(doc) async for doc in cursor]


async def ingest_document_chunks(tenant_id: str, doc_id: ObjectId, doc_name: str, text: str) -> int:
    """Chunks a document's text, embeds every chunk in one batched call,
    and stores them in document_chunks_collection. Additive to
    documents_collection, not a replacement for it."""
    pieces = chunk_text(text)
    if not pieces:
        return 0

    vectors = await embed_texts(pieces)

    docs_to_insert = [
        {
            "tenant_id": tenant_id,
            "doc_id": doc_id,
            "doc_name": doc_name,
            "chunk_text": piece,
            "embedding": vector,
        }
        for piece, vector in zip(pieces, vectors)
    ]
    await document_chunks_collection.insert_many(docs_to_insert)
    return len(docs_to_insert)


async def delete_document_chunks(doc_id: ObjectId) -> None:
    """Companion to DELETE /admin/documents/{doc_id} - without this, a
    deleted document's chunks would silently keep surfacing in retrieval."""
    await document_chunks_collection.delete_many({"doc_id": doc_id})


async def retrieve_relevant_chunks(tenant_id: str, query: str, top_k: int = TOP_K) -> list[dict]:
    """Embeds the user's message and runs Atlas Vector Search scoped to
    this tenant only via the filter field."""
    if not query or not query.strip():
        return []

    query_vector = await embed_text(query)

    pipeline = [
        {
            "$vectorSearch": {
                "index": VECTOR_INDEX_NAME,
                "path": "embedding",
                "queryVector": query_vector,
                "filter": {"tenant_id": tenant_id},
                "numCandidates": max(top_k * 20, 100),
                "limit": top_k,
            }
        },
        {
            "$project": {
                "_id": 0,
                "doc_name": 1,
                "chunk_text": 1,
                "score": {"$meta": "vectorSearchScore"},
            }
        },
    ]

    return [doc async for doc in document_chunks_collection.aggregate(pipeline)]


async def build_documents_context(tenant_id: str, query: str) -> str:
    """Query-aware replacement for the old flat dump."""
    chunks = await retrieve_relevant_chunks(tenant_id, query)
    if not chunks:
        return ""

    sections = [f"--- {c['doc_name']} ---\n{c['chunk_text']}" for c in chunks]

    return (
        "\n\nHere are the most relevant excerpts from this business's reference "
        "documents for the user's current question. Use them to answer "
        "policy/FAQ/general questions when no tool is a better fit; if they "
        "don't actually answer the question, say so rather than guessing:\n\n"
        + "\n\n".join(sections)
    )