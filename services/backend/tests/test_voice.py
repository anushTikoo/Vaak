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
async def test_transcribe_handles_small_or_empty_audio_payload(client, monkeypatch):
    transcribe = AsyncMock()
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
    transcribe.assert_not_called()


@pytest.mark.asyncio
async def test_transcribe_rejects_zero_duration_audio_without_calling_provider(client, monkeypatch):
    import io
    import wave

    transcribe = AsyncMock()
    monkeypatch.setattr(sarvam_client, "transcribe_audio", transcribe)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"")

    response = await client.post(
        "/api/v1/voice/transcribe",
        files={"audio": ("zero_duration.wav", buf.getvalue(), "audio/wav")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["transcript"] == ""
    UUID(data["session_id"])
    transcribe.assert_not_called()


@pytest.mark.asyncio
async def test_transcribe_rejects_zero_duration_m4a_container_without_calling_provider(client, monkeypatch):
    import os
    import subprocess
    import tempfile

    transcribe = AsyncMock()
    monkeypatch.setattr(sarvam_client, "transcribe_audio", transcribe)

    with tempfile.NamedTemporaryFile(suffix=".m4a", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        proc = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=44100:cl=mono",
                "-t",
                "0.0",
                "-c:a",
                "aac",
                tmp_path,
            ],
            capture_output=True,
        )
        assert proc.returncode == 0
        with open(tmp_path, "rb") as f:
            zero_m4a_bytes = f.read()
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    assert len(zero_m4a_bytes) > 100

    response = await client.post(
        "/api/v1/voice/transcribe",
        files={"audio": ("recording.m4a", zero_m4a_bytes, "audio/m4a")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["transcript"] == ""
    UUID(data["session_id"])
    transcribe.assert_not_called()


@pytest.mark.asyncio
async def test_transcribe_allows_valid_duration_m4a_and_calls_provider(client, monkeypatch):
    import os
    import subprocess
    import tempfile

    transcribe = AsyncMock(
        return_value={
            "transcript": "two packets of milk",
            "detected_language": "en-IN",
            "confidence": 0.95,
        }
    )
    monkeypatch.setattr(sarvam_client, "transcribe_audio", transcribe)

    with tempfile.NamedTemporaryFile(suffix=".m4a", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        proc = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=44100:cl=mono",
                "-t",
                "1.0",
                "-c:a",
                "aac",
                tmp_path,
            ],
            capture_output=True,
        )
        assert proc.returncode == 0
        with open(tmp_path, "rb") as f:
            valid_m4a_bytes = f.read()
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    response = await client.post(
        "/api/v1/voice/transcribe",
        files={"audio": ("recording.m4a", valid_m4a_bytes, "audio/m4a")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["transcript"] == "two packets of milk"
    assert data["detected_language"] == "en-IN"
    transcribe.assert_awaited_once_with(valid_m4a_bytes)


@pytest.mark.asyncio
async def test_transcribe_handles_sarvam_400_bad_request_gracefully(client, monkeypatch):
    import httpx

    req = httpx.Request("POST", "https://api.sarvam.ai/speech-to-text")
    resp = httpx.Response(400, request=req, text='{"error":{"message":"Audio duration is 0, please check the audio."}}')
    error = httpx.HTTPStatusError("Client error 400 Bad Request", request=req, response=resp)

    transcribe = AsyncMock(side_effect=error)
    monkeypatch.setattr(sarvam_client, "transcribe_audio", transcribe)

    # 150 bytes so it passes the pre-validation guard and hits Sarvam client
    response = await client.post(
        "/api/v1/voice/transcribe",
        files={"audio": ("corrupt.m4a", b"A" * 150, "audio/mp4")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["transcript"] == ""
    assert data["confidence"] == 0.0
    assert data["detected_language"] == "en-IN"
    UUID(data["session_id"])


@pytest.mark.asyncio
async def test_simulate_voice_utterance(client):
    response = await client.post("/api/v1/voice/simulate?query=Add+milk+and+eggs")
    assert response.status_code == 200
    data = response.json()
    assert data["transcript"] == "Add milk and eggs"
    assert data["confidence"] == 1.0
    UUID(data["session_id"])


@pytest.mark.asyncio
async def test_text_to_speech_endpoint(client, monkeypatch):
    mock_gen = AsyncMock(return_value="UklGRgAAAABXQVZFZm10IBAAAAABAAEA")
    monkeypatch.setattr(sarvam_client, "generate_speech_base64", mock_gen)

    response = await client.post("/api/v1/voice/tts", json={"text": "Hello, your order is ready", "language": "en-IN"})
    assert response.status_code == 200
    data = response.json()
    assert data["audio_base64"] == "UklGRgAAAABXQVZFZm10IBAAAAABAAEA"
    assert data["format"] == "wav"
    mock_gen.assert_awaited_once_with("Hello, your order is ready", "en-IN")
