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
