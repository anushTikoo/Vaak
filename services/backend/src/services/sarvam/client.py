import json
import re
from collections import OrderedDict
from typing import Any

from src.core.config import settings
from src.core.logging import logger

LANGUAGE_SPEAKER_MAP = {
    "hi-IN": ("hi-IN", "simran_hi_assistant"),
    "hi": ("hi-IN", "simran_hi_assistant"),
    "en-IN": ("en-IN", "simran_en_conversation"),
    "en": ("en-IN", "simran_en_conversation"),
    "bn-IN": ("bn-IN", "roopa_bn_conversational"),
    "bn": ("bn-IN", "roopa_bn_conversational"),
    "gu-IN": ("gu-IN", "pooja_gu_conversational"),
    "gu": ("gu-IN", "pooja_gu_conversational"),
    "kn-IN": ("kn-IN", "chaitra_kn_conversation"),
    "kn": ("kn-IN", "chaitra_kn_conversation"),
    "mr-IN": ("mr-IN", "ishita_mr_conversational"),
    "mr": ("mr-IN", "ishita_mr_conversational"),
    "pa-IN": ("pa-IN", "anand_pa_conversation"),
    "pa": ("pa-IN", "anand_pa_conversation"),
    "ta-IN": ("ta-IN", "gokul_ta_narration"),
    "ta": ("ta-IN", "gokul_ta_narration"),
    "te-IN": ("te-IN", "kavitha_te_conversation"),
    "te": ("te-IN", "kavitha_te_conversation"),
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
        # In-memory LRU Audio Cache to eliminate redundant Sarvam TTS requests & billing
        self._audio_cache: OrderedDict[str, str] = OrderedDict()
        self._audio_cache_max_size: int = 256

    def clear_audio_cache(self) -> None:
        """Clear all entries in the LRU audio cache."""
        self._audio_cache.clear()

    def get_audio_cache_size(self) -> int:
        """Return number of cached audio items."""
        return len(self._audio_cache)

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

    @staticmethod
    def sanitize_tts_text(text: str, max_chars: int = 140) -> str:
        """Clean markdown, punctuation, and enforce character budget for TTS cost & latency optimization."""
        if not text:
            return ""
        # Strip markdown links [text](url) -> text
        cleaned = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
        # Strip markdown formatting (*, _, #, `, ~)
        cleaned = re.sub(r"[#*_`~]+", "", cleaned)
        # Strip HTML tags
        cleaned = re.sub(r"<[^>]+>", "", cleaned)
        # Strip emojis and pictographs to prevent TTS billing on non-speech glyphs
        cleaned = re.sub(r"[\U00010000-\U0010ffff\u2600-\u27bf\u2300-\u23ff]", "", cleaned)
        # Replace list markers and bullets at start of lines
        cleaned = re.sub(r"^\s*[-*•]\s+", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"^\s*\d+\.\s+", "", cleaned, flags=re.MULTILINE)
        # Collapse multiple whitespace and newlines
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        # Clean redundant punctuation (e.g. multiple question/exclamation marks or danda)
        cleaned = re.sub(r"([!?.,।])\1+", r"\1", cleaned)
        # Remove space before punctuation marks
        cleaned = re.sub(r"\s+([!?.,।])", r"\1", cleaned)

        if len(cleaned) <= max_chars:
            return cleaned

        # Truncate cleanly within character budget (~140 chars)
        truncated = cleaned[:max_chars]
        last_punct = max(
            truncated.rfind("."),
            truncated.rfind("!"),
            truncated.rfind("?"),
            truncated.rfind("।"),
            truncated.rfind("॥"),
            truncated.rfind("؟"),
        )
        if last_punct >= max_chars // 2:
            return truncated[: last_punct + 1].strip()

        last_space = truncated.rfind(" ")
        if last_space > 0:
            return truncated[:last_space].rstrip(" ,;:-") + "..."
        return truncated.strip()

    async def generate_speech_base64(self, text: str, language: str = "en-IN") -> str:
        if not text or not text.strip():
            return ""

        # Pre-process text and enforce character budget to minimize TTS billing and token overhead
        sanitized_text = self.sanitize_tts_text(text)
        if not sanitized_text:
            return ""

        # Resolve target language and matching speaker
        target_lang = language or "en-IN"
        if target_lang in ("auto", "unknown", None, ""):
            target_lang = self.detect_language(sanitized_text)
        else:
            target_lang = self.normalize_language_code(target_lang)

        lang_code, speaker = LANGUAGE_SPEAKER_MAP.get(target_lang, ("en-IN", "simran_en_conversation"))

        # LRU Audio Cache: Check if synthesized audio already exists
        normalized_key_text = sanitized_text.strip().lower()
        cache_key = f"{lang_code}:{normalized_key_text}"

        if cache_key in self._audio_cache:
            logger.info(f"SarvamClient: Audio cache HIT for '{cache_key}'. Bypassing TTS API call.")
            self._audio_cache.move_to_end(cache_key)
            return self._audio_cache[cache_key]

        if not self.is_configured:
            return ""

        import httpx

        async with httpx.AsyncClient(timeout=30.0) as http_client:
            headers = {"api-subscription-key": self.api_key, "Content-Type": "application/json"}
            payload = {
                "inputs": [sanitized_text],
                "target_language_code": lang_code,
                "speaker": speaker,
                "model": "bulbul:v4-flash",
            }
            resp = await http_client.post("https://api.sarvam.ai/text-to-speech", headers=headers, json=payload)
            resp.raise_for_status()
            res_data = resp.json()
            if "audios" in res_data and res_data["audios"]:
                audio_b64 = res_data["audios"][0]
                # Store in LRU cache with eviction if exceeding max size
                if cache_key in self._audio_cache:
                    self._audio_cache.move_to_end(cache_key)
                else:
                    if len(self._audio_cache) >= self._audio_cache_max_size:
                        self._audio_cache.popitem(last=False)
                self._audio_cache[cache_key] = audio_b64
                return audio_b64
        return ""

    async def generate_speech(self, text: str, language: str = "en-IN") -> bytes:
        import base64

        b64 = await self.generate_speech_base64(text, language)
        if b64:
            return base64.b64decode(b64)
        return b""

    @staticmethod
    def normalize_language_code(lang_code: str | None) -> str:
        """Normalize language code to standardized BCP-47 tag (e.g. 'hi' -> 'hi-IN')."""
        if not lang_code or lang_code in ("auto", "unknown"):
            return "en-IN"
        clean = lang_code.strip()
        if clean in LANGUAGE_SPEAKER_MAP:
            return LANGUAGE_SPEAKER_MAP[clean][0]
        prefix = clean.split("-")[0].lower()
        if prefix in LANGUAGE_SPEAKER_MAP:
            return LANGUAGE_SPEAKER_MAP[prefix][0]
        return clean

    @staticmethod
    def detect_language(text: str) -> str:
        """Detect language script and Indic keywords for accurate routing and TTS voice matching."""
        if not text:
            return "en-IN"
        if re.search(r"[\u0900-\u097F]", text):
            return "hi-IN"
        if re.search(r"[\u0980-\u09FF]", text):
            return "bn-IN"
        if re.search(r"[\u0A00-\u0A7F]", text):
            return "pa-IN"
        if re.search(r"[\u0A80-\u0AFF]", text):
            return "gu-IN"
        if re.search(r"[\u0B00-\u0B7F]", text):
            return "od-IN"
        if re.search(r"[\u0B80-\u0BFF]", text):
            return "ta-IN"
        if re.search(r"[\u0C00-\u0C7F]", text):
            return "te-IN"
        if re.search(r"[\u0C80-\u0CFF]", text):
            return "kn-IN"
        if re.search(r"[\u0D00-\u0D7F]", text):
            return "ml-IN"
        if re.search(
            r"\b(doodh|dudh|chahiye|kardo|bhej do|daal do|namaste|"
            r"aate|paani|sabzi|anda|ande|chawal|cheeni|shakkar|bhaiya|beta|kripya)\b",
            text,
            re.IGNORECASE,
        ):
            return "hi-IN"
        return "en-IN"

    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        model: str | None = None,
        stream: bool = False,
    ) -> dict[str, Any]:
        """Execute chat completion with Sarvam 105B conversational model (OpenAI-compatible)."""
        chosen_model = model or self.model or "sarvam-105b-conversations"

        if not self.is_configured:
            return self._generate_mock_chat_completion(messages, tools)

        headers = {
            "api-subscription-key": self.api_key,
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": chosen_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if stream:
            payload["stream"] = True
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice or "auto"

        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.sarvam.ai/v1/chat/completions",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()

    async def chat_completion_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        model: str | None = None,
    ):
        """Stream chat completion tokens via Server-Sent Events from Sarvam 105B conversational model."""
        chosen_model = model or self.model or "sarvam-105b-conversations"

        if not self.is_configured:
            mock_res = self._generate_mock_chat_completion(messages, tools)
            content = mock_res.get("choices", [{}])[0].get("message", {}).get("content") or ""
            for word in content.split(" "):
                yield word + " "
            return

        import httpx

        headers = {
            "api-subscription-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        payload = {
            "model": chosen_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools

        async with httpx.AsyncClient(timeout=30.0) as client, client.stream(
            "POST", "https://api.sarvam.ai/v1/chat/completions", headers=headers, json=payload
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data_str = line[len("data:"):].strip()
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                    choices = chunk.get("choices") or []
                    if choices:
                        delta = choices[0].get("delta", {})
                        token = delta.get("content")
                        if token:
                            yield token
                except json.JSONDecodeError:
                    continue

    def _generate_mock_chat_completion(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Simulate Sarvam 105B model behavior in unconfigured / test environments."""
        last_msg = messages[-1] if messages else {"role": "user", "content": ""}
        role = last_msg.get("role", "user")
        content = str(last_msg.get("content", "")).lower()

        # If previous message was a tool execution result (turn 2)
        if role == "tool":
            tool_name = str(last_msg.get("name", ""))
            order_confirm_tools = (
                "create_order",
                "confirm_order_cod",
                "create_online_payment_order",
                "confirm_online_payment_order",
            )
            if tool_name in order_confirm_tools:
                turn2_reply = (
                    "Ji, I have prepared your order summary on the screen for your review. "
                    "For your safety, please check the bill and tap Confirm on your phone when you are ready."
                )
            elif tool_name in ("view_cart", "get_cart"):
                turn2_reply = (
                    "Ji, here are the items currently in your cart. "
                    "You can review them on screen whenever you are ready."
                )
            elif tool_name in ("update_cart", "add_to_cart", "remove_from_cart"):
                turn2_reply = (
                    "Ji, I have updated your cart as requested. Would you like to add anything else?"
                )
            else:
                turn2_reply = (
                    "I have found matching fresh items for you. "
                    "Would you like me to add them to your cart?"
                )
            return {
                "id": "mock_105b_completion",
                "object": "chat.completion",
                "model": "sarvam-105b-conversations",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": turn2_reply,
                            "tool_calls": None,
                        },
                    }
                ],
            }

        # Order placement intent -> Safety guardrail preview
        if any(w in content for w in ("order", "checkout", "place order", "buy", "khareed")):
            return {
                "id": "mock_105b_completion",
                "object": "chat.completion",
                "model": "sarvam-105b-conversations",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "mock_call_order",
                                    "type": "function",
                                    "function": {
                                        "name": "create_order",
                                        "arguments": json.dumps({"confirmOrder": False, "riderTip": 0}),
                                    },
                                }
                            ],
                        },
                    }
                ],
            }

        # Cart query intent
        if any(w in content for w in ("cart", "basket", "tokri", "jhola", "items in my cart")):
            return {
                "id": "mock_105b_completion",
                "object": "chat.completion",
                "model": "sarvam-105b-conversations",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "mock_call_cart",
                                    "type": "function",
                                    "function": {"name": "view_cart", "arguments": "{}"},
                                }
                            ],
                        },
                    }
                ],
            }

        # Check for grocery shopping signals
        grocery_signals = (
            "doodh", "dudh", "milk", "bread", "egg", "anda", "ande", "butter", "makhan", "ghee",
            "paneer", "apple", "seb", "banana", "kela", "tomato", "tamatar", "potato", "aloo",
            "onion", "pyaz", "sabzi", "vegetable", "fruit", "aata", "atta", "flour", "chawal",
            "rice", "dal", "daal", "cheeni", "sugar", "tea", "chai", "coffee", "oil", "tel",
            "biscuit", "water", "paani", "grocery", "groceries", "chahiye", "bhej", "lao",
            "packet", "litre", "liter", "kg", "pack"
        )
        has_grocery_intent = any(w in content for w in grocery_signals)

        # User greeting / conversational pleasantry -> SMART ROUTING: DO NOT CALL TOOLS
        greeting_words = (
            "hello", "namaste", "namaskar", "pranam", "kaise ho", "how are you",
            "good morning", "good evening", "good afternoon", "thank you", "thanks",
            "dhanyawaad", "shukriya", "who are you", "aap kaun ho"
        )
        is_greeting = any(w in content for w in greeting_words)

        # Smart routing: pure greetings with NO grocery or cart intent -> respond politely without tools
        if is_greeting and not has_grocery_intent:
            return {
                "id": "mock_105b_completion",
                "object": "chat.completion",
                "model": "sarvam-105b-conversations",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": (
                                "Namaste! I am Vaak, your caring grocery shopping companion. "
                                "How may I help you today? Please tell me what groceries you need."
                            ),
                            "tool_calls": None,
                        },
                    }
                ],
            }

        # Grocery search intent: strip polite filler words to extract core product keywords
        clean_query = content
        for stop_word in (
            "namaste", "beta", "bhaiya", "hello", "hi", "kripya", "please", "can you",
            "add", "find", "need", "chahiye", "bhej do", "daal do", "lao", "mujhe",
            "humko", "give me", "i want", "two", "do", "ek", "one", "packet", "packets"
        ):
            clean_query = re.sub(rf"\b{stop_word}\b", "", clean_query, flags=re.IGNORECASE)
        query = clean_query.strip() or "groceries"

        return {
            "id": "mock_105b_completion",
            "object": "chat.completion",
            "model": "sarvam-105b-conversations",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "mock_call_search",
                                "type": "function",
                                "function": {
                                    "name": "search_products",
                                    "arguments": json.dumps({"query": query}),
                                },
                            }
                        ],
                    },
                }
            ],
        }

    async def translate_text(
        self,
        text: str,
        target_language_code: str,
        source_language_code: str = "auto",
        mode: str = "formal",
    ) -> str:
        """Translate text using Sarvam Mayura translation API."""
        if not text or not text.strip():
            return ""

        target_lang = self.normalize_language_code(target_language_code)
        source_lang = "auto" if source_language_code == "auto" else self.normalize_language_code(source_language_code)

        if source_lang == target_lang and source_lang != "auto":
            return text

        if source_lang == "auto" and self.detect_language(text) == target_lang:
            return text

        if not self.is_configured:
            return text

        headers = {
            "api-subscription-key": self.api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "input": text[:1000],
            "source_language_code": source_lang,
            "target_language_code": target_lang,
            "mode": mode,
            "model": "mayura:v1",
        }

        import httpx

        try:
            async with httpx.AsyncClient(timeout=20.0) as http_client:
                resp = await http_client.post(
                    "https://api.sarvam.ai/translate",
                    headers=headers,
                    json=payload,
                )
                resp.raise_for_status()
                res_json = resp.json()
                return res_json.get("translated_text", text)
        except Exception as e:
            logger.warning(f"Sarvam translation failed: {e}. Falling back to original text.")
            return text


sarvam_client = SarvamClient()
