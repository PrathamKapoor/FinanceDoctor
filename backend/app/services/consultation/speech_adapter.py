"""Speech provider abstraction (Stage 7A).

Verified capability boundary (MiniMax platform docs, 2026):
- TTS: synchronous HTTP T2A ``POST {base}/t2a_v2`` with models
  ``speech-2.8-hd`` / ``speech-2.8-turbo``, Bearer auth, hex-encoded audio in
  ``data.audio``, ``base_resp.status_code == 0`` on success. IMPLEMENTED.
- STT: no public first-party speech-to-text endpoint could be verified, so
  voice input is NOT offered. The UI uses typed questions. NOT FAKED.

``StubSpeechAdapter`` (default) synthesizes a short deterministic WAV beep in
code — an explicit placeholder, never presented as MiniMax audio — so the
demo exercises Question → Answer → Audio playback with zero credentials.
"""

from __future__ import annotations

import base64
import math
import os
import struct
from typing import Any, Protocol, runtime_checkable

import httpx
from pydantic import BaseModel, Field

from backend.app.services.consultation.models import SpeechResult


class SpeechError(Exception):
    """Speech synthesis failure (provider error, timeout, bad payload)."""


class SpeechConfig(BaseModel):
    """Speech provider configuration (env-driven, backend-only)."""

    provider: str = Field(default="stub", description='"stub" or "minimax"')
    api_key: str = Field(default="", description="MiniMax API key (env only)")
    base_url: str = Field(default="https://api.minimax.chat/v1")
    group_id: str = Field(default="")
    model: str = Field(default="speech-2.8-turbo")
    voice_id: str = Field(default="English_expressive_narrator")
    timeout_seconds: float = 60.0
    max_chars: int = 2000

    @classmethod
    def from_env(cls) -> SpeechConfig:
        return cls(
            provider=os.getenv("SPEECH_PROVIDER", "stub").lower(),
            api_key=os.getenv("MINIMAX_API_KEY", ""),
            base_url=os.getenv(
                "MINIMAX_BASE_URL", "https://api.minimax.chat/v1"
            ),
            group_id=os.getenv("MINIMAX_GROUP_ID", ""),
            model=os.getenv("SPEECH_MODEL", "speech-2.8-turbo"),
            voice_id=os.getenv("SPEECH_VOICE_ID", "English_expressive_narrator"),
        )


@runtime_checkable
class SpeechProvider(Protocol):
    """Provider-independent speech synthesis."""

    @property
    def name(self) -> str: ...

    @property
    def capabilities(self) -> dict[str, bool]:
        """E.g. {"tts": True, "stt": False} — STT is never claimed."""
        ...

    async def synthesize(self, text: str, *, voice_id: str | None = None) -> SpeechResult: ...


def _sine_beep_wav(
    duration_s: float = 0.6, freq_hz: float = 440.0, sample_rate: int = 16000
) -> bytes:
    """Deterministic placeholder audio: 16-bit mono PCM WAV sine with fades."""
    n = int(duration_s * sample_rate)
    frames = bytearray()
    for i in range(n):
        t = i / sample_rate
        envelope = min(1.0, i / (0.05 * sample_rate), (n - i) / (0.05 * sample_rate))
        sample = int(12000 * envelope * math.sin(2 * math.pi * freq_hz * t))
        frames += struct.pack("<h", sample)
    pcm = bytes(frames)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + len(pcm), b"WAVE", b"fmt ", 16,
        1, 1, sample_rate, sample_rate * 2, 2, 16, b"data", len(pcm),
    )
    return header + pcm


class StubSpeechAdapter:
    """Deterministic placeholder speech. Clearly labeled ``provider="stub"``."""

    def __init__(self, config: SpeechConfig | None = None) -> None:
        self._config = config or SpeechConfig()

    @property
    def name(self) -> str:
        return "stub"

    @property
    def capabilities(self) -> dict[str, bool]:
        return {"tts": True, "stt": False}

    async def synthesize(self, text: str, *, voice_id: str | None = None) -> SpeechResult:
        if not text or not text.strip():
            raise SpeechError("Nothing to synthesize")
        wav = _sine_beep_wav()
        return SpeechResult(
            mime_type="audio/wav",
            data_base64=base64.b64encode(wav).decode("ascii"),
            byte_size=len(wav),
            duration_ms=600,
            provider="stub",
            voice=voice_id or self._config.voice_id,
        )


