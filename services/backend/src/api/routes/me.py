from fastapi import APIRouter

from src.schemas.user import UserProfileResponse

router = APIRouter(prefix="/api/v1", tags=["User"])


@router.get("/me", response_model=UserProfileResponse)
async def get_current_user_profile():
    # In initial foundation, return mock profile for session
    return UserProfileResponse(
        phone_number="+91 98765 43210",
        is_zepto_authenticated=False,
        preferred_language="en-IN",
    )
