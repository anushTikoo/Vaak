import base64
import hashlib
import secrets

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse

from src.core.config import settings
from src.core.logging import logger
from src.services.zepto.client import zepto_client

router = APIRouter(prefix="/api/v1/auth/zepto", tags=["Zepto Auth"])

# In-memory storage for active PKCE sessions: state -> code_verifier
_ACTIVE_PKCE_SESSIONS: dict[str, str] = {}


def _generate_code_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


@router.get("/login")
async def zepto_login():
    """Initiate Zepto OAuth 2.0 PKCE flow."""
    if not settings.ZEPTO_CLIENT_ID:
        raise HTTPException(status_code=500, detail="ZEPTO_CLIENT_ID not configured")

    code_verifier = secrets.token_urlsafe(64)
    code_challenge = _generate_code_challenge(code_verifier)
    state = secrets.token_urlsafe(32)

    _ACTIVE_PKCE_SESSIONS[state] = code_verifier

    redirect_uri = "http://localhost:8000/api/v1/auth/zepto/callback"
    scopes = "tools:read tools:write dev.ucp.shopping.cart:manage dev.ucp.shopping.catalog.search:read"

    auth_url = (
        f"https://auth.zepto.co.in/authorize"
        f"?response_type=code"
        f"&client_id={settings.ZEPTO_CLIENT_ID}"
        f"&redirect_uri={redirect_uri}"
        f"&scope={scopes}"
        f"&code_challenge={code_challenge}"
        f"&code_challenge_method=S256"
        f"&state={state}"
    )
    logger.info(f"Initiating Zepto OAuth PKCE flow (state={state[:8]}...)")
    return RedirectResponse(url=auth_url)


@router.get("/callback", response_class=HTMLResponse)
async def zepto_callback(code: str = Query(...), state: str = Query(...)):
    """Exchange authorization code for Zepto MCP access token."""
    code_verifier = _ACTIVE_PKCE_SESSIONS.pop(state, None)
    if not code_verifier:
        logger.warning(f"Invalid or expired state in OAuth callback: {state}")
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")

    token_url = "https://auth.zepto.co.in/token"
    redirect_uri = "http://localhost:8000/api/v1/auth/zepto/callback"

    data = {
        "grant_type": "authorization_code",
        "client_id": settings.ZEPTO_CLIENT_ID,
        "code": code,
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier,
    }

    async with httpx.AsyncClient(timeout=15.0) as http_client:
        resp = await http_client.post(token_url, data=data)
        if resp.status_code != 200:
            logger.error(f"Failed to exchange Zepto OAuth code: {resp.status_code} {resp.text}")
            error_style = "background:#1E293B; padding:16px; border-radius:8px; display:inline-block;"
            return HTMLResponse(
                content=f"""
                <html>
                <body style="font-family:sans-serif; text-align:center; padding:40px; background:#0F172A; color:#fff;">
                    <h2 style="color:#EF4444">⚠️ Authentication Failed</h2>
                    <p>Zepto returned status {resp.status_code}.</p>
                    <pre style="{error_style} text-align:left;">{resp.text}</pre>
                </body>
                </html>
                """,
                status_code=400,
            )

        token_data = resp.json()
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        zepto_client.set_tokens(access_token, refresh_token)

    card_style = "max-width:400px; margin:0 auto; background:#1E293B; padding:30px; border-radius:16px;"
    badge_style = "margin-top:24px; padding:10px; background:#0F172A; border-radius:8px; color:#A5B4FC;"
    return HTMLResponse(
        content=f"""
        <html>
        <body style="font-family:sans-serif; text-align:center; padding:50px; background:#0F172A; color:#F8FAFC;">
            <div style="{card_style} border:1px solid #10B981;">
                <h1 style="font-size:40px; margin-bottom:10px;">⚡</h1>
                <h2 style="color:#10B981; margin:0 0 10px 0;">Connected to Zepto!</h2>
                <p style="color:#94A3B8; font-size:14px; line-height:20px;">
                    Your Zepto account is authenticated for Vaak. You can close this tab and return to the app.
                </p>
                <div style="{badge_style} font-size:12px;">
                    ✓ Live Catalog Search & Cart Access Enabled
                </div>
            </div>
        </body>
        </html>
        """
    )


@router.get("/status")
async def zepto_status():
    return {
        "is_authenticated": zepto_client.is_authenticated,
        "endpoint": settings.ZEPTO_MCP_ENDPOINT,
    }
