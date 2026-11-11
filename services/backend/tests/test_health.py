import pytest


@pytest.mark.asyncio
async def test_root_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "vak-backend"


@pytest.mark.asyncio
async def test_api_v1_health(client):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["version"] == "v1"
    assert "integrations" in data
