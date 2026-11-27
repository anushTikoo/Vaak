from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from src.services.sarvam.client import sarvam_client


@pytest.mark.asyncio
async def test_create_voice_session_echoes_requested_language(client):
    response = await client.post("/api/v1/voice/session", json={"language_code": "hi-IN"})

    assert response.status_code == 200
    data = response.json()
    UUID(data["session_id"])
    assert data["ws_endpoint"] == "/api/v1/voice/stream"
    assert data["status"] == "ready"
    assert data["active_language"] == "hi-IN"


@pytest.mark.asyncio
async def test_create_voice_session_defaults_to_auto_language(client):
    response = await client.post("/api/v1/voice/session", json={})

    assert response.status_code == 200
    assert response.json()["active_language"] == "auto"


@pytest.mark.asyncio
async def test_transcribe_forwards_audio_and_returns_provider_result(client, monkeypatch):
    audio_bytes = b"test audio bytes"
    transcribe = AsyncMock(
        return_value={
            "transcript": "Do litre dudh",
            "detected_language": "hi-IN",
            "confidence": 0.91,
        }
    )
    monkeypatch.setattr(sarvam_client, "transcribe_audio", transcribe)

    response = await client.post(
        "/api/v1/voice/transcribe",
        files={"audio": ("utterance.wav", audio_bytes, "audio/wav")},
    )

    assert response.status_code == 200
    data = response.json()
    UUID(data["session_id"])
    assert data["transcript"] == "Do litre dudh"
    assert data["detected_language"] == "hi-IN"
    assert data["confidence"] == 0.91
    transcribe.assert_awaited_once_with(audio_bytes)


@pytest.mark.asyncio
async def test_transcribe_uses_safe_defaults_for_optional_provider_fields(client, monkeypatch):
    transcribe = AsyncMock(return_value={"transcript": "Hello"})
    monkeypatch.setattr(sarvam_client, "transcribe_audio", transcribe)

    response = await client.post(
        "/api/v1/voice/transcribe",
        files={"audio": ("utterance.m4a", b"audio", "audio/mp4")},
    )

    assert response.status_code == 200
    assert response.json()["transcript"] == "Hello"
    assert response.json()["detected_language"] is None
    assert response.json()["confidence"] == 0.0


@pytest.mark.asyncio
async def test_transcribe_requires_audio_upload(client):
    response = await client.post("/api/v1/voice/transcribe")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_transcribe_handles_sarvam_400_bad_request_gracefully(client, monkeypatch):
    import httpx

    req = httpx.Request("POST", "https://api.sarvam.ai/speech-to-text")
    resp = httpx.Response(400, request=req, text='{"error":{"message":"Audio duration is 0, please check the audio."}}')
    error = httpx.HTTPStatusError("Client error 400 Bad Request", request=req, response=resp)

    transcribe = AsyncMock(side_effect=error)
    monkeypatch.setattr(sarvam_client, "transcribe_audio", transcribe)

    response = await client.post(
        "/api/v1/voice/transcribe",
        files={"audio": ("empty.m4a", b"", "audio/mp4")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["transcript"] == ""
    assert data["confidence"] == 0.0
    assert data["detected_language"] == "en-IN"
    UUID(data["session_id"])
