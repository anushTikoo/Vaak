import pytest
from httpx import ASGITransport, AsyncClient

from src.api.routes import cart as cart_routes
from src.main import app


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
