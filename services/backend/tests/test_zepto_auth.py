from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from src.api.routes import auth as auth_routes
from src.services.zepto.client import zepto_client


@pytest.fixture(autouse=True)
def reset_zepto_client():
    """Ensure zepto_client is in clean state before and after each test."""
    zepto_client.access_token = None
    zepto_client.refresh_token = None
    auth_routes._ACTIVE_PKCE_SESSIONS.clear()
    yield
    zepto_client.access_token = None
    zepto_client.refresh_token = None
    auth_routes._ACTIVE_PKCE_SESSIONS.clear()


@pytest.mark.asyncio
async def test_zepto_login_redirects_to_authorize_with_pkce(client):
    response = await client.get("/api/v1/auth/zepto/login", follow_redirects=False)

    assert response.status_code == 307
    location = response.headers["location"]
    parsed = urlparse(location)
    assert parsed.scheme == "https"
    assert parsed.netloc == "auth.zepto.co.in"
    assert parsed.path == "/authorize"

    params = parse_qs(parsed.query)
    assert params["response_type"] == ["code"]
    assert params["code_challenge_method"] == ["S256"]
    assert "code_challenge" in params
    assert "state" in params
    assert "redirect_uri" in params
    assert "576d1696ca6ecbf3f9eb0db780546d50" in params["client_id"]

    state = params["state"][0]
    assert state in auth_routes._ACTIVE_PKCE_SESSIONS


@pytest.mark.asyncio
async def test_zepto_callback_rejects_missing_or_invalid_state(client):
    response = await client.get("/api/v1/auth/zepto/callback?code=mock_code&state=nonexistent_state")

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid or expired OAuth state"


@pytest.mark.asyncio
async def test_zepto_callback_exchanges_code_for_token_and_sets_authenticated(client, monkeypatch):
    # 1. Start login to register active state & verifier
    login_resp = await client.get("/api/v1/auth/zepto/login", follow_redirects=False)
    params = parse_qs(urlparse(login_resp.headers["location"]).query)
    state = params["state"][0]

    # 2. Mock token endpoint response
    async def mock_token_post(_self, _url, data=None, **_kwargs):
        assert data["grant_type"] == "authorization_code"
        assert data["code"] == "test_auth_code"
        assert "code_verifier" in data
        return httpx.Response(
            200,
            json={
                "access_token": "mock_live_zepto_token_xyz",
                "refresh_token": "mock_refresh_token_abc",
                "expires_in": 3600,
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_token_post)

    # 3. Call callback
    callback_resp = await client.get(f"/api/v1/auth/zepto/callback?code=test_auth_code&state={state}")

    assert callback_resp.status_code == 200
    assert "Connected to Zepto!" in callback_resp.text
    assert zepto_client.is_authenticated is True
    assert zepto_client.access_token == "mock_live_zepto_token_xyz"

    # 4. Status endpoint reflects authentication
    status_resp = await client.get("/api/v1/auth/zepto/status")
    assert status_resp.status_code == 200
    assert status_resp.json()["is_authenticated"] is True

    # 5. User profile reflects Zepto authentication
    profile_resp = await client.get("/api/v1/me")
    assert profile_resp.status_code == 200
    assert profile_resp.json()["is_zepto_authenticated"] is True


@pytest.mark.asyncio
async def test_zepto_callback_handles_upstream_token_error(client, monkeypatch):
    login_resp = await client.get("/api/v1/auth/zepto/login", follow_redirects=False)
    params = parse_qs(urlparse(login_resp.headers["location"]).query)
    state = params["state"][0]

    async def mock_token_post_error(_self, _url, **_kwargs):
        return httpx.Response(400, json={"error": "invalid_grant", "error_description": "Code expired"})

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_token_post_error)

    callback_resp = await client.get(f"/api/v1/auth/zepto/callback?code=expired_code&state={state}")

    assert callback_resp.status_code == 400
    assert "Authentication Failed" in callback_resp.text
    assert zepto_client.is_authenticated is False
