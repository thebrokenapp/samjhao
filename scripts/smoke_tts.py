"""Build step 1-2: synthesise one Hinglish sentence and fetch the live Bulbul v4 Flash speaker list.

Usage: .venv/bin/python -m scripts.smoke_tts [speaker ...]
"""

import asyncio
import json
import pathlib
import sys
import time

from app import tts

OUT = pathlib.Path(__file__).resolve().parent.parent / "output"
TEXT = "माँ, पहले Swiggy app open कीजिए। फिर ऊपर Search पर tap कीजिए, और ₹200 तक का खाना चुनिए। OTP 4821 किसी को मत बताइए।"


async def speakers() -> str:
    try:
        async for _ in tts.stream("test", "hi-IN", "not_a_real_speaker"):
            pass
    except tts.TTSError as e:
        return e.body
    return "(no error returned)"


async def synth(speaker: str) -> None:
    OUT.mkdir(exist_ok=True)
    t0 = time.perf_counter()
    ttfb = None
    data = bytearray()
    async for chunk in tts.stream(TEXT, "hi-IN", speaker):
        if ttfb is None:
            ttfb = (time.perf_counter() - t0) * 1000
        data += chunk
    total = (time.perf_counter() - t0) * 1000
    path = OUT / f"smoke_{speaker}.mp3"
    path.write_bytes(data)
    print(f"{speaker}: first audio {ttfb:.0f} ms, done {total:.0f} ms, {len(data)} bytes -> {path}")
    print("  head:", bytes(data[:48]).hex(" "))


async def main() -> None:
    body = await speakers()
    (OUT).mkdir(exist_ok=True)
    (OUT / "speakers_error.txt").write_text(body)
    print("speaker list error body (first 400 chars):", body[:400])
    for sp in sys.argv[1:] or ["aparna_hi_customer"]:
        await synth(sp)
    # second call on the warm connection shows the steady-state latency
    for sp in sys.argv[1:2] or ["aparna_hi_customer"]:
        await synth(sp)


asyncio.run(main())
