from uuid import uuid4

import httpx
from fastapi import APIRouter, File, UploadFile

from src.core.logging import logger
from src.schemas.voice import (
    TranscribeResponse,
    TTSRequest,
    TTSResponse,
    VoiceSessionRequest,
    VoiceSessionResponse,
)
from src.services.sarvam.client import sarvam_client
from src.utils.audio_validator import inspect_audio

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

    # Inspect audio duration & validity BEFORE calling Sarvam to prevent unnecessary billing
    inspection = inspect_audio(audio_content, filename=audio.filename or "recording.m4a")
    if not inspection.is_valid:
        logger.warning(
            f"Audio validation failed ({inspection.reason}, duration={inspection.duration:.2f}s, "
            f"{len(audio_content)} bytes). Skipping Sarvam STT API call to avoid billing."
        )
        return TranscribeResponse(
            session_id=uuid4(),
            transcript="",
            detected_language="en-IN",
            confidence=0.0,
        )

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


@router.post("/simulate", response_model=TranscribeResponse)
async def simulate_voice_utterance(query: str = "Add 2 Nandini milk and bread to my cart"):
    """Simulate a voice transcription for diagnostics and testing in restricted environments."""
    logger.info(f"Simulating voice utterance: '{query}'")
    return TranscribeResponse(
        session_id=uuid4(),
        transcript=query,
        detected_language="en-IN",
        confidence=1.0,
    )


@router.post("/tts", response_model=TTSResponse)
async def generate_text_to_speech(request: TTSRequest):
    """Generate Indian-accent spoken audio for assistant responses using Sarvam bulbul:v4-flash."""
    audio_b64 = await sarvam_client.generate_speech_base64(request.text, request.language)
    return TTSResponse(audio_base64=audio_b64, format="wav")
