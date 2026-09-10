"""
GENERIC TOOL ENGINE - same job as before (build Claude's tool schema from a
stored tool, execute the real HTTP call), now reading from Mongo instead of
SQLAlchemy.

SSRF PROTECTION: url_template is business-owner-configured, and the {param}
placeholders in it can be filled by params the LLM itself decided based on
the end chatbot user's message - so both a malicious business owner AND a
crafted chat message are untrusted input paths into the final URL. Every
resolved URL is validated (scheme + resolved IP not private/loopback/
link-local/metadata) right before the request is made, not just when the
tool is saved in the admin panel - DNS can change between save and use.
"""

import ipaddress
import json
import re
import socket
from urllib.parse import urlparse

import httpx
import jsonschema
from app.db import tools_collection
from app.models import serialize_tool
from app.crypto import decrypt_headers

ALLOWED_SCHEMES = {"http", "https"}

# Cap how much of a tool's response we'll read into memory - a malicious or
# misbehaving upstream shouldn't be able to make us buffer gigabytes.
MAX_TOOL_RESPONSE_BYTES = 2 * 1024 * 1024  # 2MB

# Cap how large the LLM-generated arguments themselves can be, before we
# even get to schema validation - a legitimate tool call is a handful of
# short fields (an order ID, a city name, etc), so this is a generous
# ceiling that only exists to stop something pathological.
MAX_PARAMS_JSON_BYTES = 20 * 1024  # 20KB


def _validate_tool_params(params_schema: dict, params: dict) -> str | None:
    """Validates the LLM-generated tool-call arguments against the tool's
    own stored params_schema, BEFORE any of it is used to build a URL or
    HTTP request. Returns None if valid, or a human-readable error string
    if not (never raises - execute_tool turns this into a normal {"error":
    ...} result, same as every other failure mode it already handles).

    The params_schema is business-owner-authored and is the server-side
    CONTRACT for what a tool call is allowed to look like - not just
    documentation for the model. Without this, a wrong-typed value, a
    missing required field, or an unexpected extra field the LLM
    hallucinated would flow straight into a real HTTP request against a
    real third-party API with zero checking.
    """
    try:
        if len(json.dumps(params)) > MAX_PARAMS_JSON_BYTES:
            return "Tool arguments are unexpectedly large"
    except (TypeError, ValueError):
        return "Tool arguments are not valid JSON"

    # additionalProperties defaults to True in JSON Schema (unknown fields
    # silently allowed) unless a schema author says otherwise. We want the
    # opposite default - reject anything the schema doesn't explicitly
    # define - while still letting a business owner opt back into
    # permissive behavior by setting additionalProperties: true themselves.
    schema = dict(params_schema or {})
    if schema.get("type") == "object" and "additionalProperties" not in schema:
        schema = {**schema, "additionalProperties": False}

    try:
        jsonschema.validate(instance=params, schema=schema)
    except jsonschema.exceptions.ValidationError as e:
        # e.message is already a clean, human-readable description (e.g.
        # "'barcode' is a required property" or "'abc' is not of type
        # 'number'") - safe to surface without leaking anything internal.
        return e.message
    except jsonschema.exceptions.SchemaError:
        # The tool's OWN stored schema is malformed - not the LLM's fault,
        # but we still can't safely validate against it, so fail closed
        # rather than skip validation entirely.
        return "This tool's parameter schema is misconfigured"

    return None

# Separate, much smaller cap on how much of a tool's result actually gets
# sent to the LLM (see format_tool_result_for_llm below). Real APIs often
# return far more than the model needs to answer one question - the useful
# fields are almost always near the top of the payload, so a hard
# truncation here keeps every follow-up turn cheap without losing the
# answer most of the time.
MAX_LLM_RESULT_CHARS = 4000


def _assert_url_is_safe(url: str) -> None:
    """Raises ValueError if `url` is not safe to fetch server-side. Blocks:
    non-http(s) schemes, missing hostname, and any hostname that resolves
    to a private/loopback/link-local/reserved IP (covers localhost,
    127.0.0.1, internal networks like 10.x/192.168.x, and cloud metadata
    endpoints like 169.254.169.254, which falls under link-local)."""
    parsed = urlparse(url)

    if parsed.scheme not in ALLOWED_SCHEMES:
        raise ValueError(f"URL scheme '{parsed.scheme}' is not allowed - only http/https")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL has no hostname")

    try:
        resolved = socket.getaddrinfo(hostname, None)
    except socket.gaierror as e:
        raise ValueError(f"Could not resolve hostname '{hostname}': {e}")

    for family, _, _, _, sockaddr in resolved:
        ip_str = sockaddr[0]
        ip = ipaddress.ip_address(ip_str)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise ValueError(
                f"Hostname '{hostname}' resolves to a blocked address ({ip_str}) - "
                "internal/private/link-local/metadata addresses are not allowed"
            )


