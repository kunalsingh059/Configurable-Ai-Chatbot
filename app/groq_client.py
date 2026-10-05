"""
GROQ PROVIDER - streams the model's response as it's generated instead of
waiting for the full completion, and runs any tool calls within a single
hop concurrently instead of one-at-a-time. Both changes are purely about
latency/perceived speed - the conversation shape, tool-calling contract,
and everything else stays the same as the non-streaming version.

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

STREAMING + TOOL CALLS: Groq's streaming API sends tool calls the same way
OpenAI's does - as incremental deltas. Text tokens arrive on
delta.content; a tool call arrives split across many chunks, each delta
carrying a fragment of the (index, id, function.name, function.arguments)
tuple, keyed by `index` so multiple simultaneous tool calls don't get their
fragments mixed together. We accumulate those fragments per-index and only
act once the stream signals no more tool calls are coming.
"""

import asyncio
import os
import json
from groq import AsyncGroq
from app.dynamic_tools import get_tenant_tools_for_execution, execute_tool, format_tool_result_for_llm
from app.documents import build_documents_context

MAX_TOOL_HOPS = int(os.environ.get("MAX_TOOL_HOPS", "5"))

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
        # max_retries=1 (SDK default is 2, each with its own backoff wait
        # honoring Groq's Retry-After header - we saw 10s, 25s, then 40s
        # waits stack up INSIDE a single request in testing). On the free
        # tier, hitting a 429 usually means you're already over the
        # minute's quota - waiting and retrying inside the same request
        # just makes the user stare at a spinner for up to a minute before
        # finding out either way. Failing fast after one retry lets us
        # surface a clear "please wait a moment" message quickly instead,
        # and the user's own next message is a perfectly good "retry".
        _client = AsyncGroq(api_key=api_key, max_retries=1)
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

# T3: Multi-language & Hinglish instruction
LANGUAGE_PROMPT_INSTRUCTION = (
    "\n\nLanguage and Script Style Guidelines:\n"
    "- Mirror the language and script style used in the user's latest message:\n"
    "  * If the user writes in English, reply in natural English.\n"
    "  * If the user writes in Hindi using Devanagari script (e.g. 'नमस्ते, क्या हाल है?'), reply in natural Hindi using Devanagari script.\n"
    "  * If the user writes in Hinglish (Hindi words written in Latin/English alphabet, e.g. 'ye test kitne ka hai?'), reply in natural conversational Hinglish using Latin alphabet.\n"
    "- Always preserve technical identifiers, product names, tool names, parameters, codes, and numerical/currency figures (e.g. ₹500, #1024, 10:00 AM) in their standard representation without translating them."
)

TONE_INSTRUCTIONS = {
    "friendly": "\nTone: Maintain a warm, friendly, encouraging, and helpful tone.",
    "professional": "\nTone: Maintain a polished, professional, concise, and courteous tone.",
    "casual": "\nTone: Maintain a relaxed, easygoing, conversational, and approachable tone.",
}


def build_system_prompt(
    tenant_tools: list[dict],
    documents_context: str,
    bot_config: dict | None = None,
) -> str:
    config = bot_config or {}
    prompt = SYSTEM_PROMPT

    tone = (config.get("tone") or "friendly").lower()
    if tone in TONE_INSTRUCTIONS:
        prompt += TONE_INSTRUCTIONS[tone]

    reply_in_user_lang = config.get("reply_in_user_language", True)
    if reply_in_user_lang:
        prompt += LANGUAGE_PROMPT_INSTRUCTION

    prompt += build_capabilities_note(tenant_tools, documents_context)
    if documents_context:
        prompt += documents_context

    return prompt


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


async def _run_one_tool_call(tc: dict, tools_by_name: dict) -> dict:
    """Executes a single accumulated tool call and returns the OpenAI-shape
    tool result message. Pulled out of the hop loop so multiple tool calls
    in the same hop can be run concurrently via asyncio.gather instead of
    one at a time - independent tool calls (e.g. "check order 123 and
    order 456") have no reason to wait on each other."""
    tool = tools_by_name.get(tc["name"])
    try:
        args = json.loads(tc["arguments"]) if tc["arguments"] else {}
    except json.JSONDecodeError:
        args = {}

    if tool is None:
        result = {"error": f"Unknown tool {tc['name']}"}
    else:
        result = await execute_tool(tool, args)

    return {"role": "tool", "tool_call_id": tc["id"], "content": format_tool_result_for_llm(result)}


