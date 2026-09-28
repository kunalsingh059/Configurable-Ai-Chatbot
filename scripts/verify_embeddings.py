"""
One-off check for the sentence-transformers -> fastembed swap: confirms the
new ONNX embeddings match what the OLD library produced, so the vectors
already stored in Atlas (and the existing vector index) stay valid and no
re-embedding is needed.

Needs BOTH libraries installed at the same time, so run it BEFORE you
recreate your venv from the new requirements.txt:

    pip install fastembed==0.8.1
    python -m scripts.verify_embeddings

(First run downloads the ~90MB model once for each library.) Once it says
PASS you can delete this file, and rebuild the venv without torch.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

SAMPLES = [
    "What are your opening hours on weekends?",
    "How do I reset my password?",
    "Refunds are processed within 5-7 business days after we receive the returned item.",
    "Do you ship internationally, and how long does delivery take?",
    # Roughly the size of a real stored chunk (~700 chars), since that's
    # what actually gets embedded at upload time.
    (
        "Our robotics starter kit includes a microcontroller board, four servo motors, "
        "an ultrasonic distance sensor, a breadboard, jumper wires and a rechargeable "
        "battery pack. It is designed for students aged 10 and above and comes with a "
        "printed step-by-step guide covering eight beginner projects, from a blinking "
        "LED to an obstacle-avoiding car. Replacement parts are sold separately in our "
        "accessories section, and every kit carries a six month warranty against "
        "manufacturing defects. For classroom bulk orders of ten kits or more, contact "
        "our sales team for a discount and free delivery to your school or institution."
    ),
]


def main() -> int:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print(
            "sentence-transformers is not installed, so there is nothing to compare "
            "against. This check needs the OLD library - run it in your existing venv "
            "(before rebuilding it) after `pip install fastembed==0.8.1`."
        )
        return 2

    from app.embeddings import _encode_sync  # the real code path the app will use

    old = SentenceTransformer("all-MiniLM-L6-v2").encode(
        SAMPLES, convert_to_numpy=True, normalize_embeddings=True
    )
    new = np.asarray(_encode_sync(SAMPLES), dtype=np.float32)

    if old.shape != new.shape:
        print(f"FAIL: shape mismatch, old {old.shape} vs new {new.shape}")
        return 1

    sims = (old * new).sum(axis=1)  # both unit length, so dot product == cosine similarity
    for text, s in zip(SAMPLES, sims):
        print(f"  cosine {s:.6f}   {text[:60]!r}")
    worst = float(sims.min())
    print(f"\nWorst-case cosine similarity: {worst:.6f}")

    if worst >= 0.99:
        print("PASS - vectors match. Existing stored embeddings and the Atlas index stay valid.")
        return 0
    if worst >= 0.95:
        print(
            "WARN - close but not identical. Retrieval will probably still work, but for "
            "consistency consider re-embedding: delete the rows in the document_chunks "
            "collection and run `python -m scripts.backfill_embeddings` (it only processes "
            "documents that have no chunks yet), or simply re-upload your documents."
        )
        return 0
    print(
        "FAIL - vectors differ materially. Do NOT deploy the swap without re-embedding "
        "everything (delete the document_chunks rows, then run the backfill script)."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())