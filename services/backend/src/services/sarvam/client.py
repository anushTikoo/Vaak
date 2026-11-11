from src.core.config import settings
from src.core.logging import logger

LANGUAGE_SPEAKER_MAP = {
    "hi-IN": ("hi-IN", "simran_hi_assistant"),
    "hi": ("hi-IN", "simran_hi_assistant"),
    "en-IN": ("en-IN", "simran_en_conversation"),
    "en": ("en-IN", "simran_en_conversation"),
    "bn-IN": ("bn-IN", "roopa_bn_conversational"),
    "gu-IN": ("gu-IN", "pooja_gu_conversational"),
    "kn-IN": ("kn-IN", "chaitra_kn_conversation"),
    "mr-IN": ("mr-IN", "ishita_mr_conversational"),
    "pa-IN": ("pa-IN", "anand_pa_conversation"),
    "ta-IN": ("ta-IN", "gokul_ta_narration"),
    "te-IN": ("te-IN", "kavitha_te_conversation"),
}


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

        # Pre-validate audio duration to completely prevent empty/zero-duration billing from Sarvam
        from src.utils.audio_validator import inspect_audio

        inspection = inspect_audio(audio_bytes)
        if not inspection.is_valid:
            logger.warning(
                f"SarvamClient: Audio pre-validation rejected ({inspection.reason}, "
                f"duration={inspection.duration:.2f}s). Aborting API call to Sarvam AI STT to avoid billing."
            )
            return {
                "transcript": "",
                "detected_language": "en-IN",
                "confidence": 0.0,
                "is_stub": False,
            }

        # Real production integration via Sarvam AI REST / WebSocket API
        import httpx

        from src.utils.audio_validator import detect_audio_container

        ext, mime_type = detect_audio_container(audio_bytes)

        async with httpx.AsyncClient(timeout=30.0) as http_client:
            files = {"file": (f"recording{ext}", audio_bytes, mime_type)}
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

    async def generate_speech_base64(self, text: str, language: str = "en-IN") -> str:
        if not self.is_configured or not text.strip():
            return ""
        import re

        import httpx

        # If language is auto or text contains Devanagari script, select Hindi
        target_lang = language or "en-IN"
        if target_lang in ("auto", "unknown", None, ""):
            target_lang = "hi-IN" if re.search(r"[\u0900-\u097F]", text) else "en-IN"
        elif target_lang.startswith("hi"):
            target_lang = "hi-IN"
        elif target_lang.startswith("en"):
            target_lang = "en-IN"

        lang_code, speaker = LANGUAGE_SPEAKER_MAP.get(target_lang, ("en-IN", "simran_en_conversation"))

        async with httpx.AsyncClient(timeout=30.0) as http_client:
            headers = {"api-subscription-key": self.api_key, "Content-Type": "application/json"}
            payload = {
                "inputs": [text],
                "target_language_code": lang_code,
                "speaker": speaker,
                "model": "bulbul:v4-flash",
            }
            resp = await http_client.post("https://api.sarvam.ai/text-to-speech", headers=headers, json=payload)
            resp.raise_for_status()
            res_data = resp.json()
            if "audios" in res_data and res_data["audios"]:
                return res_data["audios"][0]
        return ""

    async def generate_speech(self, text: str, language: str = "en-IN") -> bytes:
        if not self.is_configured:
            return b""
        import base64

        b64 = await self.generate_speech_base64(text, language)
        if b64:
            return base64.b64decode(b64)
        return b""


sarvam_client = SarvamClient()
