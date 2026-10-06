"""
ANTHROPIC PROVIDER - fallback or alternate LLM provider for the chatbot platform.
Streams responses via Anthropic Messages SSE API and executes tools concurrently.
"""

import os
import json
import logging
import asyncio
import httpx
from app.dynamic_tools import get_tenant_tools_for_execution, execute_tool, format_tool_result_for_llm
from app.documents import build_documents_context
from app.groq_client import build_system_prompt

logger = logging.getLogger("anthropic_client")

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-3-haiku-20240307")
MAX_TOOL_HOPS = int(os.environ.get("MAX_TOOL_HOPS", "5"))


def _to_anthropic_tool_schema(tool: dict) -> dict:
    """Converts internal tool representation to Anthropic tool schema format."""
    return {
        "name": tool["name"],
        "description": tool["description"],
        "input_schema": tool.get("params_schema") or {"type": "object", "properties": {}},
    }


def _prepare_anthropic_messages(conversation: list[dict]) -> list[dict]:
    """Ensures conversation messages conform to Anthropic message constraints:
    - Only 'user' and 'assistant' roles (no 'system' in messages list).
    - Merges consecutive messages of the same role if any.
    - Strips internal metadata.
    """
    cleaned: list[dict] = []
    for msg in conversation:
        role = msg.get("role")
        if role not in ("user", "assistant"):
            continue
        content = msg.get("content")
        if not content:
            continue

        if cleaned and cleaned[-1]["role"] == role:
            # Merge consecutive messages of the same role
            prev_content = cleaned[-1]["content"]
            if isinstance(prev_content, str) and isinstance(content, str):
                cleaned[-1]["content"] = f"{prev_content}\n\n{content}"
            elif isinstance(prev_content, list) and isinstance(content, list):
                cleaned[-1]["content"].extend(content)
            else:
                cleaned.append({"role": role, "content": content})
        else:
            cleaned.append({"role": role, "content": content})

    return cleaned


async def run_anthropic_chat_turn_stream(
    tenant_id: str,
    conversation: list[dict],
    bot_config: dict | None = None,
):
    """
    Async generator streaming replies from Anthropic Claude.
    Yields identical event shape as run_groq_chat_turn_stream:
      {"type": "token", "text": "..."}
      {"type": "tool_start", "name": "..."}
      {"type": "done", "text": "...", "conversation": [...], ...}
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Add it to your .env file to enable Anthropic."
        )

    tenant_tools = await get_tenant_tools_for_execution(tenant_id)
    tool_schemas = [_to_anthropic_tool_schema(t) for t in tenant_tools]
    tools_by_name = {t["name"]: t for t in tenant_tools}

    latest_user_message = ""
    if conversation and isinstance(conversation[-1].get("content"), str):
        latest_user_message = conversation[-1]["content"]
    documents_context = await build_documents_context(tenant_id, latest_user_message)
    system_prompt = build_system_prompt(tenant_tools, documents_context, bot_config)

    messages = _prepare_anthropic_messages(conversation)
    tools_executed_count = 0
    has_doc_context = bool(documents_context and documents_context.strip())

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=6, read=35, write=10, pool=5)) as client:
        for _ in range(MAX_TOOL_HOPS):
            payload = {
                "model": ANTHROPIC_MODEL,
                "max_tokens": 1024,
                "system": system_prompt,
                "messages": messages,
                "stream": True,
            }
            if tool_schemas:
                payload["tools"] = tool_schemas

            async with client.stream("POST", ANTHROPIC_API_URL, headers=headers, json=payload) as resp:
                if resp.status_code >= 400:
                    err_body = await resp.aread()
                    err_msg = err_body.decode(errors="replace")
                    logger.error(f"Anthropic API returned status {resp.status_code}: {err_msg}")
                    raise httpx.HTTPStatusError(
                        f"Anthropic API error: {resp.status_code}",
                        request=resp.request,
                        response=resp,
                    )

                text_parts: list[str] = []
                tool_calls: list[dict] = []
                current_tool: dict | None = None
                current_tool_json = ""

                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    try:
                        event = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    event_type = event.get("type")

                    if event_type == "content_block_start":
                        block = event.get("content_block", {})
                        if block.get("type") == "tool_use":
                            current_tool = {
                                "id": block.get("id"),
                                "name": block.get("name"),
                            }
                            current_tool_json = ""

                    elif event_type == "content_block_delta":
                        delta = event.get("delta", {})
                        delta_type = delta.get("type")
                        if delta_type == "text_delta":
                            piece = delta.get("text", "")
                            if piece:
                                text_parts.append(piece)
                                yield {"type": "token", "text": piece}
                        elif delta_type == "input_json_delta":
                            current_tool_json += delta.get("partial_json", "")

                    elif event_type == "content_block_stop":
                        if current_tool:
                            try:
                                args = json.loads(current_tool_json) if current_tool_json else {}
                            except json.JSONDecodeError:
                                args = {}
                            current_tool["input"] = args
                            tool_calls.append(current_tool)
                            current_tool = None
                            current_tool_json = ""

            if not tool_calls:
                final_text = "".join(text_parts)
                conversation.append({"role": "assistant", "content": final_text})
                yield {
                    "type": "done",
                    "text": final_text,
                    "conversation": conversation,
                    "tools_called_count": tools_executed_count,
                    "has_doc_context": has_doc_context,
                }
                return

            # Tool execution
            tools_executed_count += len(tool_calls)
            assistant_blocks = []
            if text_parts:
                assistant_blocks.append({"type": "text", "text": "".join(text_parts)})
            for tc in tool_calls:
                assistant_blocks.append({
                    "type": "tool_use",
                    "id": tc["id"],
                    "name": tc["name"],
                    "input": tc["input"],
                })
                yield {"type": "tool_start", "name": tc["name"]}

            messages.append({"role": "assistant", "content": assistant_blocks})

            async def _execute_anthropic_tool(tc: dict) -> dict:
                tool = tools_by_name.get(tc["name"])
                if tool is None:
                    result = {"error": f"Unknown tool {tc['name']}"}
                else:
                    result = await execute_tool(tool, tc["input"])
                return {
                    "type": "tool_result",
                    "tool_use_id": tc["id"],
                    "content": format_tool_result_for_llm(result),
                }

            tool_results = await asyncio.gather(*[_execute_anthropic_tool(tc) for tc in tool_calls])
            messages.append({"role": "user", "content": tool_results})
            conversation.append({"role": "assistant", "content": assistant_blocks + tool_results})

        fallback = "Sorry, I'm having trouble completing that request right now."
        conversation.append({"role": "assistant", "content": fallback})
        yield {
            "type": "done",
            "text": fallback,
            "conversation": conversation,
            "tools_called_count": tools_executed_count,
            "has_doc_context": has_doc_context,
            "is_fallback": True,
        }
