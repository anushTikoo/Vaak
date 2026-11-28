from uuid import UUID, uuid4

from pydantic import BaseModel, Field, computed_field


class CartItem(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    product_id: str = Field(..., description="External Zepto product ID")
    name: str = Field(..., description="Product name")
    quantity: int = Field(..., ge=1, description="Quantity of item")
    unit_price: float = Field(..., ge=0.0, description="Price per unit in INR")
    image_url: str | None = None
    pack_size: str | None = None

    @computed_field
    @property
    def total_price(self) -> float:
        return round(self.quantity * self.unit_price, 2)


class Cart(BaseModel):
    items: list[CartItem] = Field(default_factory=list)
    currency: str = "INR"

    @computed_field
    @property
    def subtotal(self) -> float:
        return round(sum(item.total_price for item in self.items), 2)

    @computed_field
    @property
    def total_items(self) -> int:
        return sum(item.quantity for item in self.items)


class AddCartItemRequest(BaseModel):
    product_id: str
    name: str
    quantity: int = Field(default=1, ge=1)
    unit_price: float = Field(..., ge=0.0)
    image_url: str | None = None
    pack_size: str | None = None


class UpdateCartItemRequest(BaseModel):
    quantity: int = Field(..., ge=0, description="New quantity (0 deletes item)")


class CheckoutRequest(BaseModel):
    confirm_order: bool = Field(
        default=False,
        description="Whether to execute live order placement (True) or safe preview (False)",
    )
    payment_method: str = Field(default="COD", description="Payment method: COD or UPI")
    rider_tip: int = Field(default=0, ge=0, description="Rider tip in INR")


class CheckoutItem(BaseModel):
    name: str
    price: float
    quantity: int
    product_id: str | None = None


class CheckoutResponse(BaseModel):
    is_preview: bool
    status: str
    order_id: str | None = None
    subtotal: float = 0.0
    delivery_fee: float = 0.0
    packaging_fee: float = 0.0
    to_pay: float = 0.0
    total_items: int = 0
    items: list[CheckoutItem] = Field(default_factory=list)
    delivery_address: str | None = None
    eta_minutes: int | None = None
    requires_confirmation: bool = True
    message: str = ""
