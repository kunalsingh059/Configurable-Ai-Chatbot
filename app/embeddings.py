"""
Local, free embedding model for RAG - sentence-transformers running on CPU,
loaded once per process and reused for every call. No API key, no per-call
cost, no network round-trip once the model is cached locally - so it's safe
to call both at document-upload time (embedding chunks) and at chat time
(embedding the user's query) without touching the paid-Groq latency budget.

all-MiniLM-L6-v2: 384-dim vectors, ~90MB download (once, cached locally
after), good enough quality for document Q&A retrieval on a free-tier CPU.
If retrieval quality ever becomes the bottleneck, swapping the model name
is the only change needed here - EMBEDDING_DIM must then be updated to
match, and the Atlas Vector Search index's numDimensions along with it.
"""

import asyncio
from sentence_transformers import SentenceTransformer

MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384  # must match numDimensions in the Atlas Vector Search index

_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        # Downloads once on first use (needs internet that one time), then
        # loads from local cache on every process start after that.
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def _encode_sync(texts: list[str]) -> list[list[float]]:
    model = _get_model()
    vectors = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
    return vectors.tolist()


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Batched embedding, off the event loop - model.encode() (and the
    one-time model load behind it) is blocking CPU/disk work, same
    reasoning as the asyncio.to_thread fix already applied to the
    blocking DNS check in dynamic_tools.py."""
    if not texts:
        return []
    return await asyncio.to_thread(_encode_sync, texts)


async def embed_text(text: str) -> list[float]:
    """Single-text convenience wrapper - used for embedding one user
    query at chat time."""
    result = await embed_texts([text])
    return result[0]