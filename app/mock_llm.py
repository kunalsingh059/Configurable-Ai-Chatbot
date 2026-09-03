"""
MOCK MODE - lets you test the entire pipeline (DB, tool executor, widget,
session handling) with ZERO API calls and ZERO cost. It fakes what Claude
would do using dumb keyword matching against each tool's params_schema.

This is NOT a replacement for real testing - it can't actually "understand"
ambiguous requests the way Claude does. But it proves your plumbing works
(DB -> tool schema -> HTTP call -> response -> reply) without spending a
single credit. Flip USE_MOCK_LLM=false in .env once you have API credits
and want to see the real reasoning.
"""

import re
from app.dynamic_tools import get_tenant_tools, execute_tool


async def run_mock_chat_turn(tenant_id: str, conversation: list[dict]) -> tuple[str, list[dict]]:
    last_user_msg = ""
    for msg in reversed(conversation):
        if msg["role"] == "user" and isinstance(msg["content"], str):
            last_user_msg = msg["content"].lower()
            break

    tenant_tools = await get_tenant_tools(tenant_id)

    # Naive matching: does the tool's name (underscores as spaces) or any
    # word from its description appear in the user's message?
    matched_tool = None
    for tool in tenant_tools:
        name_words = tool["name"].replace("_", " ").split()
        if any(word in last_user_msg for word in name_words if len(word) > 3):
            matched_tool = tool
            break

    if matched_tool is None:
        reply = (
            f"[MOCK MODE] I couldn't confidently match a tool to that message. "
            f"Available tools: {', '.join(t['name'] for t in tenant_tools) or 'none configured'}. "
            f"Try mentioning a tool-related word, e.g. 'product' or 'category'."
        )
        conversation.append({"role": "assistant", "content": reply})
        return reply, conversation

    # Extract a number from the message to use as a plausible param value
    # (real Claude would ask the user properly if it's missing - this is just
    # a stand-in so we can prove the HTTP call fires and returns real data)
    numbers = re.findall(r"\d+", last_user_msg)
    words = re.findall(r"[a-zA-Z']+", last_user_msg)

    fake_params = {}
    schema_props = (matched_tool.get("params_schema") or {}).get("properties", {})
    for param_name, param_def in schema_props.items():
        if param_def.get("type") == "integer" and numbers:
            fake_params[param_name] = int(numbers[0])
        elif param_def.get("type") == "string":
            # crude guess: use "electronics" as a safe default test category
            fake_params[param_name] = "electronics"

    result = await execute_tool(matched_tool, fake_params)

    reply = (
        f"[MOCK MODE] Matched tool '{matched_tool['name']}' with params {fake_params}.\n"
        f"Real API response: {result}"
    )
    conversation.append({"role": "assistant", "content": reply})
    return reply, conversation