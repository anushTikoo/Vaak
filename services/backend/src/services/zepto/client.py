import json
import sys
from pathlib import Path

from src.core.config import settings
from src.core.logging import logger

_TOKEN_CACHE_FILE = Path(".zepto_token.json")


class ZeptoMCPClient:
    """Client for Zepto Official MCP Server (mcp.zepto.co.in/mcp)."""

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

    async def search_products(self, query: str, limit: int = 5) -> list[dict]:
        """Search products through Zepto MCP catalog."""
        logger.info(f"Zepto MCP product search for query: '{query}'")

        if self.is_authenticated:
            try:
                import httpx

                async with httpx.AsyncClient(timeout=10.0) as http_client:
                    headers = {
                        "Authorization": f"Bearer {self.access_token}",
                        "Content-Type": "application/json",
                    }
                    payload = {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {
                            "name": "search_products",
                            "arguments": {"query": query, "limit": limit},
                        },
                    }
                    resp = await http_client.post(self.endpoint, headers=headers, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        if "result" in data and "items" in data["result"]:
                            return [
                                {
                                    "product_id": str(item.get("id", item.get("product_id"))),
                                    "name": item.get("name", "Product"),
                                    "price": float(item.get("price", 0)),
                                    "pack_size": item.get("pack_size", item.get("unit")),
                                    "image_url": item.get("image_url"),
                                    "is_available": item.get("is_available", True),
                                }
                                for item in data["result"]["items"]
                            ]
            except Exception as e:
                logger.warning(f"Live Zepto MCP search failed, using default catalog: {e}")

        # In foundation skeleton or unauthenticated fallback, return default catalog data
        return [
            {
                "product_id": "z_milk_toned_1l",
                "name": "Amul Taaza Toned Fresh Milk",
                "price": 54.0,
                "pack_size": "1 L",
                "is_available": True,
                "image_url": "https://cdn.zeptonow.com/production/ik-seo/tr:w-200,h-200,cm-pad_resize/catalog/amul_milk.jpg",
            },
            {
                "product_id": "z_eggs_6pk",
                "name": "Eggoz Farm Fresh White Eggs - Pack of 6",
                "price": 58.0,
                "pack_size": "6 pcs",
                "is_available": True,
                "image_url": "https://cdn.zeptonow.com/production/ik-seo/tr:w-200,h-200,cm-pad_resize/catalog/eggoz_6.jpg",
            },
        ]


zepto_client = ZeptoMCPClient()
