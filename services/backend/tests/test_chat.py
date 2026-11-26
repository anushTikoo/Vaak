from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from src.services.zepto.client import zepto_client


@pytest.mark.asyncio
async def test_chat_searches_products_and_requires_user_confirmation(client, monkeypatch):
    session_id = uuid4()
    search = AsyncMock(
        return_value=[
            {
                "product_id": "z_milk_1l",
                "name": "Toned Milk",
                "price": 54,
                "pack_size": "1 L",
                "image_url": "https://example.test/milk.jpg",
                "is_available": True,
            }
        ]
    )
    monkeypatch.setattr(zepto_client, "search_products", search)

    response = await client.post(
        "/api/v1/chat/message",
        json={
            "session_id": str(session_id),
            "message": "Add one litre of milk",
            "language": "en-IN",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == str(session_id)
    assert data["action_type"] == "clarification_needed"
    assert "Would you like me to add them to your cart?" in data["reply_text"]
    assert data["suggested_products"] == [
        {
            "product_id": "z_milk_1l",
            "name": "Toned Milk",
            "price": 54,
            "pack_size": "1 L",
            "image_url": "https://example.test/milk.jpg",
            "is_available": True,
        }
    ]
    search.assert_awaited_once_with("Add one litre of milk")

    # Product suggestions must not silently alter the authoritative cart.
    cart = await client.get("/api/v1/cart")
    assert cart.json()["items"] == []
    assert cart.json()["subtotal"] == 0


@pytest.mark.asyncio
async def test_chat_accepts_missing_session_and_empty_search_results(client, monkeypatch):
    search = AsyncMock(return_value=[])
    monkeypatch.setattr(zepto_client, "search_products", search)

    response = await client.post("/api/v1/chat/message", json={"message": "Find oat milk"})

    assert response.status_code == 200
    data = response.json()
    UUID(data["session_id"])
    assert data["suggested_products"] == []
    assert "0 matching items" in data["reply_text"]
    assert data["action_type"] == "clarification_needed"
    search.assert_awaited_once_with("Find oat milk")


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [{}, {"message": ""}])
async def test_chat_rejects_missing_or_empty_message(client, payload):
    response = await client.post("/api/v1/chat/message", json=payload)

    assert response.status_code == 422
