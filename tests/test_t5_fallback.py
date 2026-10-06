import os
import unittest
import asyncio
from unittest.mock import patch, MagicMock
import groq
import httpx

from app.llm_orchestrator import (
    run_orchestrated_chat_turn_stream,
    is_failover_exception,
    get_primary_provider,
    get_fallback_provider,
)
from app.anthropic_client import _prepare_anthropic_messages, _to_anthropic_tool_schema


class TestLLMOrchestrator(unittest.TestCase):
    def test_anthropic_helpers(self):
        # 1. Message preparation
        raw_convo = [
            {"role": "user", "content": "Hello"},
            {"role": "user", "content": "How are you?"},
            {"role": "system", "content": "Ignore me"},
            {"role": "assistant", "content": "I am doing well!"},
        ]
        cleaned = _prepare_anthropic_messages(raw_convo)
        self.assertEqual(len(cleaned), 2)
        self.assertEqual(cleaned[0]["role"], "user")
        self.assertIn("Hello\n\nHow are you?", cleaned[0]["content"])
        self.assertEqual(cleaned[1]["role"], "assistant")

        # 2. Tool schema conversion
        tool_doc = {
            "name": "lookup_rate",
            "description": "Look up service rate",
            "params_schema": {
                "type": "object",
                "properties": {"service": {"type": "string"}},
                "required": ["service"],
            },
        }
        anthropic_schema = _to_anthropic_tool_schema(tool_doc)
        self.assertEqual(anthropic_schema["name"], "lookup_rate")
        self.assertEqual(anthropic_schema["input_schema"], tool_doc["params_schema"])

    def test_failover_exception_detection(self):
        # Check Groq RateLimitError detection
        fake_response = MagicMock(status_code=429, headers={})
        rate_err = groq.RateLimitError("Rate limit exceeded", response=fake_response, body=None)
        self.assertTrue(is_failover_exception(rate_err))

        # Check Groq APIStatusError with 500
        fake_500 = MagicMock(status_code=500, headers={})
        status_500 = groq.APIStatusError("Internal Server Error", response=fake_500, body=None)
        self.assertTrue(is_failover_exception(status_500))

        # Check Groq APIStatusError with 400 (not failover eligible - client error)
        fake_400 = MagicMock(status_code=400, headers={})
        status_400 = groq.APIStatusError("Bad Request", response=fake_400, body=None)
        self.assertFalse(is_failover_exception(status_400))

        # Check timeout errors
        self.assertTrue(is_failover_exception(asyncio.TimeoutError()))
        self.assertTrue(is_failover_exception(httpx.ConnectTimeout("Connect timeout")))

    def test_orchestrator_failover_to_fallback(self):
        async def run():
            # Simulate Groq 429 error on primary, with fallback set to "mock"
            async def failing_primary_stream(tenant_id, conversation, bot_config=None):
                fake_response = MagicMock(status_code=429, headers={})
                raise groq.RateLimitError("Rate limit hit", response=fake_response, body=None)
                yield  # make it an async generator

            with patch.dict(os.environ, {"LLM_PRIMARY": "groq", "LLM_FALLBACK": "mock"}):
                with patch("app.llm_orchestrator._get_provider_stream") as mock_stream_factory:
                    from app.mock_llm import run_mock_chat_turn_stream

                    def side_effect(provider, tenant_id, conversation, bot_config):
                        if provider == "groq":
                            return failing_primary_stream(tenant_id, conversation, bot_config)
                        return run_mock_chat_turn_stream(tenant_id, conversation, bot_config)

                    mock_stream_factory.side_effect = side_effect

                    convo = [{"role": "user", "content": "Help me with tests"}]
                    events = []
                    async for ev in run_orchestrated_chat_turn_stream("t_test", convo):
                        events.append(ev)

                    # Fallback should have yielded tokens and a done event
                    self.assertTrue(any(ev["type"] == "token" for ev in events))
                    done_events = [ev for ev in events if ev["type"] == "done"]
                    self.assertEqual(len(done_events), 1)
                    self.assertEqual(done_events[0].get("fallback_provider_used"), "mock")

        asyncio.run(run())

    def test_orchestrator_no_fallback_raises(self):
        async def run():
            async def failing_primary_stream(tenant_id, conversation, bot_config=None):
                fake_response = MagicMock(status_code=429, headers={})
                raise groq.RateLimitError("Rate limit hit", response=fake_response, body=None)
                yield

            # No fallback set
            with patch.dict(os.environ, {"LLM_PRIMARY": "groq", "LLM_FALLBACK": ""}, clear=False):
                with patch("app.llm_orchestrator._get_provider_stream", return_value=failing_primary_stream("t_test", [])):
                    convo = [{"role": "user", "content": "Help me with tests"}]
                    with self.assertRaises(groq.RateLimitError):
                        async for _ in run_orchestrated_chat_turn_stream("t_test", convo):
                            pass

        asyncio.run(run())

    def test_orchestrator_no_failover_if_tokens_already_yielded(self):
        async def run():
            # If tokens were already streamed to user, failover mid-sentence must NOT occur
            async def partial_fail_stream(tenant_id, conversation, bot_config=None):
                yield {"type": "token", "text": "Partially generated message"}
                fake_response = MagicMock(status_code=500, headers={})
                raise groq.APIStatusError("Server crash mid-stream", response=fake_response, body=None)

            with patch.dict(os.environ, {"LLM_PRIMARY": "groq", "LLM_FALLBACK": "mock"}):
                with patch("app.llm_orchestrator._get_provider_stream", return_value=partial_fail_stream("t_test", [])):
                    convo = [{"role": "user", "content": "Help me with tests"}]
                    with self.assertRaises(groq.APIStatusError):
                        async for _ in run_orchestrated_chat_turn_stream("t_test", convo):
                            pass

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
