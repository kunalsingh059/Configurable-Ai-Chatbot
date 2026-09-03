"""
GENERIC TOOL ENGINE - same job as before (build Claude's tool schema from a
stored tool, execute the real HTTP call), now reading from Mongo instead of
SQLAlchemy.
"""

import re
import httpx
from app.db import tools_collection
from app.models import serialize_tool


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

    headers = tool.get("headers") or {}
    method = (tool.get("method") or "GET").upper()

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            if method == "GET":
                resp = await client.get(url, headers=headers, params=remaining_params)
            elif method in ("POST", "PUT", "PATCH"):
                resp = await client.request(method, url, headers=headers, json=remaining_params)
            elif method == "DELETE":
                resp = await client.delete(url, headers=headers, params=remaining_params)
            else:
                return {"error": f"Unsupported method: {method}"}

        if resp.status_code >= 400:
            return {"error": f"API returned status {resp.status_code}", "detail": resp.text[:300]}

        return resp.json()

    except httpx.RequestError as e:
        return {"error": f"Could not reach the API: {str(e)}"}
    except ValueError:
        return {"raw_response": resp.text[:500]}