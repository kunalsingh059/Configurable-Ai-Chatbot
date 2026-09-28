"""
Local, free embedding model for RAG - fastembed running the SAME model as
before (all-MiniLM-L6-v2, 384-dim) through ONNX Runtime instead of PyTorch.

WHY THIS REPLACED sentence-transformers: sentence-transformers pulls in
torch (plus transformers, scipy, scikit-learn, sympy...), which meant a
~1GB install, a ~100 second cold start on Render just to import it all, and
enough resident memory to push a 512MB instance over its limit. fastembed
runs the identical model with only onnxruntime + tokenizers: roughly 90MB
of model, a small fraction of the RAM, and imports in about a second. No
API key, no per-call cost, no network round-trip once the model is cached.

SAME VECTORS, SAME INDEX: model and dimensions are unchanged (384), so the
Atlas Vector Search index and every embedding already stored stay valid.
Vectors from ONNX vs PyTorch can differ in the far decimal places - run
scripts/verify_embeddings.py once to confirm before relying on that. Our
chunks are ~700 chars (~175 tokens), well under the model's 256-token
window, so truncation differences between the two libraries never trigger.

If retrieval quality ever becomes the bottleneck, swapping the model is the
only change needed here - EMBEDDING_DIM must then be updated to match, the
Atlas Vector Search index's numDimensions along with it, and every stored
chunk re-embedded (scripts/backfill_embeddings.py).
"""

import asyncio
import logging
import os
import threading

import numpy as np
from fastembed import TextEmbedding

logger = logging.getLogger("chatbot_platform")

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384  # must match numDimensions in the Atlas Vector Search index

# onnxruntime defaults to "all cores it can see". In a container with a
# fractional CPU quota (Render), that oversubscribes threads and makes
# everything slower, not faster. 2 is a safe default; raise it locally if
# you have cores to spare and want faster document uploads.
_THREADS = int(os.environ.get("EMBEDDING_THREADS", "2"))
# Small batches keep peak memory flat when a big document is chunked.
_BATCH_SIZE = 32
# fastembed defaults to the OS temp dir. Set EMBEDDING_CACHE_DIR to pin the
# ~90MB model download somewhere that survives restarts, if you need to.
_CACHE_DIR = os.environ.get("EMBEDDING_CACHE_DIR") or None

_model: TextEmbedding | None = None
# The model is loaded lazily on first use, from worker threads
# (asyncio.to_thread). Without a lock, two requests arriving together on a
# cold instance would BOTH load the model - doubling the memory spike at
# exactly the worst moment. Double-checked so the common (already loaded)
# path never touches the lock.
_model_lock = threading.Lock()


def _get_model() -> TextEmbedding:
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                # Downloads once on first use (needs internet that one time),
                # then loads from the local cache on every start after that.
                _model = TextEmbedding(
                    model_name=MODEL_NAME,
                    threads=_THREADS,
                    cache_dir=_CACHE_DIR,
                )
    return _model


def _encode_sync(texts: list[str]) -> list[list[float]]:
    model = _get_model()
    # model.embed() returns a lazy generator - it must be consumed here,
    # inside the worker thread, not handed back to the event loop.
    vectors = np.asarray(list(model.embed(texts, batch_size=_BATCH_SIZE)), dtype=np.float32)
    # Re-normalize explicitly so stored/query vectors are unit length no
    # matter how a library version post-processes them (the old code used
    # normalize_embeddings=True). Idempotent if already normalized.
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (vectors / norms).tolist()


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Batched embedding, off the event loop - embedding (and the one-time
    model load behind it) is blocking CPU/disk work, same reasoning as the
    asyncio.to_thread fix already applied to the blocking DNS check in
    dynamic_tools.py."""
    if not texts:
        return []
    return await asyncio.to_thread(_encode_sync, texts)


async def embed_text(text: str) -> list[float]:
    """Single-text convenience wrapper - used for embedding one user
    query at chat time."""
    result = await embed_texts([text])
    return result[0]


async def warm_up() -> None:
    """Loads the model in the background at startup so the first real chat
    or upload after a restart doesn't pay the load cost. Never raises - a
    failed warm-up (e.g. the one-time download can't reach the internet)
    just means the model loads lazily on first use instead, same as
    before, and the error is logged."""
    try:
        await asyncio.to_thread(_get_model)
        logger.info(f"Embedding model '{MODEL_NAME}' loaded and ready.")
    except Exception as e:
        logger.error(f"Embedding model warm-up failed (will retry lazily on first use): {e}")