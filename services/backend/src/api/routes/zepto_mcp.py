from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.core.config import settings
from src.services.zepto.client import ZEPTO_TOOL_DEFINITIONS, zepto_client

router = APIRouter(prefix="/api/v1/zepto/mcp", tags=["Zepto MCP"])


class CallToolRequest(BaseModel):
    tool_name: str = Field(..., description="Zepto MCP tool name (e.g. search_products, add_to_cart)")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Input parameters for the tool call")
    force_upstream: bool = Field(
        default=False,
        description="If True, sends HTTP request directly to live Zepto MCP endpoint even if unauthenticated",
    )


@router.get("/tools")
async def list_tools():
    """Retrieve all available Zepto MCP tools, their schemas, and current connection status."""
    return {
        "status": "online",
        "endpoint": settings.ZEPTO_MCP_ENDPOINT,
        "is_authenticated": zepto_client.is_authenticated,
        "tools_count": len(ZEPTO_TOOL_DEFINITIONS),
        "tools": ZEPTO_TOOL_DEFINITIONS,
    }


@router.get("/ping")
async def ping_mcp():
    """Ping the live Zepto MCP server to verify reachability and latency."""
    return await zepto_client.ping_upstream()


@router.post("/call")
async def call_tool(body: CallToolRequest):
    """Execute a single Zepto MCP tool test call with detailed JSON-RPC payload tracking."""
    result = await zepto_client.call_tool(
        name=body.tool_name,
        arguments=body.arguments,
        force_upstream=body.force_upstream,
    )
    return result


@router.post("/run-all-tests")
async def run_all_tool_tests():
    """Execute test requests across all non-destructive Zepto MCP tools and return a comprehensive report."""
    results = []
    total_time_ms = 0.0
    passed = 0

    # Exclude live purchasing tools from batch test suite to prevent accidental order placement
    batch_tools = [tool for tool in ZEPTO_TOOL_DEFINITIONS if not tool.get("skip_batch_test")]

    for tool in batch_tools:
        name = tool["name"]
        default_args = tool.get("default_input", {})
        res = await zepto_client.call_tool(name=name, arguments=default_args, force_upstream=False)
        total_time_ms += res.get("execution_time_ms", 0)
        is_success = res.get("status") == "success"
        if is_success:
            passed += 1

        results.append(
            {
                "tool_name": name,
                "category": tool.get("category"),
                "status": res.get("status"),
                "source": res.get("source"),
                "execution_time_ms": res.get("execution_time_ms"),
                "input_arguments": default_args,
                "raw_rpc_request": res.get("raw_rpc_request"),
                "response_preview": res.get("response"),
            }
        )

    return {
        "total_tools": len(batch_tools),
        "passed_tools": passed,
        "failed_tools": len(batch_tools) - passed,
        "total_execution_time_ms": round(max(total_time_ms, 0.05), 2),
        "is_authenticated": zepto_client.is_authenticated,
        "endpoint": settings.ZEPTO_MCP_ENDPOINT,
        "results": results,
    }
