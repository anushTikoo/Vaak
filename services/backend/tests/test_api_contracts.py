from uuid import UUID

import pytest


@pytest.mark.asyncio
async def test_profile_returns_identity_and_authentication_state(client):
    response = await client.get("/api/v1/me")

    assert response.status_code == 200
    profile = response.json()
    UUID(profile["id"])
    assert profile["phone_number"] == "+91 98765 43210"
    assert profile["is_zepto_authenticated"] is False
    assert profile["preferred_language"] == "en-IN"


@pytest.mark.asyncio
async def test_orders_endpoint_returns_empty_history(client):
    response = await client.get("/api/v1/orders")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_health_reports_service_and_integration_status(client):
    root_response = await client.get("/health")
    api_response = await client.get("/api/v1/health")

    assert root_response.status_code == 200
    assert root_response.json()["status"] == "healthy"
    assert root_response.json()["service"] == "vaak-backend"
    assert root_response.json()["environment"]

    assert api_response.status_code == 200
    data = api_response.json()
    assert data["status"] == "healthy"
    assert data["version"] == "v1"
    assert set(data["integrations"]) == {"sarvam", "zepto_mcp", "database"}
    assert data["integrations"]["sarvam"] in {"configured", "development_mock"}
    assert data["integrations"]["zepto_mcp"] == "ready"
    assert data["integrations"]["database"] in {"configured", "unconfigured"}
