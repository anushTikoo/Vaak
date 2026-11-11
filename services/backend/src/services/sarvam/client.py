from src.core.config import settings
from src.core.logging import logger


class SarvamClient:
    """Client for Sarvam AI Speech & Language APIs."""

    def __init__(self):
        self.api_key = settings.SARVAM_API_KEY
        self.stt_endpoint = settings.SARVAM_STT_ENDPOINT
        self.tts_endpoint = settings.SARVAM_TTS_ENDPOINT
        self.model = settings.SARVAM_LLM_MODEL

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key != "mock_dev_key")

    async def transcribe_audio(self, audio_bytes: bytes, language: str = "auto") -> dict:
        if not self.is_configured:
            logger.info(
                "SarvamClient is in development mode (no production API key). Returning stub."
            )
            return {
                "transcript": "I need two litres of milk and six eggs",
                "detected_language": "en-IN",
                "confidence": 0.95,
                "is_stub": True,
            }
        # Real integration will stream to Sarvam STT WebSocket / REST endpoint
        raise NotImplementedError(
            "Sarvam live STT endpoint connection pending production credentials"
        )

    async def generate_speech(self, text: str, language: str = "en-IN") -> bytes:
        if not self.is_configured:
            return b""
        raise NotImplementedError(
            "Sarvam live TTS endpoint connection pending production credentials"
        )


sarvam_client = SarvamClient()
