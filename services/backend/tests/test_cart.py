import pytest


@pytest.mark.asyncio
async def test_cart_lifecycle(client):
    # 1. Fetch initial cart
    response = await client.get("/api/v1/cart")
    assert response.status_code == 200
    cart_data = response.json()
    assert "items" in cart_data
    assert "subtotal" in cart_data

    # 2. Add an item
    new_item = {
        "product_id": "z_test_milk",
        "name": "Amul Milk 1L",
        "quantity": 2,
        "unit_price": 54.0,
        "pack_size": "1 L",
    }
    add_response = await client.post("/api/v1/cart/items", json=new_item)
    assert add_response.status_code == 201
    updated_cart = add_response.json()
    assert len(updated_cart["items"]) >= 1
    assert any(i["product_id"] == "z_test_milk" for i in updated_cart["items"])

    # 3. Find item ID
    added = next(i for i in updated_cart["items"] if i["product_id"] == "z_test_milk")
    item_id = added["id"]

    # 4. Update quantity
    patch_response = await client.patch(f"/api/v1/cart/items/{item_id}", json={"quantity": 3})
    assert patch_response.status_code == 200
    patched_cart = patch_response.json()
    item_after_patch = next(i for i in patched_cart["items"] if i["id"] == item_id)
    assert item_after_patch["quantity"] == 3

    # 5. Delete item
    del_response = await client.delete(f"/api/v1/cart/items/{item_id}")
    assert del_response.status_code == 200
    cart_after_del = del_response.json()
    assert not any(i["id"] == item_id for i in cart_after_del["items"])