class MiniMaxSpeechAdapter:
    """Live MiniMax Speech 2.8 TTS via the verified HTTP T2A contract."""

    def __init__(
        self,
        config: SpeechConfig,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not config.api_key:
            raise SpeechError("MiniMax speech requires MINIMAX_API_KEY")
        self._config = config
        self._transport = transport

    @property
    def name(self) -> str:
        return "minimax"

    @property
    def capabilities(self) -> dict[str, bool]:
        return {"tts": True, "stt": False}

    def _url(self) -> str:
        url = self._config.base_url.rstrip("/") + "/t2a_v2"
        if self._config.group_id:
            url += f"?GroupId={self._config.group_id}"
        return url

    def _payload(self, text: str, voice_id: str | None) -> dict[str, Any]:
        return {
            "model": self._config.model,
            "text": text,
            "stream": False,
            "voice_setting": {
                "voice_id": voice_id or self._config.voice_id,
                "speed": 1.0,
                "vol": 1,
                "pitch": 0,
            },
            "audio_setting": {
                "sample_rate": 32000,
                "bitrate": 128000,
                "format": "mp3",
                "channel": 1,
            },
            "language_boost": "English",
            "output_format": "hex",
        }

    async def synthesize(self, text: str, *, voice_id: str | None = None) -> SpeechResult:
        body = (text or "").strip()
        if not body:
            raise SpeechError("Nothing to synthesize")
        if len(body) > self._config.max_chars:
            raise SpeechError(
                f"Text exceeds {self._config.max_chars} characters for speech"
            )
        try:
            async with httpx.AsyncClient(
                timeout=self._config.timeout_seconds, transport=self._transport
            ) as client:
                resp = await client.post(
                    self._url(),
                    headers={
                        "Authorization": f"Bearer {self._config.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=self._payload(body, voice_id),
                )
        except httpx.HTTPError as exc:
            raise SpeechError(f"MiniMax TTS request failed: {exc}") from exc
        if resp.status_code != 200:
            raise SpeechError(f"MiniMax TTS HTTP {resp.status_code}")
        try:
            data = resp.json()
        except ValueError as exc:
            raise SpeechError("MiniMax TTS returned non-JSON") from exc
        base_resp = data.get("base_resp") or {}
        if base_resp.get("status_code", 0) != 0:
            raise SpeechError(
                f"MiniMax TTS error {base_resp.get('status_code')}: "
                f"{base_resp.get('status_msg', '')}"
            )
        audio_hex = (data.get("data") or {}).get("audio") or ""
        if not audio_hex:
            raise SpeechError("MiniMax TTS returned no audio")
        try:
            audio = bytes.fromhex(audio_hex)
        except ValueError as exc:
            raise SpeechError("MiniMax TTS returned malformed audio") from exc
        extra = data.get("extra_info") or {}
        return SpeechResult(
            mime_type="audio/mpeg",
            data_base64=base64.b64encode(audio).decode("ascii"),
            byte_size=len(audio),
            duration_ms=extra.get("audio_length"),
            provider="minimax",
            voice=voice_id or self._config.voice_id,
        )


def create_speech_provider(config: SpeechConfig | None = None) -> SpeechProvider:
    """Select stub (default, zero credentials) or live MiniMax TTS."""
    config = config or SpeechConfig.from_env()
    if config.provider == "minimax":
        return MiniMaxSpeechAdapter(config)
    return StubSpeechAdapter(config)


__all__ = [
    "MiniMaxSpeechAdapter",
    "SpeechConfig",
    "SpeechError",
    "SpeechProvider",
    "StubSpeechAdapter",
    "create_speech_provider",
]
