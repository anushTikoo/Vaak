import logging
import time
from typing import Any
from uuid import NAMESPACE_DNS, UUID, uuid5

from fastapi import APIRouter, HTTPException, status

from src.schemas.cart import (
    AddCartItemRequest,
    Cart,
    CartItem,
    CheckoutItem,
    CheckoutRequest,
    CheckoutResponse,
    UpdateCartItemRequest,
)
from src.services.zepto.client import zepto_client

logger = logging.getLogger("vaak")

router = APIRouter(prefix="/api/v1/cart", tags=["Cart"])

# In-memory session cart for development & testing fallback (guarantees zero test token burn)
_DEVELOPMENT_CART = Cart()

# In-memory TTL cache for Zepto MCP cart to prevent bombarding dark store upstream
_CART_CACHE: dict[str, Any] = {
    "cart": None,
    "timestamp": 0.0,
}
_CART_CACHE_TTL_SECONDS = 60.0


def invalidate_cart_cache() -> None:
    """Invalidate backend cart cache to force fresh fetch on next query."""
    _CART_CACHE["cart"] = None
    _CART_CACHE["timestamp"] = 0.0


def _parse_zepto_cart(tool_result: dict[str, Any]) -> Cart:
    """Parse Zepto MCP view_cart tool output into canonical Cart schema."""
    resp_payload = tool_result.get("response") or tool_result
    structured = resp_payload.get("structuredContent") or {}
    items_raw = structured.get("items") or resp_payload.get("items") or []

    cart_items: list[CartItem] = []
    for it in items_raw:
        pid = str(it.get("productVariantId") or it.get("id") or it.get("product_id") or "")
        name = it.get("name", "Product")
        qty = int(it.get("quantity", 1))
        raw_price = float(it.get("price") or it.get("unit_price") or 0.0)

        # Zepto MCP reports price in paise (e.g. 2600 paise -> ₹26.00)
        if "structuredContent" in resp_payload or raw_price >= 500:
            unit_price = round(raw_price / 100.0, 2)
        else:
            unit_price = round(raw_price, 2)

        try:
            item_uuid = UUID(pid)
        except Exception:
            item_uuid = uuid5(NAMESPACE_DNS, pid)

        cart_items.append(
            CartItem(
                id=item_uuid,
                product_id=pid,
                name=name,
                quantity=qty,
                unit_price=unit_price,
                image_url=it.get("imageUrl") or it.get("image_url"),
                pack_size=it.get("packSize") or it.get("pack_size"),
            )
        )
    return Cart(items=cart_items)


@router.get("", response_model=Cart)
async def get_cart(refresh: bool = False):
    """Retrieve current shopping cart and total.

    If connected to Zepto MCP, queries the live cart with 60s TTL caching.
    Pass ?refresh=true to bypass cache and query Zepto MCP directly.
    """
    if zepto_client.is_authenticated:
        now = time.time()
        if (
            not refresh
            and _CART_CACHE["cart"] is not None
            and (now - _CART_CACHE["timestamp"] < _CART_CACHE_TTL_SECONDS)
        ):
            return _CART_CACHE["cart"]

        try:
            tool_res = await zepto_client.call_tool("view_cart", {})
            cart = _parse_zepto_cart(tool_res)
            _CART_CACHE["cart"] = cart
            _CART_CACHE["timestamp"] = now
            return cart
        except Exception as e:
            logger.warning(f"Failed to fetch live Zepto cart: {e}. Falling back to cached or dev cart.")
            if _CART_CACHE["cart"] is not None:
                return _CART_CACHE["cart"]

    return _DEVELOPMENT_CART


@router.post("/items", response_model=Cart, status_code=status.HTTP_201_CREATED)
async def add_item_to_cart(item_in: AddCartItemRequest):
    """Add a product to the cart or increase quantity if already present."""
    if zepto_client.is_authenticated:
        current_cart = await get_cart(refresh=False)
        target_qty = item_in.quantity
        for existing in current_cart.items:
            if existing.product_id == item_in.product_id:
                target_qty = existing.quantity + item_in.quantity
                break

        await zepto_client.call_tool(
            "update_cart",
            {"productVariantId": item_in.product_id, "quantity": target_qty},
        )
        invalidate_cart_cache()
        return await get_cart(refresh=True)

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
    if zepto_client.is_authenticated:
        current_cart = await get_cart(refresh=False)
        matching_pid = None
        for it in current_cart.items:
            if it.id == item_id or it.product_id == str(item_id):
                matching_pid = it.product_id
                break

        if not matching_pid:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart item not found")

        await zepto_client.call_tool(
            "update_cart",
            {"productVariantId": matching_pid, "quantity": update_in.quantity},
        )
        invalidate_cart_cache()
        return await get_cart(refresh=True)

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
    if zepto_client.is_authenticated:
        current_cart = await get_cart(refresh=False)
        matching_pid = None
        for it in current_cart.items:
            if it.id == item_id or it.product_id == str(item_id):
                matching_pid = it.product_id
                break

        if not matching_pid:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart item not found")

        await zepto_client.call_tool(
            "update_cart",
            {"productVariantId": matching_pid, "quantity": 0},
        )
        invalidate_cart_cache()
        return await get_cart(refresh=True)

    for i, item in enumerate(_DEVELOPMENT_CART.items):
        if item.id == item_id:
            _DEVELOPMENT_CART.items.pop(i)
            return _DEVELOPMENT_CART

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart item not found")


