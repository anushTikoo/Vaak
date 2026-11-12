import base64
import json

import httpx
import pytest

from src.services.sarvam.client import SarvamClient, sarvam_client


def install_mock_http_client(monkeypatch, handler):
    """Route the Sarvam client's HTTP calls through an in-memory transport."""
    real_async_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        return real_async_client(
            *args,
            transport=httpx.MockTransport(handler),
            **kwargs,
        )

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)


@pytest.mark.asyncio
async def test_unconfigured_client_returns_repeatable_three_turn_dev_dialogue(monkeypatch):
    client = SarvamClient()
    monkeypatch.setattr(client, "api_key", "mock_dev_key")

    first = await client.transcribe_audio(b"audio-1")
    second = await client.transcribe_audio(b"audio-2", language="hi-IN")
    third = await client.transcribe_audio(b"audio-3")
    fourth = await client.transcribe_audio(b"audio-4")

    assert first["transcript"] == "I need two litres of milk and six eggs"
    assert second["transcript"] == "Yes, add them to my cart"
    assert third["transcript"] == "Place order"
    assert fourth["transcript"] == first["transcript"]
    assert all(result["is_stub"] is True for result in (first, second, third, fourth))
    assert all(result["detected_language"] == "en-IN" for result in (first, second, third))
    assert await client.generate_speech("hello") == b""


@pytest.mark.asyncio
async def test_configured_stt_uses_saaras_v4_multipart_contract(monkeypatch):
    requests = []

    async def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "request_id": "request-123",
                "transcript": "दो लीटर दूध",
                "language_code": "hi-IN",
                "language_probability": 0.93,
            },
        )

    install_mock_http_client(monkeypatch, handler)
    monkeypatch.setattr(sarvam_client, "api_key", "test-subscription-key")

    result = await sarvam_client.transcribe_audio(b"sample-audio", language="auto")

    assert len(requests) == 1
    request = requests[0]
    assert request.method == "POST"
    assert str(request.url) == "https://api.sarvam.ai/speech-to-text"
    assert request.headers["api-subscription-key"] == "test-subscription-key"
    assert "multipart/form-data" in request.headers["content-type"]
    request_body = await request.aread()
    assert b"sample-audio" in request_body
    assert b'name="file"' in request_body
    assert b'name="language_code"' in request_body
    assert b"unknown" in request_body
    assert b'name="model"' in request_body
    assert b"saaras:v4" in request_body
    assert result == {
        "transcript": "दो लीटर दूध",
        "detected_language": "hi-IN",
        "confidence": 0.93,
        "is_stub": False,
    }


@pytest.mark.asyncio
async def test_configured_stt_passes_explicit_language_code(monkeypatch):
    requests = []

    async def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={"transcript": "two litres of milk", "language_code": "en-IN"},
        )

    install_mock_http_client(monkeypatch, handler)
    monkeypatch.setattr(sarvam_client, "api_key", "test-subscription-key")

    result = await sarvam_client.transcribe_audio(b"sample-audio", language="en-IN")

    body = await requests[0].aread()
    assert b'name="language_code"' in body
    assert b"en-IN" in body
    assert result["detected_language"] == "en-IN"


@pytest.mark.asyncio
async def test_configured_stt_propagates_provider_http_errors(monkeypatch):
    async def handler(_request):
        return httpx.Response(401, json={"error": "invalid subscription key"})

    install_mock_http_client(monkeypatch, handler)
    monkeypatch.setattr(sarvam_client, "api_key", "invalid-key")

    with pytest.raises(httpx.HTTPStatusError):
        await sarvam_client.transcribe_audio(b"sample-audio")


