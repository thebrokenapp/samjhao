"""Bulbul v4 Flash text-to-speech over Sarvam's HTTP streaming endpoint."""

import os
from collections.abc import AsyncIterator

import httpx
from dotenv import load_dotenv

from . import config

load_dotenv()

STREAM_URL = "https://api.sarvam.ai/text-to-speech/stream"
MP3_BITRATE = "128k"


class TTSError(Exception):
    def __init__(self, status: int, body: str):
        super().__init__(f"Bulbul returned {status}: {body[:300]}")
        self.status = status
        self.body = body


_client: httpx.AsyncClient | None = None


def client() -> httpx.AsyncClient:
    """One pooled client so successive calls reuse the warm TLS connection."""
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(60, connect=10),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10, keepalive_expiry=120),
        )
    return _client


def _headers() -> dict:
    key = os.environ.get("SARVAM_API_KEY")
    if not key:
        raise RuntimeError("SARVAM_API_KEY is not set (see .env.example)")
    return {"api-subscription-key": key, "Content-Type": "application/json"}


def request_body(text: str, language: str, speaker: str, pace: float = config.TTS_PACE) -> dict:
    return {
        "text": text,
        "language_code": language,
        "model": config.TTS_MODEL,
        "speaker": speaker,
        "speech_sample_rate": config.TTS_SAMPLE_RATE,
        "output_audio_codec": "mp3",
        "output_audio_bitrate": MP3_BITRATE,
        "pace": pace,
        "enable_preprocessing": True,
    }


async def warm() -> None:
    """Open (or keep alive) a pooled connection to api.sarvam.ai so the next call skips the TLS handshake."""
    try:
        await client().get("https://api.sarvam.ai/", timeout=5)
    except httpx.HTTPError:
        pass


async def stream(text: str, language: str, speaker: str, pace: float = config.TTS_PACE) -> AsyncIterator[bytes]:
    """Yield MP3 bytes (24 kHz mono CBR frames, no headers) as Bulbul produces them."""
    body = request_body(text, language, speaker, pace)
    async with client().stream("POST", STREAM_URL, json=body, headers=_headers()) as r:
        if r.status_code != 200:
            body = (await r.aread()).decode("utf-8", "replace")
            raise TTSError(r.status_code, body)
        async for chunk in r.aiter_bytes():
            if chunk:
                yield chunk
