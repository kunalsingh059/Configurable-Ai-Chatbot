"""
LLM ORCHESTRATOR - Manages primary LLM execution and seamless failover to secondary/fallback provider.

When the primary provider encounters a rate limit (429), server error (5xx),
connection drop, or timeout BEFORE any tokens are yielded to the client, the
orchestrator immediately fails over to the configured secondary provider
without disrupting the user's chat session.
"""

import os
import logging
import asyncio
import copy
import groq
import httpx

from app.groq_client import run_groq_chat_turn_stream
from app.mock_llm import run_mock_chat_turn_stream
from app.anthropic_client import run_anthropic_chat_turn_stream

logger = logging.getLogger("llm_orchestrator")


def get_primary_provider() -> str:
    """Returns the primary LLM provider ('groq', 'anthropic', 'mock')."""
    return (os.environ.get("LLM_PRIMARY") or os.environ.get("LLM_PROVIDER") or "groq").lower().strip()


def get_fallback_provider() -> str | None:
    """Returns the fallback LLM provider, or None if none configured."""
    fb = os.environ.get("LLM_FALLBACK")
    if fb:
        fb = fb.lower().strip()
        return fb if fb in ("groq", "anthropic", "mock") else None
    return None


def is_failover_exception(exc: Exception) -> bool:
    """Determines if an exception is a transient or capacity error eligible for failover."""
    if isinstance(exc, (groq.RateLimitError, groq.APITimeoutError, groq.APIConnectionError)):
        return True
    if isinstance(exc, groq.APIStatusError) and exc.status_code >= 500:
        return True
    if isinstance(exc, (asyncio.TimeoutError, httpx.TimeoutException, httpx.NetworkError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError) and (exc.response.status_code in (429, 500, 502, 503, 504)):
        return True
    return False


def _get_provider_stream(provider: str, tenant_id: str, conversation: list[dict], bot_config: dict | None):
    if provider == "groq":
        return run_groq_chat_turn_stream(tenant_id, conversation, bot_config=bot_config)
    elif provider == "anthropic":
        return run_anthropic_chat_turn_stream(tenant_id, conversation, bot_config=bot_config)
    elif provider == "mock":
        return run_mock_chat_turn_stream(tenant_id, conversation, bot_config=bot_config)
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")


async def run_orchestrated_chat_turn_stream(
    tenant_id: str,
    conversation: list[dict],
    bot_config: dict | None = None,
):
    """
    Executes the chat turn against the primary provider with automatic failover
    to the secondary provider on 429, 5xx, or timeouts if no tokens have been streamed yet.
    """
    primary = get_primary_provider()
    fallback = get_fallback_provider()

    # Deep copy conversation for fallback in case primary mutates it before failing
    conversation_backup = copy.deepcopy(conversation)

    tokens_yielded = 0
    stream = _get_provider_stream(primary, tenant_id, conversation, bot_config)

    try:
        async for event in stream:
            if event.get("type") == "token":
                tokens_yielded += 1
            yield event
        return

    except Exception as exc:
        can_failover = (
            fallback
            and fallback != primary
            and tokens_yielded == 0
            and is_failover_exception(exc)
        )

        if not can_failover:
            # Re-raise so main.py's specific exception handlers take over
            raise exc

        logger.warning(
            f"Primary LLM '{primary}' encountered {type(exc).__name__}: {exc}. "
            f"Failing over cleanly to '{fallback}' for tenant {tenant_id}..."
        )

        # Restore conversation to pre-turn state
        conversation.clear()
        conversation.extend(conversation_backup)

        # Stream from fallback provider
        fallback_stream = _get_provider_stream(fallback, tenant_id, conversation, bot_config)
        async for event in fallback_stream:
            if event.get("type") == "done":
                event["fallback_provider_used"] = fallback
            yield event
