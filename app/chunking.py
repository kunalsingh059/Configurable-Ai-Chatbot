"""
Plain character-based chunking for RAG - deliberately no extra NLP
dependency (spaCy/nltk) for something this simple. Splits on paragraph or
sentence boundaries where possible so a chunk doesn't cut off mid-sentence,
falling back to a hard character split for a wall of text with no natural
break.
"""

CHUNK_SIZE = 700     # chars per chunk - small enough for precise retrieval,
                      # large enough to carry real context (a paragraph or two)
CHUNK_OVERLAP = 100   # chars repeated between consecutive chunks, so an answer
                      # that straddles a chunk boundary doesn't get cut in half


def chunk_text(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= CHUNK_SIZE:
        return [text]

    chunks = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + CHUNK_SIZE, n)
        if end < n:
            # Prefer breaking on a paragraph/sentence boundary within the
            # last ~20% of the window, so chunks read naturally instead of
            # stopping mid-word.
            window_start = start + int(CHUNK_SIZE * 0.8)
            break_point = -1
            for sep in ("\n\n", ". ", "\n"):
                idx = text.rfind(sep, window_start, end)
                if idx != -1:
                    break_point = idx + len(sep)
                    break
            if break_point != -1:
                end = break_point
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= n:
            break
        start = max(end - CHUNK_OVERLAP, start + 1)  # guarantee forward progress
    return chunks