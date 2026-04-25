"""TTS service — OpenAI first (via Emergent LLM key), deterministic mock fallback.

Designed for ElevenLabs to drop in later by extending `PROVIDERS` and `_provider_name()`.

Public API:
    await generate_voiceover(
        text,
        voice_style,
        project_id,
        asset_id=None,        # pre-generated uuid for file path
        scene_id=None,        # if scene-level
    ) -> dict

Returned dict is a normalised asset ready to be inserted in db.assets.
"""
from __future__ import annotations

import logging
import os
import re
import struct
import uuid
import wave
from pathlib import Path

from .storage import get_storage

logger = logging.getLogger("facelessforge.tts")

STATIC_ROOT = Path(__file__).parent.parent / "static" / "audio"
STATIC_ROOT.mkdir(parents=True, exist_ok=True)

# Voice style → OpenAI TTS voice name. Keep same keys for ElevenLabs later.
VOICE_STYLE_MAP = {
    "narrator":     {"openai_voice": "onyx",    "eleven_voice_hint": "narrative, low, male"},
    "energetic":    {"openai_voice": "nova",    "eleven_voice_hint": "bright, upbeat"},
    "documentary":  {"openai_voice": "sage",    "eleven_voice_hint": "neutral, measured"},
    "calm":         {"openai_voice": "alloy",   "eleven_voice_hint": "warm, smooth"},
    "dramatic":     {"openai_voice": "fable",   "eleven_voice_hint": "theatrical, bold"},
    "corporate":    {"openai_voice": "echo",    "eleven_voice_hint": "professional, even"},
    "mysterious":   {"openai_voice": "shimmer", "eleven_voice_hint": "breathy, intimate"},
}

SUPPORTED_STYLES = list(VOICE_STYLE_MAP.keys())

MAX_TEXT_CHARS = 5000


def _use_mock() -> bool:
    key = os.environ.get("EMERGENT_LLM_KEY", "").strip() or os.environ.get("OPENAI_API_KEY", "").strip()
    flag = os.environ.get("USE_MOCK_TTS", "true").strip().lower() in ("1", "true", "yes")
    return flag or not key


def is_mock_mode() -> bool:
    return _use_mock()


def provider_info() -> dict:
    return {
        "mock": _use_mock(),
        "provider": os.environ.get("TTS_PROVIDER", "openai"),
        "model": os.environ.get("OPENAI_TTS_MODEL", "tts-1"),
        "voices": SUPPORTED_STYLES,
        "default_voice_style": os.environ.get("DEFAULT_VOICE_STYLE", "narrator"),
    }


# ---------------- Mock audio ----------------

def _estimate_duration_seconds(text: str) -> int:
    words = len(re.findall(r"\b\w+\b", text or ""))
    return max(2, int(round(words / 2.5)))  # ~150 wpm narration


def _write_mock_wav(path: Path, duration_s: int) -> None:
    """Write a valid PCM WAV of silence with the requested duration."""
    sample_rate = 22050
    n_samples = int(sample_rate * max(1, duration_s))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        # Write silence in chunks to avoid huge memory
        chunk = b"\x00\x00" * 4096
        remaining = n_samples
        while remaining > 0:
            take = min(4096, remaining)
            w.writeframes(chunk[:take * 2])
            remaining -= take


# ---------------- Real OpenAI path ----------------

def _openai_voice_for(style: str) -> str:
    return VOICE_STYLE_MAP.get(style, VOICE_STYLE_MAP["narrator"])["openai_voice"]


async def _openai_tts(text: str, style: str, out_path: Path) -> tuple[bool, int]:
    """Try to call OpenAI TTS via Emergent-friendly OpenAI SDK.

    Returns (ok, duration_seconds_estimate). On any failure returns (False, est).
    """
    api_key = os.environ.get("EMERGENT_LLM_KEY", "") or os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return False, _estimate_duration_seconds(text)
    model = os.environ.get("OPENAI_TTS_MODEL", "tts-1")
    voice = _openai_voice_for(style)
    try:
        # Lazy import so a missing SDK never breaks mock path.
        from openai import OpenAI
        base_url = os.environ.get("OPENAI_BASE_URL") or None
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        client = OpenAI(**kwargs)
        # text is clamped upstream
        response = client.audio.speech.create(model=model, voice=voice, input=text)
        # Save binary MP3
        response.stream_to_file(str(out_path))
        return True, _estimate_duration_seconds(text)
    except Exception as e:  # noqa: BLE001
        logger.warning("OpenAI TTS failed (%s). Falling back to mock audio.", e)
        return False, _estimate_duration_seconds(text)


# ---------------- Public ----------------

async def generate_voiceover(
    *,
    text: str,
    voice_style: str,
    project_id: str,
    asset_id: str | None = None,
    scene_id: str | None = None,
    name_suffix: str = "",
) -> dict:
    if not text or not text.strip():
        raise ValueError("empty_text")
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS]
    if voice_style not in VOICE_STYLE_MAP:
        voice_style = os.environ.get("DEFAULT_VOICE_STYLE", "narrator")

    aid = asset_id or str(uuid.uuid4())
    info = provider_info()
    dir_path = STATIC_ROOT / project_id
    dir_path.mkdir(parents=True, exist_ok=True)

    ext = "wav"
    source = "mock_tts"
    duration = _estimate_duration_seconds(text)

    use_real = not _use_mock()
    real_ok = False
    if use_real:
        out_path = dir_path / f"{aid}.mp3"
        real_ok, duration = await _openai_tts(text, voice_style, out_path)
        if real_ok:
            ext = "mp3"
            source = "openai_tts"
    if not real_ok:
        out_path = dir_path / f"{aid}.wav"
        _write_mock_wav(out_path, duration)

    # Persist via storage backend (local: no-op; object: upload + remove local)
    store = get_storage()
    key = f"audio/{project_id}/{aid}.{ext}"
    content_type = "audio/mpeg" if ext == "mp3" else "audio/wav"
    saved = store.save_file(out_path, key, content_type=content_type)

    return {
        "id": aid,
        "project_id": project_id,
        "scene_id": scene_id,
        "asset_type": "voiceover_audio",
        "source": source,
        "name": (f"Voiceover {name_suffix}" if name_suffix else "Voiceover") + (" (mock)" if source == "mock_tts" else ""),
        "text_source": "scene_narration" if scene_id else "full_script",
        "voice_style": voice_style,
        "provider": info["provider"] if source != "mock_tts" else "mock_tts",
        "model": info["model"] if source != "mock_tts" else None,
        "duration": duration,
        "file_path": str(saved.file_path) if saved.file_path else None,
        "preview_url": saved.url,
        "preview_path": saved.preview_path,
        "storage_mode": store.mode,
        "storage_key": saved.key,
        "width": None,
        "height": None,
        "tags": ["voiceover", voice_style],
        "mock": source == "mock_tts",
        "status": "generated",
        "cost_estimate": round(len(text) / 1000 * 0.015, 4) if source == "openai_tts" else 0.0,
    }
