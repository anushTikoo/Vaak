from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from src.schemas.cart import CartItem


class OrderResponse(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    zepto_order_id: str | None = None
    status: str = "pending"  # "pending", "confirmed", "dispatched", "delivered", "failed"
    total_amount: float
    items: list[CartItem]
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
