"""Builds one voice note.

Every part (intro, steps, recap, safety, close) is synthesised by Bulbul in parallel, then played back in order
with silences in between. Bulbul's stream is plain 24 kHz mono CBR MP3 frames, and the silence is encoded to the
same format, so the parts can be concatenated byte for byte: the browser plays the note while it is still being
generated, and the same bytes become the shareable file.
"""

import asyncio
import logging
import re
import subprocess
import tempfile
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

from . import config, tts

log = logging.getLogger("samjhao.audio")

JOB_TTL_SECONDS = 30 * 60
MAX_PARALLEL_TTS = 4
BYTES_PER_SECOND = 128_000 / 8


@dataclass
class Part:
    kind: str
    text: str
    pace: float
    pause: float
    chunks: list[bytes] = field(default_factory=list)
    done: bool = False
    error: str | None = None


@dataclass
class Job:
    id: str
    language: str
    speaker: str
    filename: str
    parts: list[Part]
    created: float = field(default_factory=time.monotonic)
    state: str = "generating"
    ttfb_ms: float | None = None
    error: str | None = None
    file: bytes | None = None
    changed: asyncio.Condition = field(default_factory=asyncio.Condition)
    task: asyncio.Task | None = None

    def status(self) -> dict:
        return {
            "state": self.state,
            "ttfb_ms": round(self.ttfb_ms) if self.ttfb_ms is not None else None,
            "duration_s": round(len(self.file) / BYTES_PER_SECOND, 1) if self.file else None,
            "file_url": f"/api/audio/{self.id}/file" if self.file else None,
            "filename": self.filename,
            "error": self.error,
        }


JOBS: dict[str, Job] = {}
_job_added = asyncio.Event()


@cache
def silence(seconds: float) -> bytes:
    """MP3 silence in exactly Bulbul's frame format (MPEG-2 Layer III, 24 kHz, mono, 128k CBR, no headers)."""
    out = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", f"anullsrc=r={config.TTS_SAMPLE_RATE}:cl=mono",
         "-t", str(seconds), "-c:a", "libmp3lame", "-b:a", tts.MP3_BITRATE, "-write_xing", "0", "-id3v2_version", "0", "-f", "mp3", "-"],
        capture_output=True, check=True,
    )
    return out.stdout


def _sentence(text: str, language: str) -> str:
    """Trim and make sure the text ends like a sentence, so Bulbul closes the intonation."""
    text = re.sub(r"\s+", " ", text).strip()
    if text and text[-1] not in ".!?।":
        text += "." if language == "en-IN" or text[-1].isascii() else "।"
    return text


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:50] or "voice-note"


def build_parts(script: dict, language: str) -> list[Part]:
    parts = [Part("intro", _sentence(script["intro"], language), config.INTRO_PACE, config.PAUSE_AFTER_INTRO)]
    for i, step in enumerate(script["steps"][: config.MAX_STEPS]):
        text = f"{config.step_label(language, i)}. {_sentence(step, language)}"
        parts.append(Part("step", text, config.TTS_PACE, config.PAUSE_AFTER_STEP))
    if script.get("recap"):
        parts.append(Part("recap", _sentence(script["recap"], language), config.TTS_PACE, config.PAUSE_AFTER_RECAP))
    if script.get("safety"):
        parts.append(Part("safety", _sentence(script["safety"], language), config.TTS_PACE, config.PAUSE_AFTER_SAFETY))
    if script.get("close"):
        parts.append(Part("close", _sentence(script["close"], language), config.TTS_PACE, 0))
    return [p for p in parts if p.text]


def create_job(job_id: str, script: dict, language: str, voice: str) -> Job:
    _cleanup()
    voices = config.VOICES[language]
    speaker = voices.get(voice) or next(iter(voices.values()))
    title = _slug(script.get("title") or "voice note")
    filename = f"samjhao-{title}-{config.LANGUAGES[language]['name'].lower()}.mp3"
    job = Job(job_id, language, speaker, filename, build_parts(script, language))
    JOBS[job_id] = job
    _job_added.set()
    _job_added.clear()
    job.task = asyncio.create_task(_run(job))  # keep a reference so the task isn't garbage-collected
    return job


