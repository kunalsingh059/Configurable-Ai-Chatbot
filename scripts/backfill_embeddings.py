"""
One-off migration: chunks + embeds every document that was uploaded BEFORE
the RAG feature existed (they're sitting in documents_collection with no
matching rows in document_chunks_collection yet, so they'd otherwise never
show up in retrieval again).

Idempotent - skips any document that already has at least one chunk, so
it's safe to re-run (e.g. after adding a new document type) without
duplicating existing chunks.

Run once, from the project root, after setting up REDIS_URL/MONGO_URI in
.env and creating the Atlas Vector Search index (see docs/rag-setup.md):

    python -m scripts.backfill_embeddings
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()  # must run before app.db reads MONGO_URI - this script doesn't
                # go through main.py, so nothing else loads .env for us

from app.db import documents_collection, document_chunks_collection
from app.documents import ingest_document_chunks


async def main():
    total_docs = 0
    total_chunks = 0
    skipped = 0

    async for doc in documents_collection.find({}):
        existing = await document_chunks_collection.count_documents({"doc_id": doc["_id"]})
        if existing > 0:
            skipped += 1
            continue

        count = await ingest_document_chunks(
            tenant_id=doc["tenant_id"],
            doc_id=doc["_id"],
            doc_name=doc["name"],
            text=doc.get("content") or "",
        )
        total_docs += 1
        total_chunks += count
        print(f"  {doc['tenant_id']}/{doc['name']}: {count} chunks")

    print(f"\nDone. {total_docs} documents backfilled ({total_chunks} chunks total), "
          f"{skipped} already had chunks and were skipped.")


if __name__ == "__main__":
    asyncio.run(main())