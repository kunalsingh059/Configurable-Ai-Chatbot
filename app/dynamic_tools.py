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
from app.db import tools_collection
from app.models import serialize_tool

ALLOWED_SCHEMES = {"http", "https"}

# Cap how much of a tool's response we'll read into memory - a malicious or
# misbehaving upstream shouldn't be able to make us buffer gigabytes.
MAX_TOOL_RESPONSE_BYTES = 2 * 1024 * 1024  # 2MB


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
    cursor = tools_collection.find({"tenant_id": tenant_id})
    return [serialize_tool(doc) async for doc in cursor]


async def execute_tool(tool: dict, params: dict) -> dict:
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
                    return json.loads(body)
                except ValueError:
                    return {"raw_response": body[:500].decode(errors="replace")}

    except httpx.RequestError as e:
        return {"error": f"Could not reach the API: {str(e)}"}