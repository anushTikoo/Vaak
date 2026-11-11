from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class VoiceSessionRequest(BaseModel):
    language_code: str = Field(default="auto", description="Spoken language hint or auto-detect")


class VoiceSessionResponse(BaseModel):
    session_id: UUID = Field(default_factory=uuid4)
    ws_endpoint: str
    status: str = "ready"
    active_language: str = "auto"


class TranscribeResponse(BaseModel):
    session_id: UUID
    transcript: str
    detected_language: str | None = None
    confidence: float = 0.0