async def run_groq_chat_turn_stream(
    tenant_id: str,
    conversation: list[dict],
    bot_config: dict | None = None,
):
    """
    Async generator version of the chat turn. Yields dicts describing what
    happened as it happens, instead of returning only once everything is
    done:

      {"type": "token", "text": "..."}       - a piece of the reply to show immediately
      {"type": "tool_start", "name": "..."}  - the model is calling a tool (for a "looking that up..." indicator)
      {"type": "done", "text": "...", "conversation": [...]}  - final full reply + updated history to persist

    main.py turns each yielded dict into one SSE `data: ...` line. This
    generator does not touch Redis/sessions itself - the caller decides
    when/how to persist `conversation`, same as the non-streaming version
    used to just return it.
    """
    tenant_tools = await get_tenant_tools_for_execution(tenant_id)
    tool_schemas = [_to_openai_tool_schema(t) for t in tenant_tools]
    tools_by_name = {t["name"]: t for t in tenant_tools}

    client = get_client()

    # Real RAG: retrieve only chunks relevant to the CURRENT message,
    # not a flat dump of every document. conversation[-1] is the user
    # message just appended in main.py's /chat handler before this
    # generator is created.
    latest_user_message = ""
    if conversation and isinstance(conversation[-1].get("content"), str):
        latest_user_message = conversation[-1]["content"]
    documents_context = await build_documents_context(tenant_id, latest_user_message)
    system_prompt = build_system_prompt(tenant_tools, documents_context, bot_config)

    messages = [{"role": "system", "content": system_prompt}]
    for msg in conversation:
        if isinstance(msg["content"], str):
            messages.append({"role": msg["role"], "content": msg["content"]})
        else:
            messages.extend(msg["content"])

    tools_executed_count = 0
    has_doc_context = bool(documents_context and documents_context.strip())

    for _ in range(MAX_TOOL_HOPS):
        stream = await client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            tools=tool_schemas,
            max_tokens=1024,
            stream=True,
        )

        content_parts: list[str] = []
        # Keyed by the delta's `index` (not tool_call id - the id itself
        # often only arrives on the FIRST fragment of a given tool call,
        # with later fragments for the same call carrying id=None but the
        # same index), so index is the only reliable key to accumulate on.
        tool_call_accum: dict[int, dict] = {}

        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta

            if delta.content:
                content_parts.append(delta.content)
                yield {"type": "token", "text": delta.content}

            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    slot = tool_call_accum.setdefault(tc_delta.index, {"id": "", "name": "", "arguments": ""})
                    if tc_delta.id:
                        slot["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            slot["name"] += tc_delta.function.name
                        if tc_delta.function.arguments:
                            slot["arguments"] += tc_delta.function.arguments

        if not tool_call_accum:
            final_text = "".join(content_parts)
            conversation.append({"role": "assistant", "content": final_text})
            yield {
                "type": "done",
                "text": final_text,
                "conversation": conversation,
                "tools_called_count": tools_executed_count,
                "has_doc_context": has_doc_context,
            }
            return

        tool_calls = [tool_call_accum[i] for i in sorted(tool_call_accum)]
        tools_executed_count += len(tool_calls)

        assistant_msg = {
            "role": "assistant",
            "content": "".join(content_parts) or None,
            "tool_calls": [
                {"id": tc["id"], "type": "function", "function": {"name": tc["name"], "arguments": tc["arguments"]}}
                for tc in tool_calls
            ],
        }
        messages.append(assistant_msg)

        for tc in tool_calls:
            yield {"type": "tool_start", "name": tc["name"]}

        # Run every tool call in this hop concurrently - previously these
        # were awaited one at a time in a for-loop, so N tool calls in one
        # hop cost N x (tool latency) instead of ~1x.
        tool_result_messages = await asyncio.gather(
            *[_run_one_tool_call(tc, tools_by_name) for tc in tool_calls]
        )
        messages.extend(tool_result_messages)

        conversation.append({"role": "assistant", "content": [assistant_msg] + list(tool_result_messages)})

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


async def run_groq_chat_turn(tenant_id: str, conversation: list[dict]) -> tuple[str, list[dict]]:
    """Non-streaming convenience wrapper kept for anything that still wants
    a single await (e.g. tests, or a future non-chat use of the same
    turn logic) - just drains the stream above and returns the final
    result, same shape as the original function."""
    final_text = ""
    final_conversation = conversation
    async for event in run_groq_chat_turn_stream(tenant_id, conversation):
        if event["type"] == "done":
            final_text = event["text"]
            final_conversation = event["conversation"]
    return final_text, final_conversation