@pytest.mark.asyncio
async def test_configured_tts_uses_bulbul_v4_flash_and_decodes_audio(monkeypatch):
    audio_bytes = b"fake-wav-audio"
    requests = []

    async def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "request_id": "request-456",
                "audios": [base64.b64encode(audio_bytes).decode("ascii")],
            },
        )

    install_mock_http_client(monkeypatch, handler)
    monkeypatch.setattr(sarvam_client, "api_key", "test-subscription-key")

    result = await sarvam_client.generate_speech("नमस्ते", language="hi-IN")

    assert len(requests) == 1
    request = requests[0]
    assert str(request.url) == "https://api.sarvam.ai/text-to-speech"
    assert request.headers["api-subscription-key"] == "test-subscription-key"
    payload = json.loads(await request.aread())
    assert payload["inputs"] == ["नमस्ते"]
    assert payload["target_language_code"] == "hi-IN"
    assert payload["model"] == "bulbul:v4-flash"
    assert result == audio_bytes


@pytest.mark.asyncio
async def test_configured_tts_propagates_provider_http_errors(monkeypatch):
    async def handler(_request):
        return httpx.Response(429, json={"error": "rate limit exceeded"})

    install_mock_http_client(monkeypatch, handler)
    monkeypatch.setattr(sarvam_client, "api_key", "test-subscription-key")

    with pytest.raises(httpx.HTTPStatusError):
        await sarvam_client.generate_speech("hello")


@pytest.mark.asyncio
async def test_configured_stt_aborts_on_empty_or_zero_duration_audio_without_calling_api(monkeypatch):
    import io
    import wave

    requests = []

    async def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"transcript": "should not be reached"})

    install_mock_http_client(monkeypatch, handler)
    monkeypatch.setattr(sarvam_client, "api_key", "test-subscription-key")

    # 1. Empty bytes -> Must NOT call Sarvam API
    result_empty = await sarvam_client.transcribe_audio(b"")
    assert result_empty["transcript"] == ""
    assert len(requests) == 0

    # 2. Zero-duration audio container -> Must NOT call Sarvam API
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"")

    result_zero = await sarvam_client.transcribe_audio(buf.getvalue())
    assert result_zero["transcript"] == ""
    assert len(requests) == 0


@pytest.mark.asyncio
async def test_configured_chat_completion_uses_105b_and_tools_contract(monkeypatch):
    """Verify chat_completion sends OpenAI-compatible payload to https://api.sarvam.ai/v1/chat/completions."""
    requests = []

    async def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "id": "cmpl-123",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call-abc",
                                    "type": "function",
                                    "function": {"name": "search_products", "arguments": '{"query": "milk"}'},
                                }
                            ],
                        },
                    }
                ],
            },
        )

    install_mock_http_client(monkeypatch, handler)
    monkeypatch.setattr(sarvam_client, "api_key", "test-subscription-key")

    tools = [
        {
            "type": "function",
            "function": {
                "name": "search_products",
                "description": "Search products in Zepto",
                "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
            },
        }
    ]
    messages = [{"role": "user", "content": "I need milk"}]

    res = await sarvam_client.chat_completion(
        messages=messages,
        tools=tools,
        tool_choice="auto",
    )

    assert len(requests) == 1
    req = requests[0]
    assert str(req.url) == "https://api.sarvam.ai/v1/chat/completions"
    assert req.headers["api-subscription-key"] == "test-subscription-key"
    payload = json.loads(await req.aread())
    assert payload["model"] == "sarvam-105b-conversations"
    assert payload["messages"] == messages
    assert payload["tools"] == tools
    assert payload["tool_choice"] == "auto"
    assert res["choices"][0]["finish_reason"] == "tool_calls"


