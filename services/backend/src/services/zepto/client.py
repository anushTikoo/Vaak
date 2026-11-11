import contextlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from src.core.config import settings
from src.core.logging import logger

_TOKEN_CACHE_FILE = Path(".zepto_token.json")

# Universal Commerce Protocol (UCP) / Zepto MCP Tool Definitions
ZEPTO_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "search_products",
        "category": "Catalog & Search",
        "description": "Search Zepto dark store inventory for products, groceries, and staples in real-time.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search keyword (e.g. 'Amul milk', 'Bread', 'Eggs')"},
                "limit": {"type": "integer", "description": "Maximum number of items to return", "default": 5},
            },
            "required": ["query"],
        },
        "default_input": {"query": "Amul Taaza Milk 1L", "limit": 4},
    },
    {
        "name": "get_product_details",
        "category": "Catalog & Search",
        "description": "Fetch live SKU metadata including real-time stock, pricing, and pack size.",
        "parameters": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string", "description": "Unique product SKU identifier"},
            },
            "required": ["product_id"],
        },
        "default_input": {"product_id": "z_milk_toned_1l"},
    },
    {
        "name": "get_cart",
        "category": "Cart Management",
        "description": "Retrieve current Zepto shopping cart with active item breakdown, discounts, and total.",
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
        "description": "Modify the quantity of an existing item in the Zepto cart. Setting quantity to 0 removes it.",
        "parameters": {
            "type": "object",
            "properties": {
                "item_id": {"type": "string", "description": "Cart item ID or product SKU"},
                "quantity": {"type": "integer", "description": "New unit count", "default": 1},
            },
            "required": ["item_id", "quantity"],
        },
        "default_input": {"item_id": "z_eggs_6pk", "quantity": 3},
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
                "pincode": {"type": "string", "description": "6-digit Indian PIN code", "default": "560038"},
            },
            "required": ["query"],
        },
        "default_input": {"query": "Indiranagar, Bengaluru", "pincode": "560038"},
    },
    {
        "name": "place_order",
        "category": "Orders & Checkout",
        "description": "Submit and confirm grocery order with the serving Zepto micro-fulfillment center.",
        "parameters": {
            "type": "object",
            "properties": {
                "payment_method": {
                    "type": "string",
                    "description": "Payment mode: 'cod', 'upi', 'card'",
                    "default": "cod",
                },
                "address_id": {
                    "type": "string",
                    "description": "Saved delivery address ID",
                    "default": "addr_home_primary",
                },
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
        "description": "Retrieve recent order history with delivery timestamps, item summaries, and total spent.",
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

    Implements the Universal Commerce Protocol (UCP) over Model Context Protocol JSON-RPC 2.0.
    Supports live authenticated upstream calls as well as rich local development sandbox responses.
    """

    def __init__(self):
        self.endpoint = settings.ZEPTO_MCP_ENDPOINT
        self.client_id = settings.ZEPTO_CLIENT_ID
        self.access_token: str | None = None
        self.refresh_token: str | None = None

        # Only load persisted token in live server runtime, not during pytest test runs
        if "pytest" not in sys.modules and _TOKEN_CACHE_FILE.exists():
            try:
                data = json.loads(_TOKEN_CACHE_FILE.read_text(encoding="utf-8"))
                self.access_token = data.get("access_token")
                self.refresh_token = data.get("refresh_token")
                if self.access_token:
                    logger.info("Restored persisted Zepto MCP session from token cache")
            except Exception as e:
                logger.warning(f"Failed to read token cache: {e}")

    @property
    def is_authenticated(self) -> bool:
        return bool(self.access_token)

    def set_tokens(self, access_token: str, refresh_token: str | None = None):
        self.access_token = access_token
        self.refresh_token = refresh_token
        logger.info("Zepto MCP access token successfully updated")
        if "pytest" not in sys.modules:
            try:
                _TOKEN_CACHE_FILE.write_text(
                    json.dumps({"access_token": access_token, "refresh_token": refresh_token}),
                    encoding="utf-8",
                )
            except Exception as e:
                logger.warning(f"Failed to persist token cache: {e}")

    def clear_tokens(self):
        self.access_token = None
        self.refresh_token = None
        if _TOKEN_CACHE_FILE.exists():
            with contextlib.suppress(Exception):
                _TOKEN_CACHE_FILE.unlink()
        logger.info("Zepto MCP tokens cleared")

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """Return the schema metadata for all Zepto MCP tools."""
        return ZEPTO_TOOL_DEFINITIONS

    async def ping_upstream(self) -> dict[str, Any]:
        """Ping the live Zepto MCP server endpoint to verify network reachability."""
        start_time = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=8.0) as http_client:
                resp = await http_client.post(
                    self.endpoint,
                    headers={"Content-Type": "application/json"},
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
        """Execute a tool call using standard JSON-RPC 2.0 protocol against Zepto MCP.

        Args:
            name: The MCP tool name (e.g. 'search_products', 'add_to_cart').
            arguments: Dictionary of input arguments for the tool.
            force_upstream: If True, executes the call to the live Zepto MCP server even
                if unauthenticated (allowing observation of upstream headers and 401s).

        Returns:
            Structured test result containing tool_name, input_arguments, raw_rpc_request,
            status, source, latency, and response payload.
        """
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
            try:
                headers = {"Content-Type": "application/json"}
                if self.access_token:
                    headers["Authorization"] = f"Bearer {self.access_token}"

                async with httpx.AsyncClient(timeout=10.0) as http_client:
                    resp = await http_client.post(self.endpoint, headers=headers, json=payload)
                    elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

                    if resp.status_code == 200:
                        data = resp.json()
                        return {
                            "tool_name": name,
                            "input_arguments": args,
                            "raw_rpc_request": payload,
                            "status": "success",
                            "status_code": 200,
                            "source": "live_mcp",
                            "is_authenticated": self.is_authenticated,
                            "endpoint": self.endpoint,
                            "execution_time_ms": elapsed_ms,
                            "response": data.get("result", data),
                        }
                    else:
                        try:
                            err_body = resp.json()
                        except Exception:
                            err_body = {"raw": resp.text}

                        # If unauthenticated upstream call failed with 401 and force_upstream was not set,
                        # fall through to sandbox response below
                        if force_upstream or self.is_authenticated:
                            return {
                                "tool_name": name,
                                "input_arguments": args,
                                "raw_rpc_request": payload,
                                "status": "error",
                                "status_code": resp.status_code,
                                "source": "live_mcp",
                                "is_authenticated": self.is_authenticated,
                                "endpoint": self.endpoint,
                                "execution_time_ms": elapsed_ms,
                                "error": err_body,
                                "note": (
                                    "Upstream Zepto MCP returned non-200. "
                                    "Authenticate your account via OAuth to access live dark store inventory."
                                    if resp.status_code == 401
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
        if name == "search_products":
            query = str(args.get("query", "groceries")).lower()
            limit = int(args.get("limit", 5))

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

            # Filter if query matches anything, otherwise return catalog
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
            product_id = str(args.get("product_id", "z_milk_toned_1l"))
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

        elif name == "get_cart":
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

        elif name == "search_location":
            query = str(args.get("query", "Indiranagar, Bengaluru"))
            pincode = str(args.get("pincode", "560038"))
            return {
                "query": query,
                "pincode": pincode,
                "serviceable": True,
                "locations": [
                    {
                        "place_id": "loc_blr_indiranagar",
                        "formatted_address": f"{query}, Bengaluru, Karnataka {pincode}",
                        "pincode": pincode,
                        "latitude": 12.9784,
                        "longitude": 77.6408,
                        "is_serviceable": True,
                        "assigned_dark_store": {
                            "store_id": "blr_indiranagar_darkstore_04",
                            "store_name": "Indiranagar Hub #4",
                            "eta_minutes": 10,
                            "delivery_radius_km": 2.5,
                        },
                    }
                ],
            }

        elif name == "place_order":
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
                    "locality": "Indiranagar, Bengaluru",
                    "pincode": "560038",
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

        elif name == "get_order_status":
            order_id = str(args.get("order_id", "z_ord_882910"))
            return {
                "order_id": order_id,
                "status": "out_for_delivery",
                "eta_minutes": 6,
                "rider": {
                    "name": "Ramesh Kumar",
                    "phone_masked": "+91 98****1234",
                    "vehicle": "Electric Two-Wheeler",
                },
                "dark_store": "Indiranagar Hub #4",
                "timeline": [
                    {"step": "Order Received", "completed": True, "time": "3 mins ago"},
                    {"step": "Packed at Dark Store", "completed": True, "time": "2 mins ago"},
                    {"step": "Rider Assigned & Dispatched", "completed": True, "time": "1 min ago"},
                    {"step": "Delivered", "completed": False, "estimated": "in 6 mins"},
                ],
            }

        elif name == "list_orders":
            limit = int(args.get("limit", 5))
            orders = [
                {
                    "order_id": "z_ord_882910",
                    "date": "2026-11-12",
                    "status": "delivered",
                    "items_count": 3,
                    "total_amount": 166.0,
                    "currency": "INR",
                    "items_summary": "Amul Taaza Milk 1L, Eggoz Eggs (6pk), English Oven Bread",
                },
                {
                    "order_id": "z_ord_774120",
                    "date": "2026-11-10",
                    "status": "delivered",
                    "items_count": 2,
                    "total_amount": 112.0,
                    "currency": "INR",
                    "items_summary": "Nandini GoodLife Milk, Tata Salt 1kg",
                },
            ]
            return {"orders": orders[:limit], "count": len(orders[:limit])}

        return {"name": name, "status": "executed", "arguments": args}

    # Backward-compatible convenience methods for orchestrator
    async def search_products(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Search products through Zepto MCP catalog."""
        logger.info(f"Zepto MCP product search for query: '{query}'")
        res = await self.call_tool("search_products", {"query": query, "limit": limit})
        resp_data = res.get("response", {})
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
        res = await self.call_tool("get_cart", {})
        return res.get("response", {})

    async def add_to_cart(self, product_id: str, quantity: int = 1) -> dict[str, Any]:
        res = await self.call_tool("add_to_cart", {"product_id": product_id, "quantity": quantity})
        return res.get("response", {})

    async def update_cart(self, item_id: str, quantity: int) -> dict[str, Any]:
        res = await self.call_tool("update_cart", {"item_id": item_id, "quantity": quantity})
        return res.get("response", {})

    async def remove_from_cart(self, item_id: str) -> dict[str, Any]:
        res = await self.call_tool("remove_from_cart", {"item_id": item_id})
        return res.get("response", {})

    async def clear_cart(self) -> dict[str, Any]:
        res = await self.call_tool("clear_cart", {})
        return res.get("response", {})

    async def search_location(self, query: str, pincode: str | None = None) -> dict[str, Any]:
        args = {"query": query}
        if pincode:
            args["pincode"] = pincode
        res = await self.call_tool("search_location", args)
        return res.get("response", {})

    async def place_order(self, payment_method: str = "cod", address_id: str | None = None) -> dict[str, Any]:
        args = {"payment_method": payment_method}
        if address_id:
            args["address_id"] = address_id
        res = await self.call_tool("place_order", args)
        return res.get("response", {})

    async def get_order_status(self, order_id: str) -> dict[str, Any]:
        res = await self.call_tool("get_order_status", {"order_id": order_id})
        return res.get("response", {})

    async def list_orders(self, limit: int = 5) -> list[dict[str, Any]]:
        res = await self.call_tool("list_orders", {"limit": limit})
        return res.get("response", {}).get("orders", [])


zepto_client = ZeptoMCPClient()
