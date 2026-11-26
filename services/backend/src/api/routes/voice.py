from uuid import uuid4

from fastapi import APIRouter, File, UploadFile

from src.schemas.voice import TranscribeResponse, VoiceSessionRequest, VoiceSessionResponse
from src.services.sarvam.client import sarvam_client

router = APIRouter(prefix="/api/v1/voice", tags=["Voice"])


@router.post("/session", response_model=VoiceSessionResponse)
async def create_voice_session(request: VoiceSessionRequest):
    return VoiceSessionResponse(
        session_id=uuid4(),
        ws_endpoint="/api/v1/voice/stream",
        status="ready",
        active_language=request.language_code,
    )


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_audio_file(audio: UploadFile = File(...)):
    audio_content = await audio.read()
    result = await sarvam_client.transcribe_audio(audio_content)
    return TranscribeResponse(
        session_id=uuid4(),
        transcript=result["transcript"],
        detected_language=result.get("detected_language"),
        confidence=result.get("confidence", 0.0),
    )
