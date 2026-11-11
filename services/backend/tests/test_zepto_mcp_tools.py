import httpx
import pytest

from src.services.zepto.client import ZEPTO_TOOL_DEFINITIONS, ZeptoMCPClient, zepto_client


@pytest.fixture(autouse=True)
def clean_zepto_state():
    """Ensure zepto_client has clean token state for tests."""
    zepto_client.access_token = None
    zepto_client.refresh_token = None
    yield
    zepto_client.access_token = None
    zepto_client.refresh_token = None


@pytest.mark.asyncio
async def test_zepto_mcp_tools_metadata_endpoint(client):
    """Verify GET /api/v1/zepto/mcp/tools lists all available tools with schemas."""
    response = await client.get("/api/v1/zepto/mcp/tools")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert data["tools_count"] == len(ZEPTO_TOOL_DEFINITIONS)
    assert len(data["tools"]) >= 10

    tool_names = {tool["name"] for tool in data["tools"]}
    expected_tools = {
        "search_products",
        "search_multiple_products",
        "get_past_order_items",
        "get_product_details",
        "list_saved_addresses",
        "select_saved_address",
        "get_location_serviceability",
        "select_store",
        "get_user_details",
        "view_cart",
        "update_cart",
        "get_payment_methods",
        "create_order",
        "create_online_payment_order",
        "check_payment_status",
        "get_order_detail",
        "list_order_history",
    }
    assert expected_tools.issubset(tool_names)


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_def", ZEPTO_TOOL_DEFINITIONS, ids=lambda t: t["name"])
async def test_each_zepto_tool_executes_successfully_and_returns_rpc_contract(client, tool_def):
    """Test every Zepto MCP tool individually via POST /api/v1/zepto/mcp/call."""
    tool_name = tool_def["name"]
    input_args = tool_def.get("default_input", {})

    response = await client.post(
        "/api/v1/zepto/mcp/call",
        json={"tool_name": tool_name, "arguments": input_args},
    )

    assert response.status_code == 200
    data = response.json()

    # Verify MCP JSON-RPC 2.0 contract
    assert data["tool_name"] == tool_name
    assert data["input_arguments"] == input_args
    assert data["status"] == "success"
    assert data["status_code"] == 200
    assert "execution_time_ms" in data
    assert data["execution_time_ms"] >= 0

    rpc_req = data["raw_rpc_request"]
    assert rpc_req["jsonrpc"] == "2.0"
    assert rpc_req["method"] == "tools/call"
    assert rpc_req["params"]["name"] == tool_name
    assert rpc_req["params"]["arguments"] == input_args

    # Check tool-specific response contents
    resp = data["response"]
    if tool_name in ("search_products", "search_multiple_products"):
        assert "items" in resp
        assert "serving_store" in resp
        assert len(resp["items"]) > 0
    elif tool_name == "get_product_details":
        expected_pid = input_args.get("product_variant_id") or input_args.get("product_id")
        assert resp["product_id"] == expected_pid
        assert "price" in resp
        assert "available_stock" in resp
    elif tool_name == "view_cart":
        assert "items" in resp
        assert "total_payable" in resp
    elif tool_name == "update_cart":
        assert resp["status"] == "success"
        expected_id = input_args.get("productVariantId") or input_args.get("item_id")
        assert resp["item_id"] == expected_id
    elif tool_name == "get_location_serviceability":
        assert resp["serviceable"] is True
        assert len(resp["locations"]) > 0
    elif tool_name in ("create_order", "create_online_payment_order"):
        assert "order_id" in resp
    elif tool_name == "get_order_detail":
        assert resp["order_id"] == input_args["orderId"]
    elif tool_name == "list_order_history":
        assert "orders" in resp
        assert len(resp["orders"]) > 0
    elif tool_name == "select_store":
        assert resp["status"] == "selected"
    elif tool_name == "get_payment_methods":
        assert "payment_methods" in resp
    elif tool_name == "check_payment_status":
        assert resp["payment_status"] == "PAID"


