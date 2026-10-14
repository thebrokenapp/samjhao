"""Try the script writer on a few tasks and print the outputs with timings.

Usage: .venv/bin/python scripts/try_llm.py [model-id] [none|low|medium|high]
"""

import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import llm  # noqa: E402

CASES = [
    ("how to order food on Swiggy", "hi-IN", "maa", None, "android", "female"),
    ("how to order food on Swiggy", "te-IN", "maa", None, "android", "female"),
    ("how to make a UPI payment", "hi-IN", "papa", None, "iphone", "male"),
    ("how to turn off silent mode", "ta-IN", "dadi", None, "android", "female"),
]


def show(label: str, script: dict, seconds: float) -> None:
    print(f"\n=== {label} ({seconds:.2f}s)")
    print(json.dumps(script, ensure_ascii=False, indent=2))


async def main() -> None:
    if len(sys.argv) > 1:
        llm.WRITE_MODEL = llm.TRANSLATE_MODEL = sys.argv[1]
    if len(sys.argv) > 2:
        llm.REASONING_EFFORT = None if sys.argv[2] == "none" else sys.argv[2]
    print("model:", llm.WRITE_MODEL, "reasoning:", llm.REASONING_EFFORT)
    write_times, translate_times = [], []
    scripts = {}
    for task, lang, rel, name, phone, voice in CASES:
        t = time.perf_counter()
        script = await llm.write_script(task, lang, rel, name, phone, voice)
        dt = time.perf_counter() - t
        write_times.append(dt)
        scripts[(task, lang)] = script
        show(f"write: {task} / {lang} / {rel} / {phone} / {voice}", script, dt)

    source = scripts[("how to order food on Swiggy", "hi-IN")]
    for lang in ("te-IN", "ta-IN"):
        t = time.perf_counter()
        script = await llm.translate_script(source, lang, "maa", None, "android", "female")
        dt = time.perf_counter() - t
        translate_times.append(dt)
        show(f"translate: Hindi Swiggy -> {lang}", script, dt)

    print(f"\nmedian write {statistics.median(write_times):.2f}s, median translate {statistics.median(translate_times):.2f}s")
    await llm.aclose()


asyncio.run(main())
