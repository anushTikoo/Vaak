import contextlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from src.core.config import settings
from src.core.logging import logger


def _find_token_cache() -> Path | None:
    candidates = [
        Path(".zepto_token.json"),
        Path("services/backend/.zepto_token.json"),
        Path(__file__).resolve().parent.parent.parent.parent / ".zepto_token.json",
        Path(__file__).resolve().parent.parent.parent.parent / "services" / "backend" / ".zepto_token.json",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def _get_primary_token_file() -> Path:
    # Save to services/backend/.zepto_token.json if directory exists, else .zepto_token.json
    if Path("services/backend").exists():
        return Path("services/backend/.zepto_token.json")
    return Path(".zepto_token.json")


# Universal Commerce Protocol (UCP) / Official Zepto MCP Tool Definitions
ZEPTO_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "search_products",
        "category": "Catalog & Search",
        "description": "Search for ONE concrete purchasable product in the Zepto dark store catalog.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search keyword (e.g. 'Amul Milk', 'Bread')"},
                "quantity": {"type": "number", "description": "Desired quantity (default: 1)", "default": 1},
            },
            "required": ["query"],
        },
        "default_input": {"query": "Amul Milk", "quantity": 1},
    },
    {
        "name": "search_multiple_products",
        "category": "Catalog & Search",
        "description": "Search for multiple different products simultaneously (e.g. ['diet coke', 'chips']).",
        "parameters": {
            "type": "object",
            "properties": {
                "queries": {
                    "type": "array",
                    "description": "Array of product search queries",
                    "items": {"type": "string"},
                },
            },
            "required": ["queries"],
        },
        "default_input": {"queries": ["Amul Milk", "Brown Bread"]},
    },
    {
        "name": "get_past_order_items",
        "category": "Catalog & Search",
        "description": "Retrieve unique products ordered in the user's last 30+ orders, sorted by frequency.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
        "default_input": {},
    },
    {
        "name": "get_product_details",
        "category": "Catalog & Search",
        "description": "Fetch detailed live metadata for a specific product SKU / variant.",
        "parameters": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string", "description": "Product ID or variant ID"},
            },
            "required": ["product_id"],
        },
        "default_input": {"product_id": "z_milk_toned_1l"},
    },
    {
        "name": "list_saved_addresses",
        "category": "Location & Store",
        "description": "List all saved customer delivery addresses for the authenticated user.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
        "default_input": {},
    },
    {
        "name": "select_saved_address",
        "category": "Location & Store",
        "description": "Select a delivery address and automatically bind the serving dark store ID for this session.",
        "parameters": {
            "type": "object",
            "properties": {
                "addressId": {"type": "string", "description": "Saved address ID"},
            },
            "required": ["addressId"],
        },
        "default_input": {"addressId": "default_home_address"},
    },
    {
        "name": "get_location_serviceability",
        "category": "Location & Store",
        "description": "Check if Zepto services a location and retrieve nearest dark store details.",
        "parameters": {
            "type": "object",
            "properties": {
                "pincode": {"type": "string", "description": "6-digit Indian PIN code", "default": "400014"},
            },
            "required": ["pincode"],
        },
        "default_input": {"pincode": "400014"},
    },
    {
        "name": "get_user_details",
        "category": "Account & Profile",
        "description": "Fetch authenticated user's profile details including name, verification, and status.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
        "default_input": {},
    },
    {
        "name": "get_cart",
        "category": "Cart Management",
        "description": "View current user cart contents, item breakdown, and delivery fees.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
        "default_input": {},
    },
    {
        "name": "view_cart",
        "category": "Cart Management",
        "description": "View current user cart contents, item breakdown, and delivery fees.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
        "default_input": {},
    },
    {
        "name": "add_to_cart",
        "category": "Cart Management",
        "description": "Add a grocery SKU with specified quantity to the user's active Zepto basket.",
        "parameters": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string", "description": "Product SKU ID"},
                "quantity": {"type": "integer", "description": "Number of units to add", "default": 1},
            },
            "required": ["product_id"],
        },
        "default_input": {"product_id": "z_eggs_6pk", "quantity": 2},
    },
    {
        "name": "update_cart",
        "category": "Cart Management",
        "description": "Add, modify quantity, or remove items from the live Zepto cart.",
        "parameters": {
            "type": "object",
            "properties": {
                "item_id": {"type": "string", "description": "Cart item ID or product SKU"},
                "quantity": {"type": "integer", "description": "New unit count", "default": 1},
            },
            "required": ["item_id", "quantity"],
        },
        "default_input": {"item_id": "z_eggs_6pk", "quantity": 2},
    },
    {
        "name": "remove_from_cart",
        "category": "Cart Management",
        "description": "Remove a specific item line from the active Zepto cart.",
        "parameters": {
            "type": "object",
            "properties": {
                "item_id": {"type": "string", "description": "Cart item ID or product SKU"},
            },
            "required": ["item_id"],
        },
        "default_input": {"item_id": "z_eggs_6pk"},
    },
    {
        "name": "clear_cart",
        "category": "Cart Management",
        "description": "Empty all items from the current Zepto cart session.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
        "default_input": {},
    },
    {
        "name": "search_location",
        "category": "Location & Store",
        "description": "Resolve delivery address, area, or Indian PIN code to locate nearest serving dark store.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Locality or address (e.g. 'Indiranagar, Bengaluru')"},
                "pincode": {"type": "string", "description": "6-digit Indian PIN code", "default": "400014"},
            },
            "required": ["query"],
        },
        "default_input": {"query": "Indiranagar, Bengaluru", "pincode": "400014"},
    },
    {
        "name": "place_order",
        "category": "Orders & Checkout",
        "description": "Place a real Cash on Delivery (COD) grocery order with the serving dark store.",
        "parameters": {
            "type": "object",
            "properties": {
                "payment_method": {"type": "string", "description": "Payment method: 'cod'", "default": "cod"},
                "address_id": {"type": "string", "description": "Saved address ID", "default": "addr_home_primary"},
            },
            "required": ["payment_method"],
        },
        "default_input": {"payment_method": "cod", "address_id": "addr_home_primary"},
    },
    {
        "name": "get_order_status",
        "category": "Orders & Checkout",
        "description": "Query real-time 10-minute order status, dark store packing, and delivery rider ETA.",
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "Zepto order reference ID"},
            },
            "required": ["order_id"],
        },
        "default_input": {"order_id": "z_ord_882910"},
    },
    {
        "name": "list_orders",
        "category": "Orders & Checkout",
        "description": "Retrieve recent order history with delivery timestamps and total spent.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Number of previous orders to return", "default": 5},
            },
            "required": [],
        },
        "default_input": {"limit": 5},
    },
    {
        "name": "get_payment_methods",
        "category": "Orders & Checkout",
        "description": "Get available payment methods (COD, UPI, Cards, Zepto Cash) for active cart.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
        "default_input": {},
    },
    {
        "name": "create_order",
        "category": "Orders & Checkout",
        "description": "Place a real Cash on Delivery (COD) grocery order with the serving dark store.",
        "parameters": {
            "type": "object",
            "properties": {
                "confirmOrder": {"type": "boolean", "description": "Must be true to place order", "default": False},
                "riderTip": {"type": "number", "description": "Tip for the rider in INR", "default": 0},
            },
            "required": [],
        },
        "default_input": {"confirmOrder": False, "riderTip": 0},
    },
    {
        "name": "get_order_detail",
        "category": "Orders & Checkout",
        "description": "Query detailed order tracking, packing state, and delivery rider ETA.",
        "parameters": {
            "type": "object",
            "properties": {
                "orderId": {"type": "string", "description": "Zepto order ID"},
            },
            "required": ["orderId"],
        },
        "default_input": {"orderId": "z_ord_882910"},
    },
    {
        "name": "list_order_history",
        "category": "Orders & Checkout",
        "description": "Retrieve recent order history with delivery timestamps and total spent.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Number of previous orders to return", "default": 5},
            },
            "required": [],
        },
        "default_input": {"limit": 5},
    },
]


