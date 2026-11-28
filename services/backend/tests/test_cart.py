from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_cart_starts_empty_and_reports_authoritative_totals(client):
    response = await client.get("/api/v1/cart")

    assert response.status_code == 200
    assert response.json() == {
        "items": [],
        "currency": "INR",
        "subtotal": 0,
        "total_items": 0,
    }


@pytest.mark.asyncio
async def test_cart_add_update_and_remove_lifecycle(client):
    added_response = await client.post(
        "/api/v1/cart/items",
        json={
            "product_id": "z_test_milk",
            "name": "Amul Milk 1L",
            "quantity": 2,
            "unit_price": 54.25,
            "pack_size": "1 L",
        },
    )

    assert added_response.status_code == 201
    cart = added_response.json()
    assert cart["currency"] == "INR"
    assert cart["subtotal"] == 108.5
    assert cart["total_items"] == 2
    assert len(cart["items"]) == 1
    item = cart["items"][0]
    assert item["product_id"] == "z_test_milk"
    assert item["quantity"] == 2
    assert item["unit_price"] == 54.25
    assert item["total_price"] == 108.5

    item_id = item["id"]
    updated_response = await client.patch(f"/api/v1/cart/items/{item_id}", json={"quantity": 3})

    assert updated_response.status_code == 200
    updated_cart = updated_response.json()
    assert updated_cart["items"][0]["quantity"] == 3
    assert updated_cart["subtotal"] == 162.75
    assert updated_cart["total_items"] == 3

    removed_response = await client.delete(f"/api/v1/cart/items/{item_id}")

    assert removed_response.status_code == 200
    assert removed_response.json()["items"] == []
    assert removed_response.json()["subtotal"] == 0
    assert removed_response.json()["total_items"] == 0


@pytest.mark.asyncio
async def test_adding_existing_product_increases_quantity(client):
    first = {
        "product_id": "z_test_eggs",
        "name": "Farm Eggs",
        "quantity": 1,
        "unit_price": 58,
    }
    await client.post("/api/v1/cart/items", json=first)
    response = await client.post("/api/v1/cart/items", json={**first, "quantity": 2})

    assert response.status_code == 201
    cart = response.json()
    assert len(cart["items"]) == 1
    assert cart["items"][0]["quantity"] == 3
    assert cart["subtotal"] == 174
    assert cart["total_items"] == 3


@pytest.mark.asyncio
async def test_setting_quantity_to_zero_removes_item(client):
    added = await client.post(
        "/api/v1/cart/items",
        json={"product_id": "z_test_bread", "name": "Bread", "unit_price": 40},
    )
    item_id = added.json()["items"][0]["id"]

    response = await client.patch(f"/api/v1/cart/items/{item_id}", json={"quantity": 0})

    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["subtotal"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"product_id": "p", "name": "Item", "quantity": 0, "unit_price": 10},
        {"product_id": "p", "name": "Item", "quantity": -1, "unit_price": 10},
        {"product_id": "p", "name": "Item", "quantity": 1, "unit_price": -0.01},
        {"product_id": "p", "name": "Item", "quantity": 1},
    ],
)
async def test_add_item_rejects_invalid_quantity_or_price(client, payload):
    response = await client.post("/api/v1/cart/items", json=payload)

    assert response.status_code == 422
    assert (await client.get("/api/v1/cart")).json()["items"] == []


@pytest.mark.asyncio
async def test_update_rejects_negative_quantity_without_changing_cart(client):
    added = await client.post(
        "/api/v1/cart/items",
        json={"product_id": "z_test_rice", "name": "Rice", "unit_price": 80},
    )
    item_id = added.json()["items"][0]["id"]

    response = await client.patch(f"/api/v1/cart/items/{item_id}", json={"quantity": -1})

    assert response.status_code == 422
    current_cart = (await client.get("/api/v1/cart")).json()
    assert current_cart["items"][0]["quantity"] == 1
    assert current_cart["subtotal"] == 80