@pytest.mark.asyncio
async def test_configured_translate_text_uses_mayura_v1(monkeypatch):
    """Verify translate_text sends proper parameters to https://api.sarvam.ai/translate."""
    requests = []

    async def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "request_id": "trans-123",
                "translated_text": "नमस्ते, मैं आपकी कैसे मदद कर सकता हूँ?",
                "source_language_code": "en-IN",
            },
        )

    install_mock_http_client(monkeypatch, handler)
    monkeypatch.setattr(sarvam_client, "api_key", "test-subscription-key")

    res = await sarvam_client.translate_text(
        text="Hello, how can I help you?",
        target_language_code="hi-IN",
        source_language_code="en-IN",
    )

    assert len(requests) == 1
    req = requests[0]
    assert str(req.url) == "https://api.sarvam.ai/translate"
    assert req.headers["api-subscription-key"] == "test-subscription-key"
    payload = json.loads(await req.aread())
    assert payload["input"] == "Hello, how can I help you?"
    assert payload["source_language_code"] == "en-IN"
    assert payload["target_language_code"] == "hi-IN"
    assert payload["model"] == "mayura:v1"
    assert res == "नमस्ते, मैं आपकी कैसे मदद कर सकता हूँ?"


def test_language_normalization_and_detection_helpers():
    """Verify normalization of language tags and Indic script detection."""
    assert sarvam_client.normalize_language_code("hi") == "hi-IN"
    assert sarvam_client.normalize_language_code("hi-IN") == "hi-IN"
    assert sarvam_client.normalize_language_code("ta") == "ta-IN"
    assert sarvam_client.normalize_language_code("auto") == "en-IN"
    assert sarvam_client.normalize_language_code(None) == "en-IN"

    assert sarvam_client.detect_language("मुझे दो पैकेट दूध चाहिए") == "hi-IN"
    assert sarvam_client.detect_language("எனக்கு பால் வேண்டும்") == "ta-IN"
    assert sarvam_client.detect_language("నాకు పాలు కావాలి") == "te-IN"
    assert sarvam_client.detect_language("আমাকে দুধ দিন") == "bn-IN"
    assert sarvam_client.detect_language("doodh aur bread chahiye bhaiya") == "hi-IN"
    assert sarvam_client.detect_language("I want two cartons of milk") == "en-IN"


@pytest.mark.asyncio
async def test_unconfigured_chat_completion_stream(monkeypatch):
    """Verify chat_completion_stream streams tokens in unconfigured mock development mode."""
    client = SarvamClient()
    monkeypatch.setattr(client, "api_key", "mock_dev_key")
    tokens = []
    async for token in client.chat_completion_stream(
        messages=[{"role": "user", "content": "Hello"}]
    ):
        tokens.append(token)
    assert len(tokens) > 0
    full_text = "".join(tokens)
    assert "Namaste" in full_text or "help" in full_text or "groceries" in full_text


@pytest.mark.asyncio
async def test_configured_chat_completion_stream_yields_sse_chunks(monkeypatch):
    """Verify chat_completion_stream connects with stream=True and processes Server-Sent Events."""
    requests = []

    sse_data = (
        b'data: {"choices":[{"delta":{"content":"Namaste"}}]}\n\n'
        b'data: {"choices":[{"delta":{"content":" Ji"}}]}\n\n'
        b'data: [DONE]\n\n'
    )

    async def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            content=sse_data,
            headers={"Content-Type": "text/event-stream"},
        )

    install_mock_http_client(monkeypatch, handler)
    monkeypatch.setattr(sarvam_client, "api_key", "test-subscription-key")

    tokens = []
    async for token in sarvam_client.chat_completion_stream(
        messages=[{"role": "user", "content": "Namaste"}]
    ):
        tokens.append(token)

    assert tokens == ["Namaste", " Ji"]
    assert len(requests) == 1
    req = requests[0]
    payload = json.loads(await req.aread())
    assert payload["stream"] is True
    assert payload["model"] == "sarvam-105b-conversations"