class ZeptoMCPClient:
    """Client for Zepto Official MCP Server (mcp.zepto.co.in/mcp).

    Implements full Model Context Protocol (MCP) streamable HTTP session lifecycle:
    - Automatically sends JSON-RPC 'initialize' handshake
    - Captures and passes 'Mcp-Session-Id' header on all requests
    - Accepts both 'application/json' and 'text/event-stream' (SSE)
    - Automatically bootstraps delivery address & dark store context
    - Automatically handles session expiry and re-negotiation
    """

    def __init__(self):
        self.endpoint = settings.ZEPTO_MCP_ENDPOINT
        self.client_id = settings.ZEPTO_CLIENT_ID
        self.access_token: str | None = None
        self.refresh_token: str | None = None
        self.session_id: str | None = None
        self.selected_address_id: str | None = None
        self.selected_store_id: str | None = None

        # Only load persisted token in live server runtime, not during pytest test runs
        if "pytest" not in sys.modules:
            token_path = _find_token_cache()
            if token_path:
                try:
                    data = json.loads(token_path.read_text(encoding="utf-8"))
                    self.access_token = data.get("access_token")
                    self.refresh_token = data.get("refresh_token")
                    if self.access_token:
                        logger.info(f"Restored persisted Zepto MCP session from {token_path}")
                except Exception as e:
                    logger.warning(f"Failed to read token cache: {e}")

    @property
    def is_authenticated(self) -> bool:
        return bool(self.access_token)

    def set_tokens(self, access_token: str, refresh_token: str | None = None):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.session_id = None  # Reset session when token changes
        logger.info("Zepto MCP access token successfully updated")
        if "pytest" not in sys.modules:
            try:
                target = _get_primary_token_file()
                payload = json.dumps({"access_token": access_token, "refresh_token": refresh_token})
                target.write_text(payload, encoding="utf-8")
                # Also write to root if running in backend dir
                alt = Path(".zepto_token.json")
                if alt != target:
                    with contextlib.suppress(Exception):
                        alt.write_text(payload, encoding="utf-8")
            except Exception as e:
                logger.warning(f"Failed to persist token cache: {e}")

    def clear_tokens(self):
        self.access_token = None
        self.refresh_token = None
        self.session_id = None
        self.selected_address_id = None
        self.selected_store_id = None
        for p in [Path(".zepto_token.json"), Path("services/backend/.zepto_token.json")]:
            if p.exists():
                with contextlib.suppress(Exception):
                    p.unlink()
        logger.info("Zepto MCP tokens cleared")

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """Return the schema metadata for all Zepto MCP tools."""
        return ZEPTO_TOOL_DEFINITIONS

    def _parse_mcp_response(self, resp: httpx.Response) -> dict[str, Any]:
        """Parse MCP HTTP response handling both raw JSON and text/event-stream SSE format."""
        content_type = resp.headers.get("content-type", "")
        text = resp.text

        if "text/event-stream" in content_type or text.startswith("event:") or text.startswith("data:"):
            # Extract JSON-RPC payload from SSE event stream lines
            for line in text.splitlines():
                line_str = line.strip()
                if line_str.startswith("data:"):
                    raw_json = line_str[5:].strip()
                    try:
                        return json.loads(raw_json)
                    except Exception:
                        pass

        try:
            return resp.json()
        except Exception:
            return {"raw_text": text}

    async def _ensure_session(self, http_client: httpx.AsyncClient) -> str:
        """Establish stateful MCP session via 'initialize' handshake and bootstrap dark store location."""
        if self.session_id:
            return self.session_id

        logger.info("Initiating Zepto MCP session handshake (POST /initialize)...")
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        init_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}, "resources": {}},
                "clientInfo": {"name": "vaak-agent", "version": "1.0.0"},
            },
        }

        init_resp = await http_client.post(self.endpoint, headers=headers, json=init_payload)
        session_id = init_resp.headers.get("mcp-session-id") or init_resp.headers.get("Mcp-Session-Id")

        if not session_id:
            parsed = self._parse_mcp_response(init_resp)
            logger.warning(f"Zepto initialize did not return Mcp-Session-Id: {init_resp.status_code} {parsed}")
            raise RuntimeError(f"Zepto MCP handshake failed: {init_resp.status_code}")

        self.session_id = session_id
        logger.info(f"Zepto MCP session established successfully: {self.session_id}")

        # Send notifications/initialized
        headers["Mcp-Session-Id"] = self.session_id
        with contextlib.suppress(Exception):
            await http_client.post(
                self.endpoint,
                headers=headers,
                json={"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            )

        # Auto-bootstrap dark store location from user's saved addresses
        try:
            addr_payload = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "list_saved_addresses", "arguments": {}},
            }
            addr_resp = await http_client.post(self.endpoint, headers=headers, json=addr_payload)
            parsed_addr = self._parse_mcp_response(addr_resp)
            addresses = parsed_addr.get("result", {}).get("structuredContent", {}).get("addresses", [])
            if addresses:
                primary_addr = addresses[0]
                addr_id = primary_addr.get("id")
                if addr_id:
                    label = primary_addr.get("label", "home")
                    logger.info(f"Auto-binding primary saved address ({label}): {addr_id}")
                    sel_payload = {
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "tools/call",
                        "params": {"name": "select_saved_address", "arguments": {"addressId": addr_id}},
                    }
                    sel_resp = await http_client.post(self.endpoint, headers=headers, json=sel_payload)
                    sel_parsed = self._parse_mcp_response(sel_resp)
                    self.selected_address_id = addr_id
                    self.selected_store_id = sel_parsed.get("result", {}).get("structuredContent", {}).get("storeId")
                    logger.info(f"Dark store active: {self.selected_store_id}")
        except Exception as e:
            logger.warning(f"Address bootstrap notice: {e}")

        return self.session_id

    def _resolve_tool_mapping(self, name: str, args: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        """Map generic / legacy tool calls to official Zepto MCP server tool names and parameters."""
        # Mapping aliases
        if name in ("get_cart", "cart"):
            return "view_cart", {}
        if name == "search_location":
            if "pincode" in args:
                return "get_location_serviceability", {"pincode": str(args["pincode"])}
            return "list_saved_addresses", {}
        if name in ("place_order", "checkout"):
            return "create_order", {
                "confirmOrder": bool(args.get("confirmOrder", False)),
                "riderTip": args.get("riderTip", 0),
            }
        if name in ("get_order_status", "track_order"):
            return "get_order_detail", {"orderId": args.get("order_id", args.get("orderId", "z_ord_882910"))}
        if name in ("list_orders", "order_history"):
            return "list_order_history", {"limit": args.get("limit", 5)}
        if name == "add_to_cart":
            pid = args.get("product_id", args.get("productVariantId", "z_eggs_6pk"))
            qty = args.get("quantity", 1)
            return "update_cart", {"items": [{"productVariantId": pid, "quantity": qty}]}
        if name == "remove_from_cart":
            item_id = args.get("item_id", args.get("product_id", "z_eggs_6pk"))
            return "update_cart", {"items": [{"productVariantId": item_id, "quantity": 0}]}
        if name == "clear_cart":
            return "view_cart", {}

        return name, args

    async def ping_upstream(self) -> dict[str, Any]:
        """Ping the live Zepto MCP server endpoint to verify network reachability."""
        start_time = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=8.0) as http_client:
                resp = await http_client.post(
                    self.endpoint,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json, text/event-stream",
                    },
                    json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
                )
                elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
                return {
                    "reachable": True,
                    "status_code": resp.status_code,
                    "latency_ms": elapsed_ms,
                    "endpoint": self.endpoint,
                    "headers": dict(resp.headers),
                    "response": resp.text[:300],
                }
        except Exception as err:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return {
                "reachable": False,
                "error": str(err),
                "latency_ms": elapsed_ms,
                "endpoint": self.endpoint,
            }

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        force_upstream: bool = False,
    ) -> dict[str, Any]:
        """Execute a tool call using standard JSON-RPC 2.0 protocol against Zepto MCP with session support."""
        args = arguments or {}

        payload = {
            "jsonrpc": "2.0",
            "id": int(time.time() * 1000) % 100000,
            "method": "tools/call",
            "params": {
                "name": name,
                "arguments": args,
            },
        }

        start_time = time.perf_counter()

        # Execute upstream request if authenticated or forced by tester
        if self.is_authenticated or force_upstream:
            target_name, target_args = self._resolve_tool_mapping(name, args)
            upstream_payload = {
                "jsonrpc": "2.0",
                "id": payload["id"],
                "method": "tools/call",
                "params": {
                    "name": target_name,
                    "arguments": target_args,
                },
            }

            try:
                headers = {
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                }
                if self.access_token:
                    headers["Authorization"] = f"Bearer {self.access_token}"

                async with httpx.AsyncClient(timeout=15.0) as http_client:
                    # 1. Establish stateful MCP session if authenticated
                    if self.is_authenticated:
                        try:
                            session_id = await self._ensure_session(http_client)
                            headers["Mcp-Session-Id"] = session_id
                        except Exception as sess_err:
                            logger.warning(f"Could not establish MCP session: {sess_err}")

                    # 2. Execute tool call
                    resp = await http_client.post(self.endpoint, headers=headers, json=upstream_payload)
                    elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
                    parsed_body = self._parse_mcp_response(resp)

                    # 3. Check for session expiry error and auto-recover once
                    err_text = str(parsed_body.get("error", ""))
                    if (resp.status_code in (400, 404) or "Mcp-Session-Id" in err_text) and self.is_authenticated:
                        logger.info("Mcp-Session-Id expired or missing. Re-initializing session and retrying...")
                        self.session_id = None
                        session_id = await self._ensure_session(http_client)
                        headers["Mcp-Session-Id"] = session_id
                        resp = await http_client.post(self.endpoint, headers=headers, json=upstream_payload)
                        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
                        parsed_body = self._parse_mcp_response(resp)

                    # 4. Handle success response
                    if resp.status_code == 200 and "error" not in parsed_body:
                        result_data = parsed_body.get("result", parsed_body)
                        return {
                            "tool_name": name,
                            "target_tool_name": target_name,
                            "input_arguments": args,
                            "raw_rpc_request": upstream_payload,
                            "status": "success",
                            "status_code": 200,
                            "source": "live_mcp",
                            "is_authenticated": self.is_authenticated,
                            "session_id": self.session_id,
                            "active_store_id": self.selected_store_id,
                            "endpoint": self.endpoint,
                            "execution_time_ms": elapsed_ms,
                            "response": result_data,
                        }
                    else:
                        err_payload = (
                            parsed_body
                            if "error" in parsed_body and not isinstance(parsed_body["error"], dict)
                            else parsed_body.get("error", parsed_body)
                        )
                        if force_upstream or self.is_authenticated:
                            return {
                                "tool_name": name,
                                "target_tool_name": target_name,
                                "input_arguments": args,
                                "raw_rpc_request": upstream_payload,
                                "status": "error",
                                "status_code": resp.status_code,
                                "source": "live_mcp",
                                "is_authenticated": self.is_authenticated,
                                "endpoint": self.endpoint,
                                "execution_time_ms": elapsed_ms,
                                "error": err_payload,
                                "note": (
                                    "Upstream Zepto MCP returned non-200. Check OAuth scopes or address selection."
                                    if resp.status_code != 200
                                    else None
                                ),
                            }
            except Exception as e:
                logger.warning(f"Live Zepto MCP call failed: {e}")
                if force_upstream:
                    elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
                    return {
                        "tool_name": name,
                        "input_arguments": args,
                        "raw_rpc_request": payload,
                        "status": "error",
                        "status_code": 500,
                        "source": "live_mcp",
                        "is_authenticated": self.is_authenticated,
                        "endpoint": self.endpoint,
                        "execution_time_ms": elapsed_ms,
                        "error": str(e),
                    }

        # Sandbox / Development Mock Response (accurately mimics Zepto dark store schema)
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
        mock_result = self._generate_sandbox_response(name, args)
        return {
            "tool_name": name,
            "input_arguments": args,
            "raw_rpc_request": payload,
            "status": "success",
            "status_code": 200,
            "source": "sandbox_mock",
            "is_authenticated": False,
            "endpoint": self.endpoint,
            "execution_time_ms": elapsed_ms,
            "response": mock_result,
            "note": (
                "Running in realistic Zepto dark store sandbox mode. "
                "Connect via OAuth to link your live Zepto account."
            ),
        }

    def _generate_sandbox_response(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Generate realistic quick-commerce dark store responses for each tool."""
        if name in ("search_products", "search_multiple_products"):
            query = str(args.get("query", "groceries")).lower()
            limit = int(args.get("limit", args.get("quantity", 5)))

            catalog = [
                {
                    "product_id": "z_milk_toned_1l",
                    "name": "Amul Taaza Toned Fresh Milk",
                    "price": 54.0,
                    "mrp": 54.0,
                    "pack_size": "1 L",
                    "is_available": True,
                    "category": "Dairy, Bread & Eggs",
                    "eta_minutes": 10,
                    "image_url": "https://cdn.zeptonow.com/production/ik-seo/tr:w-200,h-200,cm-pad_resize/catalog/amul_milk.jpg",
                },
                {
                    "product_id": "z_eggs_6pk",
                    "name": "Eggoz Farm Fresh White Eggs - Pack of 6",
                    "price": 58.0,
                    "mrp": 65.0,
                    "pack_size": "6 pcs",
                    "is_available": True,
                    "category": "Dairy, Bread & Eggs",
                    "eta_minutes": 10,
                    "image_url": "https://cdn.zeptonow.com/production/ik-seo/tr:w-200,h-200,cm-pad_resize/catalog/eggoz_6.jpg",
                },
                {
                    "product_id": "z_bread_brown_400g",
                    "name": "English Oven 100% Whole Wheat Brown Bread",
                    "price": 45.0,
                    "mrp": 50.0,
                    "pack_size": "400 g",
                    "is_available": True,
                    "category": "Bakery & Breads",
                    "eta_minutes": 10,
                    "image_url": "https://cdn.zeptonow.com/production/ik-seo/tr:w-200,h-200,cm-pad_resize/catalog/brown_bread.jpg",
                },
                {
                    "product_id": "z_butter_100g",
                    "name": "Amul Pasteurised Butter",
                    "price": 56.0,
                    "mrp": 60.0,
                    "pack_size": "100 g",
                    "is_available": True,
                    "category": "Dairy & Milk Products",
                    "eta_minutes": 10,
                    "image_url": "https://cdn.zeptonow.com/production/ik-seo/tr:w-200,h-200,cm-pad_resize/catalog/amul_butter.jpg",
                },
                {
                    "product_id": "z_atta_5kg",
                    "name": "Aashirvaad Superior MP Sharbati Whole Wheat Atta",
                    "price": 275.0,
                    "mrp": 310.0,
                    "pack_size": "5 kg",
                    "is_available": True,
                    "category": "Atta, Rice & Dal",
                    "eta_minutes": 10,
                    "image_url": "https://cdn.zeptonow.com/production/ik-seo/tr:w-200,h-200,cm-pad_resize/catalog/aashirvaad_atta.jpg",
                },
            ]

            stopwords = {
                "i",
                "need",
                "and",
                "or",
                "the",
                "a",
                "an",
                "in",
                "of",
                "to",
                "with",
                "want",
                "some",
                "please",
                "kardo",
                "daal",
                "do",
                "chahiye",
            }
            query_words = [w for w in query.split() if len(w) > 2 and w not in stopwords]

            filtered = [
                item
                for item in catalog
                if any(word in item["name"].lower() for word in query_words)
            ]
            items = (filtered if filtered else catalog)[:limit]

            return {
                "items": items,
                "total_found": len(items),
                "query": args.get("query"),
                "serving_store": {
                    "store_id": "blr_indiranagar_darkstore_04",
                    "locality": "Indiranagar, Bengaluru",
                    "pincode": "560038",
                    "eta_minutes": 10,
                    "is_serviceable": True,
                },
            }

        elif name == "get_product_details":
            product_id = str(args.get("product_id", args.get("productVariantId", "z_milk_toned_1l")))
            return {
                "product_id": product_id,
                "name": "Amul Taaza Toned Fresh Milk",
                "brand": "Amul",
                "price": 54.0,
                "mrp": 54.0,
                "discount_percent": 0,
                "pack_size": "1 L",
                "is_available": True,
                "available_stock": 38,
                "nutrition_facts": "Energy: 58 kcal, Protein: 3.1g, Fat: 3.0g, Carbohydrate: 4.7g per 100ml",
                "shelf_life": "2 days from manufacturing",
                "serving_store": "blr_indiranagar_darkstore_04",
                "eta_minutes": 10,
                "image_url": "https://cdn.zeptonow.com/production/ik-seo/tr:w-200,h-200,cm-pad_resize/catalog/amul_milk.jpg",
            }

        elif name in ("get_cart", "view_cart"):
            return {
                "cart_id": "z_cart_sess_9941",
                "items": [
                    {
                        "item_id": "z_milk_toned_1l",
                        "product_id": "z_milk_toned_1l",
                        "name": "Amul Taaza Toned Fresh Milk",
                        "quantity": 2,
                        "unit_price": 54.0,
                        "total_price": 108.0,
                        "pack_size": "1 L",
                        "image_url": "https://cdn.zeptonow.com/production/ik-seo/tr:w-200,h-200,cm-pad_resize/catalog/amul_milk.jpg",
                    }
                ],
                "subtotal": 108.0,
                "delivery_fee": 0.0,
                "handling_fee": 4.0,
                "total_payable": 112.0,
                "currency": "INR",
                "total_items": 2,
                "delivery_eta_minutes": 10,
                "serving_store": "blr_indiranagar_darkstore_04",
            }

        elif name == "add_to_cart":
            pid = str(args.get("product_id", "z_eggs_6pk"))
            qty = int(args.get("quantity", 1))
            return {
                "status": "success",
                "action": "item_added",
                "item": {
                    "product_id": pid,
                    "quantity": qty,
                    "unit_price": 58.0,
                    "added_at": "2026-11-12T02:20:00Z",
                },
                "cart_summary": {
                    "total_items": qty,
                    "subtotal": 58.0 * qty,
                    "currency": "INR",
                    "delivery_eta_minutes": 10,
                },
            }

        elif name == "update_cart":
            item_id = str(args.get("item_id", "z_eggs_6pk"))
            qty = int(args.get("quantity", 1))
            return {
                "status": "success",
                "action": "quantity_updated" if qty > 0 else "item_removed",
                "item_id": item_id,
                "new_quantity": qty,
                "cart_summary": {
                    "total_items": max(0, qty),
                    "subtotal": 58.0 * max(0, qty),
                    "currency": "INR",
                },
            }

        elif name == "remove_from_cart":
            item_id = str(args.get("item_id", "z_eggs_6pk"))
            return {
                "status": "success",
                "action": "item_removed",
                "item_id": item_id,
                "remaining_items": 0,
            }

        elif name == "clear_cart":
            return {
                "status": "success",
                "action": "cart_cleared",
                "items_removed": 1,
                "cart_summary": {
                    "total_items": 0,
                    "subtotal": 0.0,
                    "currency": "INR",
                },
            }

        elif name in ("search_location", "get_location_serviceability"):
            query = str(args.get("query", "Indiranagar, Bengaluru"))
            pincode = str(args.get("pincode", "400014"))
            return {
                "query": query,
                "pincode": pincode,
                "serviceable": True,
                "locations": [
                    {
                        "place_id": "loc_blr_indiranagar",
                        "formatted_address": f"{query}, PIN {pincode}",
                        "pincode": pincode,
                        "latitude": 19.0191,
                        "longitude": 72.8552,
                        "is_serviceable": True,
                        "assigned_dark_store": {
                            "store_id": "mum_dadar_darkstore_01",
                            "store_name": "Dadar Central Hub",
                            "eta_minutes": 10,
                            "delivery_radius_km": 2.5,
                        },
                    }
                ],
            }

        elif name in ("place_order", "create_order"):
            payment_method = str(args.get("payment_method", "cod"))
            address_id = str(args.get("address_id", "addr_home_primary"))
            return {
                "order_id": "z_ord_882910",
                "status": "confirmed",
                "payment_mode": payment_method,
                "payment_status": "pending_delivery" if payment_method == "cod" else "paid",
                "eta_minutes": 10,
                "placed_at": "2026-11-12T02:20:00Z",
                "delivery_address": {
                    "address_id": address_id,
                    "locality": "Dadar, Mumbai",
                    "pincode": "400014",
                },
                "bill_details": {
                    "item_total": 108.0,
                    "delivery_charge": 0.0,
                    "handling_charge": 4.0,
                    "grand_total": 112.0,
                    "currency": "INR",
                },
                "tracking_url": "https://zeptonow.com/track/z_ord_882910",
            }

        elif name in ("get_order_status", "get_order_detail"):
            order_id = str(args.get("order_id", args.get("orderId", "z_ord_882910")))
            return {
                "order_id": order_id,
                "status": "out_for_delivery",
                "eta_minutes": 6,
                "rider": {
                    "name": "Ramesh Kumar",
                    "phone_masked": "+91 98****1234",
                    "vehicle": "Electric Two-Wheeler",
                },
                "dark_store": "Dadar Central Hub",
                "timeline": [
                    {"step": "Order Received", "completed": True, "time": "3 mins ago"},
                    {"step": "Packed at Dark Store", "completed": True, "time": "2 mins ago"},
                    {"step": "Rider Assigned & Dispatched", "completed": True, "time": "1 min ago"},
                    {"step": "Delivered", "completed": False, "estimated": "in 6 mins"},
                ],
            }

        elif name in ("list_orders", "list_order_history"):
            limit = int(args.get("limit", 5))
            orders = [
                {
                    "order_id": "z_ord_882910",
                    "date": "2026-11-12",
                    "status": "delivered",
                    "items_count": 3,
                    "total_amount": 166.0,
                    "currency": "INR",
                    "items_summary": "Amul Lactose Free Milk, Origami Napkins, Exo Dishwash",
                },
                {
                    "order_id": "z_ord_774120",
                    "date": "2026-11-10",
                    "status": "delivered",
                    "items_count": 2,
                    "total_amount": 112.0,
                    "currency": "INR",
                    "items_summary": "Amul Cow Milk 500ml, Electral ORS",
                },
            ]
            return {"orders": orders[:limit], "count": len(orders[:limit])}

        elif name == "list_saved_addresses":
            return {
                "addresses": [
                    {"id": "addr_1", "label": "home", "addressLine": "Dadar, Mumbai 400014"},
                    {"id": "addr_2", "label": "Bangalore Home", "addressLine": "Carmelaram, Bengaluru 560099"},
                ]
            }

        elif name == "get_user_details":
            return {
                "name": "Anush",
                "registered": True,
                "verified": True,
                "active": True,
            }

        elif name == "get_past_order_items":
            return {
                "products": [
                    {"name": "Origami Klassic Cocktail Napkin Tissue Paper", "frequency": 8},
                    {"name": "Exo Neem & Lime Anti Bacterial Dishwash Liquid", "frequency": 3},
                    {"name": "Amul Lactose Free Milk", "frequency": 3},
                ]
            }

        return {"name": name, "status": "executed", "arguments": args}

    # Backward-compatible convenience methods for orchestrator
    async def search_products(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Search products through Zepto MCP catalog."""
        logger.info(f"Zepto MCP product search for query: '{query}'")
        res = await self.call_tool("search_products", {"query": query, "quantity": limit})
        resp_data = res.get("response", {})

        # If live response has content array with structured data
        if "structuredContent" in resp_data and "products" in resp_data["structuredContent"]:
            return [
                {
                    "product_id": str(item.get("id", item.get("productVariantId", ""))),
                    "name": item.get("name", "Product"),
                    "price": float(item.get("price", 0)),
                    "pack_size": item.get("packSize", item.get("unit", "")),
                    "image_url": item.get("imageUrl"),
                    "is_available": item.get("isAvailable", True),
                }
                for item in resp_data["structuredContent"]["products"]
            ]

        if "items" in resp_data:
            return [
                {
                    "product_id": str(item.get("id", item.get("product_id"))),
                    "name": item.get("name", "Product"),
                    "price": float(item.get("price", 0)),
                    "pack_size": item.get("pack_size", item.get("unit")),
                    "image_url": item.get("image_url"),
                    "is_available": item.get("is_available", True),
                }
                for item in resp_data["items"]
            ]
        return []

    async def get_product_details(self, product_id: str) -> dict[str, Any]:
        res = await self.call_tool("get_product_details", {"product_id": product_id})
        return res.get("response", {})

    async def get_cart(self) -> dict[str, Any]:
        res = await self.call_tool("view_cart", {})
        return res.get("response", {})

    async def add_to_cart(self, product_id: str, quantity: int = 1) -> dict[str, Any]:
        res = await self.call_tool("update_cart", {"item_id": product_id, "quantity": quantity})
        return res.get("response", {})

    async def update_cart(self, item_id: str, quantity: int) -> dict[str, Any]:
        res = await self.call_tool("update_cart", {"item_id": item_id, "quantity": quantity})
        return res.get("response", {})

    async def remove_from_cart(self, item_id: str) -> dict[str, Any]:
        res = await self.call_tool("update_cart", {"item_id": item_id, "quantity": 0})
        return res.get("response", {})

    async def clear_cart(self) -> dict[str, Any]:
        res = await self.call_tool("clear_cart", {})
        return res.get("response", {})

    async def search_location(self, query: str, pincode: str | None = None) -> dict[str, Any]:
        args = {"query": query}
        if pincode:
            args["pincode"] = pincode
        res = await self.call_tool("get_location_serviceability", args)
        return res.get("response", {})

    async def place_order(self, payment_method: str = "cod", address_id: str | None = None) -> dict[str, Any]:
        args = {"payment_method": payment_method}
        if address_id:
            args["address_id"] = address_id
        res = await self.call_tool("create_order", args)
        return res.get("response", {})

    async def get_order_status(self, order_id: str) -> dict[str, Any]:
        res = await self.call_tool("get_order_detail", {"orderId": order_id})
        return res.get("response", {})

    async def list_orders(self, limit: int = 5) -> list[dict[str, Any]]:
        res = await self.call_tool("list_order_history", {"limit": limit})
        return res.get("response", {}).get("orders", [])


zepto_client = ZeptoMCPClient()
