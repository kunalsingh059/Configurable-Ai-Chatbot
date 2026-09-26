# RAG setup: Atlas Vector Search

One-time setup, done in the Atlas UI (no code, no separate vector DB - M0
free tier includes this).

## 1. Create the index

1. Atlas dashboard -> your cluster -> **Search** tab -> **Create Search Index**
2. Choose **JSON Editor** (not the visual builder - the visual builder doesn't
   expose the `filter` field type this app needs for tenant isolation)
3. Database: your DB (matches `MONGO_DB_NAME`, defaults to `chatbot_platform`)
4. Collection: `document_chunks`
5. Index name: `document_chunks_vector_index` (must match `VECTOR_INDEX_NAME`
   in `app/documents.py` exactly)
6. Paste this definition:

```json
{
  "fields": [
    { "type": "vector", "path": "embedding", "numDimensions": 384, "similarity": "cosine" },
    { "type": "filter", "path": "tenant_id" }
  ]
}
```

`numDimensions: 384` matches `all-MiniLM-L6-v2` (see `app/embeddings.py`) -
if you ever swap embedding models, update both places together or every
query will fail with a dimension-mismatch error.

7. Save. Index build takes a minute or two on M0 - status goes from
   "Building" to "Active" in the same Search tab.

## 2. Backfill documents uploaded before this feature existed

Anything already in `documents_collection` has no chunks yet. Run once:

    python -m scripts.backfill_embeddings

Safe to re-run - it skips documents that already have chunks.

## 3. Verify

Upload a fresh test document via the admin UI, then ask the widget a
question whose answer only exists in that document. The `/chat` request
should now retrieve just the relevant chunk(s) instead of the whole
document.