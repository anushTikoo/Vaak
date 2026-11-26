from src.core.config import settings
from src.core.logging import logger


class ZeptoMCPClient:
    """Client for Zepto Official MCP Server (mcp.zepto.co.in/mcp)."""

    def __init__(self):
        self.endpoint = settings.ZEPTO_MCP_ENDPOINT
        self.client_id = settings.ZEPTO_CLIENT_ID
        self.client_secret = settings.ZEPTO_CLIENT_SECRET

    @property
    def is_authenticated(self) -> bool:
        # Will verify active OAuth access token
        return False

    async def search_products(self, query: str, limit: int = 5) -> list[dict]:
        """Search products through Zepto MCP catalog."""
        logger.info(f"Zepto MCP product search for query: '{query}'")
        # In foundation skeleton, return clearly marked sample catalog data
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