def build_claude_schema(tool: dict) -> dict:
    return {
        "name": tool["name"],
        "description": tool["description"],
        "input_schema": tool["params_schema"],
    }


async def get_tenant_tools(tenant_id: str) -> list[dict]:
    """ADMIN-FACING: headers are masked to header_keys only - see
    serialize_tool's docstring. Used by GET/POST/PUT /admin/tools. Do NOT
    use this for actual tool execution (chat runtime) - it can't make a
    real HTTP call, since it never has the real header values."""
    cursor = tools_collection.find({"tenant_id": tenant_id})
    return [serialize_tool(doc) async for doc in cursor]


async def get_tenant_tools_for_execution(tenant_id: str) -> list[dict]:
    """RUNTIME-FACING: headers are decrypted to real values server-side,
    for actually making the HTTP call in execute_tool(). Used by
    claude_client.py/groq_client.py/mock_llm.py only - NEVER return this
    data to the browser (decrypted secrets included)."""
    cursor = tools_collection.find({"tenant_id": tenant_id})
    tools = []
    async for doc in cursor:
        tools.append({
            "id": str(doc["_id"]),
            "tenant_id": doc["tenant_id"],
            "name": doc["name"],
            "description": doc["description"],
            "method": doc.get("method", "GET"),
            "url_template": doc["url_template"],
            "headers": decrypt_headers(doc.get("headers_encrypted")),
            "params_schema": doc["params_schema"],
            "response_fields": doc.get("response_fields", []),
        })
    return tools


def _apply_response_fields(parsed, fields: list[str]):
    """Trims a successful JSON response down to just the top-level keys the
    business owner cares about, when they've configured any. Only applies
    to plain objects - a list or scalar response passes through untouched,
    since "top-level keys" doesn't mean anything for those shapes."""
    if not fields or not isinstance(parsed, dict):
        return parsed
    return {k: parsed[k] for k in fields if k in parsed}


def format_tool_result_for_llm(result: dict) -> str:
    """Turns a tool's result dict into the text actually sent to the LLM.

    Two things this fixes vs. the old `str(result)`:
      1. Proper JSON (json.dumps) instead of Python's dict repr - str()
         produces single-quoted strings and None/True/False instead of
         null/true/false, which is both non-standard for an LLM to parse
         and needlessly token-heavier.
      2. A hard length cap - an upstream API can return many KB of nested
         JSON for one lookup; sending all of it on every subsequent turn
         of the conversation is expensive and rarely necessary, since the
         fields that answer the user's question are almost always near
         the top of the payload.
    """
    try:
        text = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        text = str(result)

    if len(text) > MAX_LLM_RESULT_CHARS:
        text = text[:MAX_LLM_RESULT_CHARS] + f"...[truncated, {len(text)} chars total]"

    return text


async def execute_tool(tool: dict, params: dict) -> dict:
    validation_error = _validate_tool_params(tool.get("params_schema") or {}, params)
    if validation_error:
        return {"error": f"Invalid tool arguments: {validation_error}"}

    url = tool["url_template"]
    remaining_params = dict(params)

    for match in re.findall(r"\{(\w+)\}", url):
        if match in remaining_params:
            url = url.replace(f"{{{match}}}", str(remaining_params.pop(match)))
        else:
            return {"error": f"Missing required path parameter: {match}"}

    try:
        _assert_url_is_safe(url)
    except ValueError as e:
        return {"error": f"Blocked unsafe tool URL: {e}"}

    headers = tool.get("headers") or {}
    method = (tool.get("method") or "GET").upper()
    if method not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
        return {"error": f"Unsupported method: {method}"}

    request_kwargs = {"headers": headers}
    if method in ("POST", "PUT", "PATCH"):
        request_kwargs["json"] = remaining_params
    else:
        request_kwargs["params"] = remaining_params

    try:
        # follow_redirects=False on purpose: a validated-safe URL could
        # redirect to an internal address, and re-validating a redirect
        # chain is extra complexity we don't need - just refuse to follow.
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            async with client.stream(method, url, **request_kwargs) as resp:
                if resp.is_redirect:
                    return {"error": "Blocked: tool endpoint attempted a redirect"}

                body = b""
                async for chunk in resp.aiter_bytes():
                    body += chunk
                    if len(body) > MAX_TOOL_RESPONSE_BYTES:
                        return {"error": "Tool response too large"}

                if resp.status_code >= 400:
                    return {
                        "error": f"API returned status {resp.status_code}",
                        "detail": body[:300].decode(errors="replace"),
                    }

                try:
                    parsed = json.loads(body)
                except ValueError:
                    return {"raw_response": body[:500].decode(errors="replace")}

                return _apply_response_fields(parsed, tool.get("response_fields") or [])

    except httpx.RequestError as e:
        return {"error": f"Could not reach the API: {str(e)}"}