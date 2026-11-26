from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class UserProfileResponse(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    phone_number: str | None = None
    is_zepto_authenticated: bool = False
    preferred_language: str = "en-IN"