def test_sanitize_tts_text_cleans_markdown_html_and_bullets():
    """Verify sanitize_tts_text strips markdown, HTML, bullet lists, and excessive punctuation."""
    raw = (
        "### Special Offer!\n"
        "- **Amul Gold Milk** (1L) for ₹54 at [Zepto](https://zepto.com).\n"
        "- *Fresh eggs* 6 pcs for ₹45! <br/>\n"
        "Would you like me to order them???"
    )
    cleaned = SarvamClient.sanitize_tts_text(raw)
    assert "###" not in cleaned
    assert "**" not in cleaned
    assert "*" not in cleaned
    assert "[Zepto]" not in cleaned
    assert "https://" not in cleaned
    assert "<br/>" not in cleaned
    assert "???" not in cleaned
    assert "Amul Gold Milk (1L) for ₹54 at Zepto" in cleaned
    assert "Would you like me to order them?" in cleaned


def test_sanitize_tts_text_enforces_character_budget():
    """Verify sanitize_tts_text truncates long paragraphs cleanly at <= max_chars (140)."""
    long_text = (
        "Namaste Ji, I have found five different kinds of organic milk in your local store, "
        "including cow milk, buffalo milk, toned milk, and skimmed milk with various discounts. "
        "Would you like me to add the first two packets to your cart right now?"
    )
    assert len(long_text) > 200
    cleaned = SarvamClient.sanitize_tts_text(long_text, max_chars=140)
    assert len(cleaned) <= 140
    assert cleaned.endswith(".") or cleaned.endswith("...") or cleaned.endswith("?")


@pytest.mark.asyncio
async def test_audio_cache_hit_bypasses_tts_api_call(monkeypatch):
    """Verify that identical TTS requests hit the in-memory LRU cache and make 0 HTTP calls."""
    sarvam_client.clear_audio_cache()
    requests = []

    async def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "request_id": "tts-cached-1",
                "audios": ["dGVzdC1hdWRpby1iYXNlNjQ="],
            },
        )

    install_mock_http_client(monkeypatch, handler)
    monkeypatch.setattr(sarvam_client, "api_key", "test-subscription-key")

    # First invocation -> cache miss -> 1 HTTP request
    audio1 = await sarvam_client.generate_speech_base64("Order placed successfully", language="en-IN")
    assert audio1 == "dGVzdC1hdWRpby1iYXNlNjQ="
    assert len(requests) == 1
    assert sarvam_client.get_audio_cache_size() == 1

    # Second invocation with exact same text -> cache hit -> 0 extra HTTP requests
    audio2 = await sarvam_client.generate_speech_base64("Order placed successfully", language="en-IN")
    assert audio2 == "dGVzdC1hdWRpby1iYXNlNjQ="
    assert len(requests) == 1  # Request count unchanged!

    # Third invocation with case and whitespace differences -> normalized cache hit -> 0 extra HTTP requests
    audio3 = await sarvam_client.generate_speech_base64("  order placed successfully  ", language="en-IN")
    assert audio3 == "dGVzdC1hdWRpby1iYXNlNjQ="
    assert len(requests) == 1  # Still 1 request!


@pytest.mark.asyncio
async def test_audio_cache_evicts_lru_when_capacity_exceeded(monkeypatch):
    """Verify that when cache exceeds max_size, the least-recently used entry is evicted."""
    client = SarvamClient()
    monkeypatch.setattr(client, "api_key", "test-subscription-key")
    client._audio_cache_max_size = 2  # Set small size to test LRU eviction

    async def handler(request):
        payload = json.loads(await request.aread())
        text = payload["inputs"][0]
        return httpx.Response(200, json={"audios": [f"audio_for_{text}"]})

    install_mock_http_client(monkeypatch, handler)

    await client.generate_speech_base64("One", language="en-IN")
    await client.generate_speech_base64("Two", language="en-IN")
    assert client.get_audio_cache_size() == 2
    assert "en-IN:one" in client._audio_cache
    assert "en-IN:two" in client._audio_cache

    # Adding a 3rd item should evict "en-IN:one" (the oldest / least recently used)
    await client.generate_speech_base64("Three", language="en-IN")
    assert client.get_audio_cache_size() == 2
    assert "en-IN:one" not in client._audio_cache
    assert "en-IN:two" in client._audio_cache
    assert "en-IN:three" in client._audio_cache


