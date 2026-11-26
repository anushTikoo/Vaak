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