@router.post("/checkout", response_model=CheckoutResponse)
async def checkout_cart(req: CheckoutRequest = CheckoutRequest()):
    """Preview or place an order via Zepto MCP create_order tool.

    Guardrail Policy:
    Spoken AI turns cannot place real orders. Live order confirmation (confirm_order=True)
    is only permitted through an explicit visual touch tap on the Checkout / Confirm button.
    """
    if zepto_client.is_authenticated:
        tool_result = await zepto_client.call_tool(
            "create_order",
            {"confirmOrder": req.confirm_order, "riderTip": req.rider_tip},
            enforce_guardrail=not req.confirm_order,
        )
        resp_payload = tool_result.get("response") or tool_result
        structured = resp_payload.get("structuredContent") or {}

        if tool_result.get("status") == "error" or resp_payload.get("isError"):
            err_msg = ""
            if "content" in resp_payload and isinstance(resp_payload["content"], list):
                err_msg = resp_payload["content"][0].get("text", "")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=err_msg or "Order could not be created with Zepto. Check deliverability.",
            )

        items_out: list[CheckoutItem] = []
        for it in structured.get("items", []):
            raw_p = float(it.get("price", 0))
            items_out.append(
                CheckoutItem(
                    name=it.get("name", "Product"),
                    price=round(raw_p / 100.0, 2) if raw_p >= 500 else round(raw_p, 2),
                    quantity=int(it.get("quantity", 1)),
                    product_id=str(it.get("productVariantId") or it.get("storeProductId") or ""),
                )
            )

        raw_to_pay = float(structured.get("toPayAmount", 0))
        to_pay_val = round(raw_to_pay / 100.0, 2) if raw_to_pay >= 500 else round(raw_to_pay, 2)
        raw_sub = float(structured.get("subTotal", 0))
        sub_val = round(raw_sub / 100.0, 2) if raw_sub >= 500 else round(raw_sub, 2)
        raw_del = float(structured.get("deliveryFee", 0))
        del_val = round(raw_del / 100.0, 2) if raw_del >= 500 else round(raw_del, 2)
        raw_pack = float(structured.get("packagingFee", 0))
        pack_val = round(raw_pack / 100.0, 2) if raw_pack >= 500 else round(raw_pack, 2)

        addr = structured.get("deliveryAddress", {})
        addr_text = addr.get("addressLine") or addr.get("label") or "Home"

        if req.confirm_order:
            invalidate_cart_cache()
            return CheckoutResponse(
                is_preview=False,
                status="confirmed",
                order_id=str(structured.get("orderId") or f"ZEP-{int(time.time())}"),
                subtotal=sub_val,
                delivery_fee=del_val,
                packaging_fee=pack_val,
                to_pay=to_pay_val,
                total_items=structured.get("totalItems", len(items_out)),
                items=items_out,
                delivery_address=addr_text,
                eta_minutes=structured.get("etaInMinutes") or 10,
                requires_confirmation=False,
                message="Your Zepto order has been placed successfully! Estimated delivery in 10 minutes.",
            )

        return CheckoutResponse(
            is_preview=True,
            status="preview",
            subtotal=sub_val,
            delivery_fee=del_val,
            packaging_fee=pack_val,
            to_pay=to_pay_val,
            total_items=structured.get("totalItems", len(items_out)),
            items=items_out,
            delivery_address=addr_text,
            eta_minutes=structured.get("etaInMinutes") or 10,
            requires_confirmation=True,
            message="Order summary ready. Tap Confirm Order to place.",
        )

    # Sandbox / Mock fallback (used during automated tests)
    items_out = [
        CheckoutItem(
            name=it.name,
            price=it.unit_price,
            quantity=it.quantity,
            product_id=it.product_id,
        )
        for it in _DEVELOPMENT_CART.items
    ]
    subtotal = _DEVELOPMENT_CART.subtotal
    total_items = _DEVELOPMENT_CART.total_items

    if req.confirm_order:
        _DEVELOPMENT_CART.items.clear()
        return CheckoutResponse(
            is_preview=False,
            status="confirmed",
            order_id=f"ZEP-TEST-{int(time.time())}",
            subtotal=subtotal,
            delivery_fee=0.0,
            packaging_fee=0.0,
            to_pay=subtotal,
            total_items=total_items,
            items=items_out,
            delivery_address="Home (Test)",
            eta_minutes=10,
            requires_confirmation=False,
            message="Your Zepto order has been placed successfully! Estimated delivery in 10 minutes.",
        )

    return CheckoutResponse(
        is_preview=True,
        status="preview",
        subtotal=subtotal,
        delivery_fee=0.0,
        packaging_fee=0.0,
        to_pay=subtotal,
        total_items=total_items,
        items=items_out,
        delivery_address="Home (Test)",
        eta_minutes=10,
        requires_confirmation=True,
        message="Order summary ready. Tap Confirm Order to place.",
    )
