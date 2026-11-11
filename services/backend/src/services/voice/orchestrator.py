import re
from uuid import UUID

from src.core.logging import logger
from src.schemas.chat import ChatMessageResponse, ProductCard
from src.services.zepto.client import zepto_client


class VoiceOrchestrator:
    """Central conversational orchestrator bridging STT, Intent/LLM, and Zepto Commerce."""

    async def process_user_intent(
        self, user_message: str, session_id: UUID | None = None, language: str = "auto"
    ) -> ChatMessageResponse:
        logger.info(f"Processing conversational intent for message: '{user_message}', language='{language}'")

        # Detect Hindi vs English
        is_hindi = (
            (language and (language.startswith("hi") or language == "hi-IN"))
            or bool(re.search(r"[\u0900-\u097F]", user_message))
            or bool(
                re.search(
                    r"\b(doodh|dudh|chahiye|kardo|bhej do|daal do|namaste|"
                    r"aate|paani|sabzi|anda|ande|chawal|cheeni|shakkar|haan|theek)\b",
                    user_message,
                    re.IGNORECASE,
                )
            )
        )

        detected_lang = "hi-IN" if is_hindi else "en-IN"

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

        if is_hindi:
            reply = (
                f"मुझे Zepto पर '{user_message}' के लिए {len(cards)} सामान मिले हैं। "
                "क्या मैं इन्हें आपके कार्ट में जोड़ दूँ?"
            )
        else:
            reply = (
                f"I found {len(cards)} matching items on Zepto for '{user_message}'. "
                "Would you like me to add them to your cart?"
            )

        return ChatMessageResponse(
            session_id=session_id or UUID(int=0),
            reply_text=reply,
            suggested_products=cards,
            action_type="clarification_needed",
            detected_language=detected_lang,
        )


voice_orchestrator = VoiceOrchestrator()
