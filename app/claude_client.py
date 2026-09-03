"""
THE CORE LOOP - this is the entire product's brain.

Flow:
1. Load this tenant's configured tools from the DB, convert to Claude's
   tool-use format.
2. Send conversation history + tools to Claude.
3. Claude replies with either:
   a) plain text -> we're done, return it to the user
   b) a `tool_use` block -> Claude wants to call one of the tenant's tools
4. If (b): we run the generic HTTP executor for that tool, get the result,
   send it BACK to Claude as a `tool_result`, and ask again.
5. Repeat until Claude responds with plain text (no more tools needed).
"""

import os
from anthropic import AsyncAnthropic
from app.dynamic_tools import get_tenant_tools, build_claude_schema, execute_tool
from app.documents import build_documents_context

# Lazy client - only created the first time it's actually needed, so the app
# doesn't crash on startup/import if no API key is set yet (e.g. while
# running in mock mode). See app/mock_llm.py for the zero-cost test path.
_client: AsyncAnthropic | None = None


def get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Add it to your .env file, or "
                "set USE_MOCK_LLM=true in .env to test without a real API key."
            )
        _client = AsyncAnthropic(api_key=api_key)
    return _client


SYSTEM_PROMPT = (
    "You are a helpful customer support assistant embedded on a business's "
    "website. Use the available tools to look up real information whenever "
    "the user's question needs it. If a tool requires information you don't "
    "have yet (like an order ID), ask the user for it in a short, clear "
    "message before calling the tool. Keep answers concise and friendly.\n\n"
    "Format replies in markdown - the widget renders it. Use short "
    "paragraphs, **bold** for key terms (prices, statuses, names), and "
    "bullet or numbered lists whenever you're presenting more than one item "
    "(products, steps, options). Don't use raw asterisks or dashes outside "
    "proper markdown syntax, and don't use headings (#) - they're too "
    "heavy for a chat bubble."
)


async def run_chat_turn(tenant_id: str, conversation: list[dict]) -> tuple[str, list[dict]]:
    """
    conversation: list of {"role": "user"|"assistant", "content": ...} messages
                  (full history so far, including the latest user message)

    Returns: (final_text_reply, updated_conversation)
    """
    tenant_tools = await get_tenant_tools(tenant_id)
    tool_schemas = [build_claude_schema(t) for t in tenant_tools]
    tools_by_name = {t["name"]: t for t in tenant_tools}

    messages = conversation.copy()

    client = get_client()

    system_prompt = SYSTEM_PROMPT + await build_documents_context(tenant_id)

    for _ in range(5):  # safety limit on tool-call hops
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=system_prompt,
            tools=tool_schemas,
            messages=messages,
        )

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            final_text = "".join(
                block.text for block in response.content if block.type == "text"
            )
            return final_text, messages

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            tool = tools_by_name.get(block.name)
            if tool is None:
                result = {"error": f"Unknown tool {block.name}"}
            else:
                result = await execute_tool(tool, block.input)

            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": str(result),
                }
            )

        messages.append({"role": "user", "content": tool_results})

    return "Sorry, I'm having trouble completing that request right now.", messages