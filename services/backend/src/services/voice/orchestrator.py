from uuid import UUID

from src.core.logging import logger
from src.schemas.chat import ChatMessageResponse, ProductCard
from src.services.zepto.client import zepto_client


class VoiceOrchestrator:
    """Central conversational orchestrator bridging STT, Intent/LLM, and Zepto Commerce."""

    async def process_user_intent(
        self, user_message: str, session_id: UUID | None = None
    ) -> ChatMessageResponse:
        logger.info(f"Processing conversational intent for message: '{user_message}'")

        # Query Zepto catalog for matching products
        products = await zepto_client.search_products(user_message)
        cards = [
            ProductCard(
                product_id=p["product_id"],
                name=p["name"],
                price=p["price"],
                pack_size=p["pack_size"],
                image_url=p["image_url"],
                is_available=p["is_available"],
            )
            for p in products
        ]

        reply = (
            f"I found {len(cards)} matching items on Zepto for '{user_message}'. "
            "Would you like me to add them to your cart?"
        )

        return ChatMessageResponse(
            session_id=session_id or UUID(int=0),
            reply_text=reply,
            suggested_products=cards,
            action_type="clarification_needed",
        )


voice_orchestrator = VoiceOrchestrator()
