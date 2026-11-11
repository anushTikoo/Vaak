import io
import subprocess
import wave

from src.utils.audio_validator import inspect_audio, is_audio_container


def test_is_audio_container_detection():
    # Negative cases
    assert is_audio_container(b"") is False
    assert is_audio_container(b"plain text payload") is False

    # Positive cases
    assert is_audio_container(b"\x00\x00\x00\x1cftypM4A ") is True
    assert is_audio_container(b"RIFF\x24\x00\x00\x00WAVEfmt ") is True
    assert is_audio_container(b"ID3\x04\x00\x00\x00") is True
    assert is_audio_container(b"OggS\x00\x02\x00\x00") is True


def test_inspect_audio_empty_payload():
    result = inspect_audio(b"")
    assert result.is_valid is False
    assert result.duration == 0.0
    assert result.reason == "empty_payload"


def test_inspect_audio_unparsed_test_payload():
    # Arbitrary strings used in mock unit tests should pass through
    result = inspect_audio(b"test audio bytes")
    assert result.is_valid is True
    assert result.duration == 1.0
    assert result.reason == "unparsed_test_payload"


def test_inspect_audio_zero_duration_wav():
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"")  # 0 frames -> 0.0 seconds

    result = inspect_audio(buf.getvalue(), "zero.wav")
    assert result.is_valid is False
    assert result.duration == 0.0
    assert result.reason == "zero_duration"


def test_inspect_audio_valid_wav():
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * 16000)  # 1 second

    result = inspect_audio(buf.getvalue(), "valid.wav")
    assert result.is_valid is True
    assert result.duration == 1.0
    assert result.reason == "ok"


def test_inspect_audio_zero_duration_m4a():
    import os
    import tempfile

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
            data = f.read()
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    assert len(data) > 0
    result = inspect_audio(data, "empty.m4a")
    assert result.is_valid is False
    assert result.duration <= 0.05
    assert result.reason in ("zero_duration", "unable_to_verify_duration")


def test_inspect_audio_valid_webm():
    import os
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        proc = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=1000:duration=2.0",
                "-c:a",
                "libopus",
                tmp_path,
            ],
            capture_output=True,
        )
        assert proc.returncode == 0
        with open(tmp_path, "rb") as f:
            data = f.read()
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    # Even if client uploaded it with filename 'recording.m4a', it should be correctly identified as WebM and valid
    result = inspect_audio(data, "recording.m4a")
    assert result.is_valid is True
    assert result.duration >= 1.5
    assert result.reason in ("ok", "valid_by_payload_size")


def test_inspect_audio_zero_duration_webm():
    import os
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        proc = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=1000:duration=0.01",
                "-c:a",
                "libopus",
                tmp_path,
            ],
            capture_output=True,
        )
        assert proc.returncode == 0
        with open(tmp_path, "rb") as f:
            data = f.read()
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    result = inspect_audio(data, "recording.m4a")
    assert result.is_valid is False
    assert result.duration <= 0.05
    assert result.reason in ("zero_duration", "unable_to_verify_duration")

