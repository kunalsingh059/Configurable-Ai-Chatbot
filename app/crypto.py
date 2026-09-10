"""
Symmetric encryption for tool header secrets at rest (API keys/Bearer
tokens a business owner configures for their own third-party integrations).
Uses Fernet (AES-128-CBC + HMAC-SHA256, authenticated encryption) from the
`cryptography` library - deliberately not rolling custom crypto.

TOOL_HEADERS_ENCRYPTION_KEY must be set in .env to a Fernet key. Generate
one with:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

IMPORTANT: unlike JWT_SECRET, this key must stay IDENTICAL across every
restart and every process - losing or rotating it makes every already-
stored tool header unrecoverable (decrypt_headers() fails safe to {}
rather than crashing, but the business owner's stored API keys/tokens
would need to be re-entered).
"""

import os
import json
from cryptography.fernet import Fernet, InvalidToken

_key = os.environ.get("TOOL_HEADERS_ENCRYPTION_KEY")
if not _key:
    raise RuntimeError(
        "TOOL_HEADERS_ENCRYPTION_KEY is not set in .env - required to "
        "encrypt tool header secrets (API keys/Bearer tokens) at rest. "
        'Generate one with: python -c "from cryptography.fernet import '
        'Fernet; print(Fernet.generate_key().decode())" and add it to .env.'
    )

_fernet = Fernet(_key.encode())


def encrypt_headers(headers: dict) -> str:
    """Serializes a headers dict to JSON and encrypts it for storage."""
    plaintext = json.dumps(headers or {})
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt_headers(ciphertext: str | None) -> dict:
    """Reverses encrypt_headers(). Returns {} for empty/missing ciphertext
    (tools that have no headers, or predate this field existing) and also
    fails safe to {} on a corrupted/wrong-key value rather than raising -
    one bad tool shouldn't be able to crash a chat turn or the test endpoint."""
    if not ciphertext:
        return {}
    try:
        plaintext = _fernet.decrypt(ciphertext.encode())
        return json.loads(plaintext)
    except (InvalidToken, ValueError):
        return {}