async def get_job(job_id: str, wait: float = 0) -> Job | None:
    """The browser asks for the stream in the same tap that creates the job, so the stream may arrive first."""
    deadline = time.monotonic() + wait
    while job_id not in JOBS and time.monotonic() < deadline:
        try:
            await asyncio.wait_for(_job_added.wait(), timeout=max(0.01, deadline - time.monotonic()))
        except asyncio.TimeoutError:
            break
    return JOBS.get(job_id)


async def _synthesise(job: Job, part: Part, sem: asyncio.Semaphore, first_audio: asyncio.Event | None = None) -> None:
    async with sem:
        for attempt in range(2):
            t0 = time.perf_counter()
            try:
                async for chunk in tts.stream(part.text, job.language, job.speaker, part.pace):
                    if first_audio is not None and job.ttfb_ms is None:
                        job.ttfb_ms = (time.perf_counter() - t0) * 1000
                        first_audio.set()
                    async with job.changed:
                        part.chunks.append(chunk)
                        job.changed.notify_all()
                break
            except Exception as e:  # retry once with a clean slate, then give up on this part
                log.warning("TTS failed for %s part (attempt %d): %s", part.kind, attempt + 1, e)
                if part.chunks or attempt == 1:
                    part.error = str(e)
                    break
                await asyncio.sleep(0.4)
    async with job.changed:
        part.done = True
        job.changed.notify_all()


async def _run(job: Job) -> None:
    sem = asyncio.Semaphore(MAX_PARALLEL_TTS)
    first_audio = asyncio.Event()
    intro = asyncio.create_task(_synthesise(job, job.parts[0], sem, first_audio))
    # Start the rest only once the intro is flowing, so they don't compete with the first-sound latency.
    try:
        await asyncio.wait_for(first_audio.wait(), timeout=3)
    except asyncio.TimeoutError:
        pass
    await asyncio.gather(intro, *[_synthesise(job, p, sem) for p in job.parts[1:]])

    failed = [p.kind for p in job.parts if p.error]
    if failed:
        job.state, job.error = "error", f"Couldn't generate the {', '.join(failed)} audio. Please try again."
        return
    raw = b"".join(b"".join(p.chunks) + (silence(p.pause) if p.pause else b"") for p in job.parts)
    job.file = await asyncio.to_thread(_with_header, raw)
    job.state = "ready"


def _with_header(raw: bytes) -> bytes:
    """Remux (no re-encode) to add a Xing header, so phones show the right duration. Falls back to the raw bytes."""
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = Path(tmp) / "in.mp3", Path(tmp) / "out.mp3"
        src.write_bytes(raw)
        r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "mp3", "-i", str(src), "-c:a", "copy",
                            "-id3v2_version", "0", "-write_xing", "1", str(dst)], capture_output=True)
        return dst.read_bytes() if r.returncode == 0 and dst.exists() else raw


async def stream(job: Job) -> AsyncIterator[bytes]:
    """Yield the voice note in order, as soon as each part's audio is available."""
    for part in job.parts:
        sent = 0
        while True:
            async with job.changed:
                await job.changed.wait_for(lambda: len(part.chunks) > sent or part.done)
                new = part.chunks[sent:]
                finished = part.done
            for chunk in new:
                yield chunk
            sent += len(new)
            if finished and sent == len(part.chunks):
                break
        if part.pause and not part.error:
            yield silence(part.pause)


def _cleanup() -> None:
    cutoff = time.monotonic() - JOB_TTL_SECONDS
    for job_id in [k for k, j in JOBS.items() if j.created < cutoff]:
        del JOBS[job_id]