@pytest.mark.asyncio
async def test_run_all_tools_summary_endpoint(client):
    """Verify POST /api/v1/zepto/mcp/run-all-tests runs all tools and produces clean report."""
    response = await client.post("/api/v1/zepto/mcp/run-all-tests")

    assert response.status_code == 200
    report = response.json()

    assert report["total_tools"] == len(ZEPTO_TOOL_DEFINITIONS)
    assert report["passed_tools"] == len(ZEPTO_TOOL_DEFINITIONS)
    assert report["failed_tools"] == 0
    assert report["total_execution_time_ms"] >= 0
    assert len(report["results"]) == len(ZEPTO_TOOL_DEFINITIONS)
    assert all(r["status"] == "success" for r in report["results"])


@pytest.mark.asyncio
async def test_force_upstream_unauthenticated_captures_live_mcp_rejection(client, monkeypatch):
    """Verify force_upstream=True executes HTTP call to Zepto endpoint and captures upstream 401."""
    original_post = httpx.AsyncClient.post

    async def mock_upstream_post(self, url, **kwargs):
        if "mcp.zepto.co.in" in str(url):
            return httpx.Response(
                401,
                json={"error": "unauthorized", "error_description": "Authorization header is required"},
            )
        return await original_post(self, url, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_upstream_post)

    response = await client.post(
        "/api/v1/zepto/mcp/call",
        json={
            "tool_name": "search_products",
            "arguments": {"query": "Milk"},
            "force_upstream": True,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "live_mcp"
    assert data["status"] == "error"
    assert data["status_code"] == 401
    assert "unauthorized" in str(data["error"])


@pytest.mark.asyncio
async def test_authenticated_client_calls_live_mcp_successfully(client, monkeypatch):
    """Verify that when authenticated, client attaches Bearer token, negotiates session, and parses live response."""
    zepto_client.set_tokens("live_valid_test_token_999")
    original_post = httpx.AsyncClient.post

    async def mock_live_upstream(self, url, **kwargs):
        if "mcp.zepto.co.in" in str(url):
            headers = kwargs.get("headers") or {}
            json_data = kwargs.get("json") or {}
            assert headers.get("Authorization") == "Bearer live_valid_test_token_999"

            if json_data.get("method") == "initialize":
                return httpx.Response(
                    200,
                    headers={"mcp-session-id": "mock_test_sess_999", "content-type": "application/json"},
                    json={"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2024-11-05"}},
                )
            if json_data.get("method") == "notifications/initialized":
                return httpx.Response(202, headers={"mcp-session-id": "mock_test_sess_999"})
            if (
                json_data.get("method") == "tools/call"
                and json_data.get("params", {}).get("name") == "list_saved_addresses"
            ):
                return httpx.Response(
                    200,
                    headers={"mcp-session-id": "mock_test_sess_999"},
                    json={"jsonrpc": "2.0", "result": {"structuredContent": {"addresses": []}}},
                )

            assert headers.get("Mcp-Session-Id") == "mock_test_sess_999"
            assert json_data.get("method") == "tools/call"
            return httpx.Response(
                200,
                headers={"mcp-session-id": "mock_test_sess_999"},
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "result": {
                        "items": [
                            {
                                "id": "live_sku_1",
                                "name": "Live Store Amul Milk",
                                "price": 54.0,
                                "is_available": True,
                            }
                        ]
                    },
                },
            )
        return await original_post(self, url, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_live_upstream)

    response = await client.post(
        "/api/v1/zepto/mcp/call",
        json={"tool_name": "search_products", "arguments": {"query": "Amul"}},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "live_mcp"
    assert data["status"] == "success"
    assert data["is_authenticated"] is True
    assert data["session_id"] == "mock_test_sess_999"
    assert data["response"]["items"][0]["name"] == "Live Store Amul Milk"


@pytest.mark.asyncio
async def test_zepto_client_convenience_methods():
    """Verify individual Python convenience methods on ZeptoMCPClient."""
    inst = ZeptoMCPClient()
    cart = await inst.get_cart()
    assert "items" in cart

    prod = await inst.get_product_details("z_milk_toned_1l")
    assert prod["product_id"] == "z_milk_toned_1l"

    loc = await inst.search_location("Indiranagar")
    assert loc["serviceable"] is True

    order = await inst.place_order("cod")
    assert order["status"] == "confirmed"

    status = await inst.get_order_status("z_ord_882910")
    assert status["order_id"] == "z_ord_882910"

    orders = await inst.list_orders(3)
    assert len(orders) <= 3
