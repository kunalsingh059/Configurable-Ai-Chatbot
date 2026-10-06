"""
MongoDB connection setup using Motor (the async MongoDB driver — matches
FastAPI's async style, same reason we used async SQLAlchemy patterns before).

For local dev, run MongoDB locally or use a free MongoDB Atlas cluster and
paste its connection string into .env as MONGO_URI.
"""

import os
from dotenv import load_dotenv
load_dotenv()

# Ensure robust DNS SRV resolution across local Windows dev networks / routers
try:
    import dns.resolver
    _default_resolver = dns.resolver.get_default_resolver()
    if _default_resolver and "8.8.8.8" not in _default_resolver.nameservers:
        _default_resolver.nameservers.extend(["8.8.8.8", "1.1.1.1"])
except Exception:
    pass

from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.environ.get("MONGO_DB_NAME", "chatbot_platform")

# Explicit timeouts - without these, a network/cluster problem makes every
# request wait on Motor's own (much longer) internal defaults instead of
# failing fast. serverSelectionTimeoutMS bounds "can I even reach the
# cluster"; connectTimeoutMS bounds establishing a new connection;
# socketTimeoutMS bounds how long an individual operation can hang once
# connected.
client = AsyncIOMotorClient(
    MONGO_URI,
    serverSelectionTimeoutMS=5000,
    connectTimeoutMS=5000,
    socketTimeoutMS=10000,
)
db = client[DB_NAME]

tools_collection = db["tools"]
documents_collection = db["documents"]
admin_users_collection = db["admin_users"]

# One doc per CHUNK (not per uploaded file) - each has tenant_id, the
# parent document's id/name, the chunk's text, and its embedding vector.
# documents_collection stays the source of truth for the admin UI
# (list/delete a whole uploaded file); this collection is the retrieval
# index Atlas Vector Search actually queries against. See app/documents.py.
document_chunks_collection = db["document_chunks"]

# T1: Feedback collection - thumbs up/down ratings per message
feedback_collection = db["feedback"]

# T2: Unanswered questions collection - tracks queries the bot could not answer
unanswered_collection = db["unanswered_questions"]

# T7: Usage daily tracking - records daily messages, tokens, and tool calls per tenant
usage_daily_collection = db["usage_daily"]

# T9: Leads collection - captures visitor contact details / handoffs
leads_collection = db["leads"]