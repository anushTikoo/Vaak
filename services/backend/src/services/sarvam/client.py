from src.core.config import settings
from src.core.logging import logger


class SarvamClient:
    """Client for Sarvam AI Speech & Language APIs."""

    def __init__(self):
        self.api_key = settings.SARVAM_API_KEY
        self.stt_endpoint = settings.SARVAM_STT_ENDPOINT
        self.tts_endpoint = settings.SARVAM_TTS_ENDPOINT
        self.model = settings.SARVAM_LLM_MODEL
        # Turn counter for realistic multi-turn conversational progression in development
        self._dev_turn_index = 0

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key != "mock_dev_key")

    async def transcribe_audio(self, audio_bytes: bytes, language: str = "auto") -> dict:
        if not self.is_configured:
            # Simulate natural conversational dialogue progression across consecutive recordings
            dev_dialogue_turns = [
                "I need two litres of milk and six eggs",
                "Yes, add them to my cart",
                "Place order",
            ]
            chosen_transcript = dev_dialogue_turns[self._dev_turn_index % len(dev_dialogue_turns)]
            self._dev_turn_index += 1

            logger.info(
                f"SarvamClient (Dev Mode): Simulated Turn {self._dev_turn_index} -> '{chosen_transcript}' "
                f"({len(audio_bytes)} bytes received)"
            )
            return {
                "transcript": chosen_transcript,
                "detected_language": "en-IN",
                "confidence": 0.95,
                "is_stub": True,
            }

        # Real production integration via Sarvam AI REST / WebSocket API
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as http_client:
            files = {"file": ("recording.m4a", audio_bytes, "audio/m4a")}
            headers = {"api-subscription-key": self.api_key}
            data = {"language_code": "unknown" if language == "auto" else language, "model": "saaras:v4"}
            resp = await http_client.post(
                "https://api.sarvam.ai/speech-to-text",
                files=files,
                headers=headers,
                data=data,
            )
            resp.raise_for_status()
            res_json = resp.json()
            return {
                "transcript": res_json.get("transcript", ""),
                "detected_language": res_json.get("language_code", "en-IN"),
                "confidence": res_json.get("language_probability", 0.98),
                "is_stub": False,
            }

    async def generate_speech(self, text: str, language: str = "en-IN") -> bytes:
        if not self.is_configured:
            return b""
        import base64

        import httpx

        async with httpx.AsyncClient(timeout=30.0) as http_client:
            headers = {"api-subscription-key": self.api_key, "Content-Type": "application/json"}
            payload = {
                "inputs": [text],
                "target_language_code": language,
                "speaker": "meera",
                "model": "bulbul:v4-flash",
            }
            resp = await http_client.post("https://api.sarvam.ai/text-to-speech", headers=headers, json=payload)
            resp.raise_for_status()
            res_data = resp.json()
            if "audios" in res_data and res_data["audios"]:
                return base64.b64decode(res_data["audios"][0])
            return b""


sarvam_client = SarvamClient()
