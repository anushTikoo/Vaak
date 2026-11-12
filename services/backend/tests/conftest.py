import pytest
from httpx import ASGITransport, AsyncClient

from src.api.routes import cart as cart_routes
from src.main import app


@pytest.fixture(autouse=True)
def prevent_external_api_token_consumption(monkeypatch):
    """Ensure automated tests never consume live Sarvam AI API tokens or cloud credits."""
    from src.services.sarvam.client import sarvam_client
    from src.services.zepto.client import zepto_client

    monkeypatch.setattr(sarvam_client, "api_key", "mock_dev_key")
    monkeypatch.setattr(zepto_client, "access_token", None)
    monkeypatch.setattr(zepto_client, "refresh_token", None)


@pytest.fixture(autouse=True)
def reset_development_cart():
    """Keep tests independent from the process-wide development cart."""
    cart_routes._DEVELOPMENT_CART.items.clear()
    yield
    cart_routes._DEVELOPMENT_CART.items.clear()


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
