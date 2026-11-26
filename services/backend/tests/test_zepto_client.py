import pytest

from src.services.zepto.client import ZeptoMCPClient, zepto_client


@pytest.mark.asyncio
async def test_development_catalog_results_match_product_search_contract():
    client = ZeptoMCPClient()

    products = await client.search_products("milk and eggs")

    assert products
    assert all(
        {"product_id", "name", "price", "pack_size", "image_url", "is_available"}
        <= product.keys()
        for product in products
    )
    assert all(isinstance(product["product_id"], str) for product in products)
    assert all(isinstance(product["name"], str) for product in products)
    assert all(isinstance(product["price"], (int, float)) for product in products)
    assert all(product["price"] >= 0 for product in products)
    assert all(isinstance(product["is_available"], bool) for product in products)


@pytest.mark.asyncio
async def test_chat_to_zepto_development_catalog_suggests_items_but_does_not_add_them(client):
    response = await client.post(
        "/api/v1/chat/message",
        json={"message": "I need milk and eggs", "language": "en-IN"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["action_type"] == "clarification_needed"
    assert len(data["suggested_products"]) == 2
    assert {product["product_id"] for product in data["suggested_products"]} == {
        "z_milk_toned_1l",
        "z_eggs_6pk",
    }
    assert all(product["is_available"] is True for product in data["suggested_products"])

    cart = (await client.get("/api/v1/cart")).json()
    assert cart["items"] == []
    assert cart["subtotal"] == 0


def test_zepto_client_does_not_claim_authenticated_session_without_token_support():
    assert zepto_client.is_authenticated is False
