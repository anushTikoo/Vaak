from uuid import uuid4

import httpx
from fastapi import APIRouter, File, UploadFile

from src.core.logging import logger
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
    logger.info(f"Received audio upload: {len(audio_content)} bytes, filename={audio.filename}")
    try:
        result = await sarvam_client.transcribe_audio(audio_content)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 400:
            logger.warning(f"Sarvam STT returned 400 (audio empty or zero duration): {e.response.text}")
            return TranscribeResponse(
                session_id=uuid4(),
                transcript="",
                detected_language="en-IN",
                confidence=0.0,
            )
        raise

    return TranscribeResponse(
        session_id=uuid4(),
        transcript=result["transcript"],
        detected_language=result.get("detected_language"),
        confidence=result.get("confidence", 0.0),
    )
