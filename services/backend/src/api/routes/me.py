from fastapi import APIRouter

from src.schemas.user import UserProfileResponse
from src.services.zepto.client import zepto_client

router = APIRouter(prefix="/api/v1", tags=["User"])


@router.get("/me", response_model=UserProfileResponse)
async def get_current_user_profile():
    return UserProfileResponse(
        phone_number="+91 98765 43210",
        is_zepto_authenticated=zepto_client.is_authenticated,
        preferred_language="en-IN",
    )
