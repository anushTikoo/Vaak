from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ChatMessageRequest(BaseModel):
    session_id: UUID | None = None
    message: str = Field(..., min_length=1, description="User prompt or transcribed speech")
    language: str = "auto"


class ProductCard(BaseModel):
    product_id: str
    name: str
    price: float
    pack_size: str | None = None
    image_url: str | None = None
    is_available: bool = True


class ChatMessageResponse(BaseModel):
    session_id: UUID = Field(default_factory=uuid4)
    reply_text: str
    suggested_products: list[ProductCard] = Field(default_factory=list)
    action_type: str = (
        "none"  # "none", "cart_updated", "clarification_needed", "order_confirmation_requested"
    )