@pytest.mark.asyncio
async def test_audio_cache_language_isolation(monkeypatch):
    """Verify that identical text in different languages produces separate cache entries."""
    client = SarvamClient()
    monkeypatch.setattr(client, "api_key", "test-subscription-key")

    async def handler(request):
        payload = json.loads(await request.aread())
        lang = payload["target_language_code"]
        return httpx.Response(200, json={"audios": [f"audio_for_{lang}"]})

    install_mock_http_client(monkeypatch, handler)

    res_en = await client.generate_speech_base64("Namaste", language="en-IN")
    res_hi = await client.generate_speech_base64("Namaste", language="hi-IN")

    assert res_en == "audio_for_en-IN"
    assert res_hi == "audio_for_hi-IN"
    assert client.get_audio_cache_size() == 2
    assert "en-IN:namaste" in client._audio_cache
    assert "hi-IN:namaste" in client._audio_cache


def test_sanitize_tts_text_indic_sentence_boundaries():
    """Verify sanitize_tts_text cleanly terminates at Indic punctuation boundaries (Devanagari danda ।)."""
    long_hindi = (
        "नमस्ते जी, मैंने आपके लिए ताज़ा दूध और ब्रेड ढूंढ लिया है। "
        "क्या मैं इन्हें आपके कार्ट में जोड़ दूँ? कार्ट का कुल मूल्य अड़तालीस रुपये है।"
    )
    # With a budget of 80 chars, the first complete Hindi sentence ends at ~58 chars with ।
    cleaned = SarvamClient.sanitize_tts_text(long_hindi, max_chars=80)
    assert len(cleaned) <= 80
    assert cleaned.endswith("।")
    assert cleaned == "नमस्ते जी, मैंने आपके लिए ताज़ा दूध और ब्रेड ढूंढ लिया है।"


def test_sanitize_tts_text_strips_emojis_and_cleans_punctuation_spacing():
    """Verify emojis are stripped to prevent TTS billing on non-speech glyphs, and spacing is cleaned."""
    raw = "Namaste 🙏! Here is your fresh milk 🥛 and bread 🍞 ✅."
    cleaned = SarvamClient.sanitize_tts_text(raw)
    assert "🙏" not in cleaned
    assert "🥛" not in cleaned
    assert "🍞" not in cleaned
    assert "✅" not in cleaned
    assert cleaned == "Namaste! Here is your fresh milk and bread."


@pytest.mark.asyncio
async def test_generate_speech_returns_cached_bytes_when_unconfigured():
    """Verify generate_speech returns decoded audio from the LRU cache even in unconfigured/dev mode."""
    client = SarvamClient()
    fake_b64 = base64.b64encode(b"cached-wav-audio-content").decode("ascii")
    # Pre-populate cache
    client._audio_cache["en-IN:order confirmed"] = fake_b64

    # Even though unconfigured (mock dev key), cached audio must be returned
    audio_bytes = await client.generate_speech("Order confirmed", language="en-IN")
    assert audio_bytes == b"cached-wav-audio-content"


@pytest.mark.asyncio
async def test_generate_speech_base64_auto_detects_indic_scripts(monkeypatch):
    """Verify language='auto' routes Bengali and Tamil text to their respective language codes."""
    client = SarvamClient()
    monkeypatch.setattr(client, "api_key", "test-subscription-key")
    languages_called = []

    async def handler(request):
        payload = json.loads(await request.aread())
        languages_called.append(payload["target_language_code"])
        return httpx.Response(200, json={"audios": ["audio_b64"]})

    install_mock_http_client(monkeypatch, handler)

    # Bengali text with language='auto'
    await client.generate_speech_base64("আমাকে দুধ দিন", language="auto")
    assert languages_called[-1] == "bn-IN"

    # Tamil text with language='auto'
    await client.generate_speech_base64("எனக்கு பால் வேண்டும்", language="auto")
    assert languages_called[-1] == "ta-IN"

