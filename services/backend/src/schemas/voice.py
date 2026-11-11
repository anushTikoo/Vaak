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


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Text to synthesize to speech")
    language: str = Field(default="en-IN", description="Target spoken language code")


class TTSResponse(BaseModel):
    audio_base64: str
    format: str = "wav"
