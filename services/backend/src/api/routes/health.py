from fastapi import APIRouter

from src.core.config import settings

router = APIRouter(tags=["Health"])


@router.get("/health")
async def root_health():
    return {
        "status": "healthy",
        "service": "vak-backend",
        "environment": settings.ENVIRONMENT,
    }


@router.get("/api/v1/health")
async def api_v1_health():
    return {
        "status": "healthy",
        "version": "v1",
        "integrations": {
            "sarvam": "configured"
            if settings.SARVAM_API_KEY and settings.SARVAM_API_KEY != "mock_dev_key"
            else "development_mock",
            "zepto_mcp": "ready",
            "database": "configured" if settings.DATABASE_URL else "unconfigured",
        },
    }
