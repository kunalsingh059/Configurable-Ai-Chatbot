"""
MongoDB connection setup using Motor (the async MongoDB driver — matches
FastAPI's async style, same reason we used async SQLAlchemy patterns before).

For local dev, run MongoDB locally or use a free MongoDB Atlas cluster and
paste its connection string into .env as MONGO_URI.
"""

import os
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