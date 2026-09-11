"""
GROQ PROVIDER - same loop as app/claude_client.py, but Groq uses OpenAI-style
tool calling, which differs from Anthropic's format in a few ways:

  Anthropic                          Groq (OpenAI-style)
  ----------------------------------  ----------------------------------
  tools=[{name, description,          tools=[{"type":"function","function":
          input_schema}]                {name, description, parameters}}]
  response.content = [text/tool_use   response.choices[0].message.tool_calls
    blocks]                            = [{id, function:{name, arguments}}]
                                        (arguments is a JSON STRING, not dict)
  tool_result sent as a "user"        tool_result sent as its own message:
    message with tool_use_id           {"role":"tool","tool_call_id":id,
                                         "content": "..."}

Everything else (load tenant tools from DB, execute HTTP call, loop until
no more tool calls) stays conceptually identical.
"""

import os
import json
from groq import AsyncGroq
from app.dynamic_tools import get_tenant_tools_for_execution, execute_tool, format_tool_result_for_llm
from app.documents import build_documents_context

# Fast + good tool-calling quality on Groq's free tier.
GROQ_MODEL = "openai/gpt-oss-120b"

_client: AsyncGroq | None = None


def get_client() -> AsyncGroq:
    global _client
    if _client is None:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not set. Add it to your .env file "
                "(get one free at console.groq.com)."
            )
        _client = AsyncGroq(api_key=api_key)
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


def build_capabilities_note(tenant_tools: list[dict], documents_context: str) -> str:
    """Grounds the model in what THIS business actually has configured, so
    it can't fall back on generic training-data knowledge of "what customer
    support chatbots usually do" (order tracking, returns, account
    management, etc.) when asked something like "how can you help me" and
    nothing real is set up yet. Without this, an empty tool list and empty
    document context give the model nothing to anchor on except its own
    priors - and it will confidently invent capabilities that don't exist
    for this tenant, which is indistinguishable from a real feature to the
    end user until they actually try it and it fails."""
    if tenant_tools:
        tool_names = ", ".join(t["name"].replace("_", " ") for t in tenant_tools)
        note = f"\n\nYou have these live lookup tools available: {tool_names}."
    else:
        note = "\n\nNo live lookup tools are configured for this business yet."

    if not documents_context:
        note += " No reference documents (FAQs, policies, menus, etc.) have been uploaded either."

    note += (
        " When asked what you can help with, ONLY describe capabilities backed by "
        "the tools and documents actually available to you, listed above/below. "
        "Never invent or imply generic abilities - like order tracking, returns, "
        "account management, or a general FAQ - unless they are truly configured "
        "here. If nothing is configured yet, say so plainly (e.g. \"I don't have "
        "any specific information set up yet\") and ask what the person is "
        "looking for, instead of guessing or listing typical support-bot features."
    )
    return note


def _to_openai_tool_schema(tool: dict) -> dict:
    """DB tool doc -> OpenAI/Groq function-calling format."""
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool["description"],
            "parameters": tool["params_schema"],
        },
    }


async def run_groq_chat_turn(tenant_id: str, conversation: list[dict]) -> tuple[str, list[dict]]:
    """
    conversation is stored in Anthropic-ish shape ({"role","content"} with
    content sometimes being a list of tool_result dicts). We convert to
    OpenAI/Groq's flatter message shape internally, but keep returning/
    accepting the same shape as claude_client.run_chat_turn so main.py
    doesn't need to know which provider is active.
    """
    tenant_tools = await get_tenant_tools_for_execution(tenant_id)
    tool_schemas = [_to_openai_tool_schema(t) for t in tenant_tools]
    tools_by_name = {t["name"]: t for t in tenant_tools}

    client = get_client()

    # Append this tenant's uploaded documents (menu, FAQ, policy, etc) to the
    # system prompt, if any exist. Tenants with none configured see this add
    # an empty string, so behavior is unchanged for them.
    documents_context = await build_documents_context(tenant_id)
    system_prompt = SYSTEM_PROMPT + build_capabilities_note(tenant_tools, documents_context) + documents_context

    # Build a plain OpenAI-style message list from our stored conversation.
    # Our conversation so far only contains plain user text turns (see
    # main.py) plus whatever we append below, so this is a straightforward
    # pass-through on the first call.
    messages = [{"role": "system", "content": system_prompt}]
    for msg in conversation:
        if isinstance(msg["content"], str):
            messages.append({"role": msg["role"], "content": msg["content"]})
        else:
            # Already-converted tool messages from a previous hop in this loop
            messages.extend(msg["content"])

    for _ in range(5):  # safety limit on tool-call hops
        response = await client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            tools=tool_schemas,
            max_tokens=1024,
        )
        choice = response.choices[0]
        msg = choice.message

        if not msg.tool_calls:
            final_text = msg.content or ""
            conversation.append({"role": "assistant", "content": final_text})
            return final_text, conversation

        # Record the assistant's tool-call request in OpenAI shape
        assistant_msg = {
            "role": "assistant",
            "content": msg.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in msg.tool_calls
            ],
        }
        messages.append(assistant_msg)

        tool_result_messages = []
        for tc in msg.tool_calls:
            tool = tools_by_name.get(tc.function.name)
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}

            if tool is None:
                result = {"error": f"Unknown tool {tc.function.name}"}
            else:
                result = await execute_tool(tool, args)

            tool_msg = {"role": "tool", "tool_call_id": tc.id, "content": format_tool_result_for_llm(result)}
            messages.append(tool_msg)
            tool_result_messages.append(tool_msg)

        # Also store this hop in our conversation log (as raw dicts, flagged
        # by not being a plain string) so it round-trips through main.py's
        # SESSIONS store correctly for the next user turn.
        conversation.append({"role": "assistant", "content": [assistant_msg] + tool_result_messages})

    fallback = "Sorry, I'm having trouble completing that request right now."
    conversation.append({"role": "assistant", "content": fallback})
    return fallback, conversation