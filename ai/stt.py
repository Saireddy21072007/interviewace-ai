"""
Speech-to-text - the only file that turns audio into words.

THREE TIERS, DELIBERATELY
-------------------------
1. faster-whisper (local)  - free, private, no key, ~1s per 10s of audio on CPU.
2. OpenAI Whisper API      - if a key is set and local Whisper is not installed.
3. Browser transcript      - the frontend already runs the Web Speech API while
                             recording, and posts that text alongside the audio.

Tier 3 is why the voice interview works on a fresh laptop with nothing
installed. The audio file is still uploaded and stored, so the same interview
can be re-transcribed later with a better model without asking the candidate to
repeat themselves - that is the reason we do not throw the audio away.

`transcribe()` never raises. A failed transcription returns text="" and an
explanation, and the interview continues.
"""

from __future__ import annotations

import io
import logging
import os
import struct
import wave
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_MODEL: Any = None
_MODEL_NAME: str | None = None


def describe() -> dict[str, Any]:
    """What the /health endpoint reports about speech input."""
    provider = os.getenv("STT_PROVIDER", "auto").lower()
    return {
        "configured": provider,
        "local_whisper_installed": _faster_whisper_available(),
        "openai_key_present": bool(os.getenv("OPENAI_API_KEY", "").strip()),
        "effective": _effective_provider(provider),
    }


def transcribe(
    audio: bytes,
    filename: str = "answer.webm",
    *,
    browser_transcript: str | None = None,
    language: str = "en",
) -> dict[str, Any]:
    """Audio bytes -> {text, provider, duration_sec, note}. Never raises."""
    provider = _effective_provider(os.getenv("STT_PROVIDER", "auto").lower())
    duration = estimate_duration(audio, filename)

    if provider == "faster-whisper":
        try:
            text = _faster_whisper(audio, filename, language)
            if text.strip():
                return {"text": text.strip(), "provider": "faster-whisper",
                        "duration_sec": duration, "note": ""}
            log.info("faster-whisper returned nothing; falling back.")
        except Exception as exc:  # noqa: BLE001
            log.warning("faster-whisper failed: %s", exc)

    elif provider == "openai-whisper":
        try:
            text = _openai_whisper(audio, filename, language)
            if text.strip():
                return {"text": text.strip(), "provider": "openai-whisper",
                        "duration_sec": duration, "note": ""}
        except Exception as exc:  # noqa: BLE001
            log.warning("OpenAI Whisper failed: %s", exc)

    if browser_transcript and browser_transcript.strip():
        return {
            "text": browser_transcript.strip(),
            "provider": "browser-web-speech",
            "duration_sec": duration,
            "note": "Transcribed in the browser. Install faster-whisper for better accuracy.",
        }

    return {
        "text": "",
        "provider": "none",
        "duration_sec": duration,
        "note": "No speech-to-text engine was available and the browser sent no transcript. "
                "Type your answer instead, or install faster-whisper.",
    }


# --------------------------------------------------------------------------- #
# Engines
# --------------------------------------------------------------------------- #


def _effective_provider(configured: str) -> str:
    if configured == "none":
        return "none"
    if configured in ("faster-whisper", "openai-whisper"):
        return configured
    if _faster_whisper_available():
        return "faster-whisper"
    if os.getenv("OPENAI_API_KEY", "").strip():
        return "openai-whisper"
    return "none"


def _faster_whisper_available() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def _faster_whisper(audio: bytes, filename: str, language: str) -> str:
    """Local Whisper. The model is loaded once and cached for the process."""
    global _MODEL, _MODEL_NAME
    from faster_whisper import WhisperModel  # type: ignore

    wanted = os.getenv("WHISPER_MODEL", "base.en")
    if _MODEL is None or _MODEL_NAME != wanted:
        log.info("Loading faster-whisper model %r (first call only)...", wanted)
        _MODEL = WhisperModel(wanted, device="cpu", compute_type="int8")
        _MODEL_NAME = wanted

    # faster-whisper needs a real path; ffmpeg reads webm/ogg/wav from there.
    temp_path = Path(os.getenv("STORAGE_DIR", "./storage")) / "tmp"
    temp_path.mkdir(parents=True, exist_ok=True)
    file_path = temp_path / f"stt_{abs(hash(audio)) % 10**12}{Path(filename).suffix or '.webm'}"
    file_path.write_bytes(audio)
    try:
        segments, _info = _MODEL.transcribe(
            str(file_path),
            language=None if language == "auto" else language,
            vad_filter=True,
        )
        return " ".join(segment.text.strip() for segment in segments)
    finally:
        file_path.unlink(missing_ok=True)


def _openai_whisper(audio: bytes, filename: str, language: str) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))
    buffer = io.BytesIO(audio)
    buffer.name = filename or "answer.webm"
    response = client.audio.transcriptions.create(
        model="whisper-1",
        file=buffer,
        language=None if language == "auto" else language,
    )
    return response.text or ""


# --------------------------------------------------------------------------- #
# Duration - used by the evaluator to compute speaking pace
# --------------------------------------------------------------------------- #


def estimate_duration(audio: bytes, filename: str = "") -> float | None:
    """Best-effort clip length in seconds.

    WAV is read exactly from its header. WebM/Ogg would need a full demuxer, so
    we return None and let the browser tell us how long it recorded - it knows
    precisely, and it is not worth a dependency to re-derive it here.
    """
    suffix = Path(filename).suffix.lower()
    if suffix == ".wav" or audio[:4] == b"RIFF":
        try:
            with wave.open(io.BytesIO(audio)) as handle:
                return round(handle.getnframes() / float(handle.getframerate()), 2)
        except (wave.Error, EOFError, struct.error):
            return None
    return None