@pytest.mark.asyncio
async def test_cart_mutations_return_not_found_for_unknown_item(client):
    unknown_id = uuid4()

    update_response = await client.patch(f"/api/v1/cart/items/{unknown_id}", json={"quantity": 2})
    delete_response = await client.delete(f"/api/v1/cart/items/{unknown_id}")

    assert update_response.status_code == 404
    assert update_response.json()["detail"] == "Cart item not found"
    assert delete_response.status_code == 404
    assert delete_response.json()["detail"] == "Cart item not found"


@pytest.mark.asyncio
async def test_cart_rejects_malformed_item_id(client):
    response = await client.delete("/api/v1/cart/items/not-a-uuid")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_cart_checkout_preview_and_confirmation(client):
    # Add an item to the cart
    await client.post(
        "/api/v1/cart/items",
        json={"product_id": "z_test_apple", "name": "Kashmir Apple", "unit_price": 120.0, "quantity": 1},
    )

    # Preview checkout
    preview_res = await client.post("/api/v1/cart/checkout", json={"confirm_order": False})
    assert preview_res.status_code == 200
    preview_data = preview_res.json()
    assert preview_data["is_preview"] is True
    assert preview_data["requires_confirmation"] is True
    assert preview_data["status"] == "preview"
    assert preview_data["subtotal"] == 120.0
    assert preview_data["total_items"] == 1

    # Cart should still retain item after preview
    cart_res = await client.get("/api/v1/cart")
    assert len(cart_res.json()["items"]) == 1

    # Explicitly confirm checkout
    confirm_res = await client.post("/api/v1/cart/checkout", json={"confirm_order": True})
    assert confirm_res.status_code == 200
    confirm_data = confirm_res.json()
    assert confirm_data["is_preview"] is False
    assert confirm_data["requires_confirmation"] is False
    assert confirm_data["status"] == "confirmed"
    assert confirm_data["order_id"] is not None

    # Cart should be cleared after confirmed order
    empty_cart = await client.get("/api/v1/cart")
    assert empty_cart.json()["items"] == []
    assert empty_cart.json()["total_items"] == 0


@pytest.mark.asyncio
async def test_zepto_cart_parsing_and_caching(client, monkeypatch):
    from unittest.mock import AsyncMock

    from src.api.routes.cart import invalidate_cart_cache
    from src.services.zepto.client import zepto_client

    invalidate_cart_cache()

    mock_view_cart = AsyncMock(
        return_value={
            "status": "success",
            "response": {
                "structuredContent": {
                    "items": [
                        {
                            "id": "23037033-b0ab-4109-82b6-30f3a2a2cf84",
                            "productVariantId": "23037033-b0ab-4109-82b6-30f3a2a2cf84",
                            "name": "Amul Lactose Free Milk",
                            "price": 2600,  # 2600 paise -> ₹26.00
                            "quantity": 2,
                            "packSize": "1 L",
                        }
                    ],
                    "totalItems": 2,
                    "isEmpty": False,
                }
            },
        }
    )

    monkeypatch.setattr(zepto_client, "access_token", "mock_test_token")
    monkeypatch.setattr(zepto_client, "call_tool", mock_view_cart)

    # First fetch: should invoke MCP and populate cache
    res1 = await client.get("/api/v1/cart")
    assert res1.status_code == 200
    data1 = res1.json()
    assert len(data1["items"]) == 1
    assert data1["items"][0]["unit_price"] == 26.0
    assert data1["items"][0]["quantity"] == 2
    assert data1["subtotal"] == 52.0
    assert mock_view_cart.call_count == 1

    # Second fetch: should hit TTL cache and NOT call MCP again
    res2 = await client.get("/api/v1/cart")
    assert res2.status_code == 200
    assert mock_view_cart.call_count == 1

    # Third fetch with ?refresh=true: should bypass cache and call MCP
    res3 = await client.get("/api/v1/cart?refresh=true")
    assert res3.status_code == 200
    assert mock_view_cart.call_count == 2
