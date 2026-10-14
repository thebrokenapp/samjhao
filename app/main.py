"""Samjhao API: writes the steps (Sarvam-105B), speaks them (Bulbul v4 Flash), and serves the one-page app."""

import asyncio
import logging
import re
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator, model_validator

from . import audio, config, llm, tts

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("samjhao")

STATIC = Path(__file__).resolve().parent.parent / "static"


async def _keep_warm() -> None:
    """Keep a TLS connection to api.sarvam.ai open so the first Bulbul call of a demo is as fast as the rest."""
    with suppress(Exception):
        await llm.write_script("how to make a phone call", "hi-IN", "maa", None, "android", "female")
    while True:
        await tts.warm()
        await asyncio.sleep(20)


@asynccontextmanager
async def lifespan(_: FastAPI):
    for seconds in {config.PAUSE_AFTER_INTRO, config.PAUSE_AFTER_STEP, config.PAUSE_AFTER_RECAP, config.PAUSE_AFTER_SAFETY}:
        audio.silence(seconds)
    warmer = asyncio.create_task(_keep_warm())
    yield
    warmer.cancel()
    await llm.aclose()


app = FastAPI(title="Samjhao", lifespan=lifespan)


class Script(BaseModel):
    title: str = Field("", max_length=120)
    intro: str = Field(min_length=1, max_length=1500)
    steps: list[str] = Field(min_length=1)
    recap: str = Field("", max_length=1500)
    safety: str | None = Field(None, max_length=1000)
    close: str = Field("", max_length=800)
    note: str | None = Field(None, max_length=500)

    @field_validator("steps")
    @classmethod
    def _steps(cls, steps: list[str]) -> list[str]:
        steps = [s.strip() for s in steps if s and s.strip()]
        if not steps:
            raise ValueError("add at least one step")
        if len(steps) > config.MAX_STEPS:
            raise ValueError(f"at most {config.MAX_STEPS} steps")
        if any(len(s) > 1200 for s in steps):
            raise ValueError("a step is too long")
        return steps


class Audience(BaseModel):
    language: str
    relation: str = "maa"
    custom_name: str | None = Field(None, max_length=40)
    phone: str = "android"
    voice: str = "female"

    @model_validator(mode="after")
    def _check(self):
        if self.language not in config.LANGUAGES:
            raise ValueError("unsupported language")
        if self.relation not in config.RELATIONS:
            raise ValueError("unknown relation")
        if self.relation == "custom" and not (self.custom_name or "").strip():
            raise ValueError("enter a name")
        if self.phone not in config.PHONES:
            raise ValueError("unknown phone")
        if self.voice not in ("female", "male"):
            raise ValueError("unknown voice")
        return self

    def narrator(self) -> str:
        """The voice that will actually speak: falls back when a language lacks the chosen gender (Tamil has no female voice)."""
        voices = config.VOICES[self.language]
        return self.voice if self.voice in voices else next(iter(voices))


class ScriptRequest(Audience):
    task: str = Field(min_length=3, max_length=300)


class TranslateRequest(Audience):
    script: Script


class AudioRequest(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9-]{8,64}$")
    language: str
    voice: str = "female"
    script: Script

    @model_validator(mode="after")
    def _check(self):
        if self.language not in config.LANGUAGES:
            raise ValueError("unsupported language")
        return self


@app.get("/api/config")
def get_config():
    return {
        "languages": [
            {
                "code": code,
                "lang": code[:2],
                "name": lang["name"],
                "native": lang["native"],
                "address": {rel: {"native": native, "latin": latin} for rel, (native, latin) in lang["address"].items()},
                "voices": [g for g in ("female", "male") if g in config.VOICES[code]],
            }
            for code, lang in config.LANGUAGES.items()
        ],
        "relations": [{"id": rel, **info} for rel, info in config.RELATIONS.items()],
        "phones": [{"id": pid, "label": label} for pid, label in config.PHONES.items()],
        "max_steps": config.MAX_STEPS,
    }


@app.post("/api/script")
async def write_script(req: ScriptRequest):
    try:
        return await llm.write_script(req.task.strip(), req.language, req.relation, req.custom_name, req.phone, req.narrator())
    except Exception:
        log.exception("writing the script failed")
        raise HTTPException(502, "Couldn't write the steps just now. Please try again.")


@app.post("/api/translate")
async def translate(req: TranslateRequest):
    try:
        return await llm.translate_script(req.script.model_dump(), req.language, req.relation, req.custom_name, req.phone, req.narrator())
    except Exception:
        log.exception("translating the script failed")
        raise HTTPException(502, "Couldn't translate the steps just now. Please try again.")


@app.post("/api/audio")
async def make_audio(req: AudioRequest):
    if req.id in audio.JOBS:
        raise HTTPException(409, "This voice note is already being made.")
    audio.create_job(req.id, req.script.model_dump(), req.language, req.voice)
    return {"id": req.id}


@app.get("/api/audio/{job_id}/stream")
async def stream_audio(job_id: str):
    job = await audio.get_job(job_id, wait=5)
    if not job:
        raise HTTPException(404, "Voice note not found.")
    return StreamingResponse(audio.stream(job), media_type="audio/mpeg", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@app.get("/api/audio/{job_id}")
async def audio_status(job_id: str):
    job = await audio.get_job(job_id, wait=2)
    if not job:
        raise HTTPException(404, "Voice note not found.")
    return job.status()


@app.get("/api/audio/{job_id}/file")
async def audio_file(job_id: str, request: Request):
    job = audio.JOBS.get(job_id)
    if not job or not job.file:
        raise HTTPException(404, "Voice note not ready.")
    data, size = job.file, len(job.file)
    headers = {"Content-Disposition": f'attachment; filename="{job.filename}"', "Accept-Ranges": "bytes", "Cache-Control": "no-store"}
    # Safari only plays media from servers that honour byte ranges.
    m = re.fullmatch(r"bytes=(\d*)-(\d*)", request.headers.get("range", ""))
    if m and (m[1] or m[2]):
        start, end = (int(m[1]), int(m[2]) if m[2] else size - 1) if m[1] else (max(0, size - int(m[2])), size - 1)
        end = min(end, size - 1)
        if start > end:
            return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
        return Response(data[start : end + 1], status_code=206, media_type="audio/mpeg", headers=headers)
    return Response(data, media_type="audio/mpeg", headers=headers)


STATIC.mkdir(exist_ok=True)
app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
