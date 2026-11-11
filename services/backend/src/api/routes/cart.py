from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from src.schemas.cart import AddCartItemRequest, Cart, CartItem, UpdateCartItemRequest

router = APIRouter(prefix="/api/v1/cart", tags=["Cart"])

# In-memory session cart for development (will be backed by PostgreSQL / Hyperdrive)
_DEVELOPMENT_CART = Cart()


@router.get("", response_model=Cart)
async def get_cart():
    """Retrieve current shopping cart and total."""
    return _DEVELOPMENT_CART


@router.post("/items", response_model=Cart, status_code=status.HTTP_201_CREATED)
async def add_item_to_cart(item_in: AddCartItemRequest):
    """Add a product to the cart or increase quantity if already present."""
    for item in _DEVELOPMENT_CART.items:
        if item.product_id == item_in.product_id:
            item.quantity += item_in.quantity
            return _DEVELOPMENT_CART

    new_item = CartItem(
        product_id=item_in.product_id,
        name=item_in.name,
        quantity=item_in.quantity,
        unit_price=item_in.unit_price,
        image_url=item_in.image_url,
        pack_size=item_in.pack_size,
    )
    _DEVELOPMENT_CART.items.append(new_item)
    return _DEVELOPMENT_CART


@router.patch("/items/{item_id}", response_model=Cart)
async def update_cart_item(item_id: UUID, update_in: UpdateCartItemRequest):
    """Update quantity for a cart item. Setting quantity to 0 removes the item."""
    for i, item in enumerate(_DEVELOPMENT_CART.items):
        if item.id == item_id:
            if update_in.quantity == 0:
                _DEVELOPMENT_CART.items.pop(i)
            else:
                item.quantity = update_in.quantity
            return _DEVELOPMENT_CART

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart item not found")


@router.delete("/items/{item_id}", response_model=Cart)
async def remove_cart_item(item_id: UUID):
    """Remove a specific item from the cart."""
    for i, item in enumerate(_DEVELOPMENT_CART.items):
        if item.id == item_id:
            _DEVELOPMENT_CART.items.pop(i)
            return _DEVELOPMENT_CART

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart item not found")
