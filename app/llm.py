"""Script writer: turns a phone task into a short voice-note script with Sarvam's chat API.

Everything model-specific lives in _complete(); swap that one function to change the LLM.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path

import httpx
from dotenv import load_dotenv

from . import config

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

CHAT_URL = "https://api.sarvam.ai/v1/chat/completions"
# sarvam-105b-conversations is ~3x faster but made more factual mistakes in the steps during testing.
WRITE_MODEL = "sarvam-105b"
TRANSLATE_MODEL = "sarvam-105b"
TIMEOUT = 45.0
WRITE_TEMPERATURE = 0.5
TRANSLATE_TEMPERATURE = 0.3
# Thinking is on by default: it adds seconds and can use up the whole token budget.
REASONING_EFFORT: str | None = None

SCRIPT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "intro": {"type": "string"},
        "steps": {"type": "array", "items": {"type": "string"}},
        "recap": {"type": "string"},
        "safety": {"type": ["string", "null"]},
        "close": {"type": "string"},
        "note": {"type": ["string", "null"]},
    },
    "required": ["title", "intro", "steps", "recap", "safety", "close", "note"],
    "additionalProperties": False,
}


class ScriptError(RuntimeError):
    """The LLM call failed or returned an unusable script."""


# --- prompt pieces -----------------------------------------------------------------------------

LISTENER = {"maa": "mother", "papa": "father", "dadi": "grandmother (father's mother)",
            "nani": "grandmother (mother's mother)", "custom": "elder in the family"}

PHONE_HINTS = {
    "android": "Android phones have a Back button or back gesture at the bottom of the screen, and apps come from Play Store.",
    "iphone": "iPhones have no Back button: going back is the arrow at the top-left of the screen, swiping up from the bottom goes home, and apps come from App Store. "
              "Silent mode is the small switch on the LEFT side, above the two volume buttons: an orange mark showing means silent, and flipping "
              "the switch toward the screen hides the orange and turns sound back on. On iPhone 15 Pro and newer it is the Action button in the "
              "same place, pressed and held. The volume buttons are on the left side too; the only button on the right side is the power button.",
}

# First-person examples for languages whose verbs show the speaker's gender: (female, male).
FIRST_PERSON = {
    "hi-IN": ("मैं आपको बताती हूँ", "मैं आपको बताता हूँ"),
    "mr-IN": ("मी तुम्हाला सांगते", "मी तुम्हाला सांगतो"),
    "gu-IN": ("હું તમને શીખવાડવા આવી છું", "હું તમને શીખવાડવા આવ્યો છું"),
    "pa-IN": ("ਮੈਂ ਤੁਹਾਨੂੰ ਦੱਸਦੀ ਹਾਂ", "ਮੈਂ ਤੁਹਾਨੂੰ ਦੱਸਦਾ ਹਾਂ"),
}

DANDA_LANGUAGES = {"hi-IN", "bn-IN", "pa-IN"}

SCRIPT_RANGES = {
    "Devanagari": (0x0900, 0x097F), "Bengali": (0x0980, 0x09FF), "Gurmukhi": (0x0A00, 0x0A7F),
    "Gujarati": (0x0A80, 0x0AFF), "Tamil": (0x0B80, 0x0BFF), "Telugu": (0x0C00, 0x0C7F),
    "Kannada": (0x0C80, 0x0CFF),
}


def _language_rules(language: str, relation: str, custom_name: str | None, voice: str) -> str:
    lang = config.LANGUAGES[language]
    name, script = lang["name"], lang["script"]
    listener_gender = config.RELATIONS[relation]["listener_gender"]
    full_stop = "।" if language in DANDA_LANGUAGES else "."

    lines = [
        "LANGUAGE",
        f"- Write in {name}, in {script} script." + ("" if script == "Latin" else f" Never write {name} words in Latin letters."),
        f"- {lang['style']}",
        "- Keep app names, button labels and menu items in English, in Latin script, spelled exactly as they appear "
        "on the screen (for example: Swiggy, Search, Add to cart, Proceed to Pay, Where to?, Settings). Everyday English "
        f"words people mix into {name} (app, open, tap, button, screen, OTP) also stay in English, in Latin script.",
        '- The mix we want, in Hindi: "Phone की Settings app open कीजिए। नीचे scroll करके Display पर tap कीजिए।"',
        '- The mix we want, in Telugu: "WhatsApp open చేయండి. కింద ఉన్న Calls మీద tap చేయండి."',
        "- Write numbers and ₹ amounts as digits (4, ₹500). Never spell numbers out in words.",
        f"- Short spoken sentences, 12 words or fewer. Commas for small pauses. End sentences with {full_stop} "
        "No ellipses, no emojis, no markdown, no quotation marks around button names.",
        "",
        "HOW TO SPEAK TO THEM",
        "- Never call the listener by name or relation: no Maa, Mummy, Papa, Amma, Appa, Dadi, Nani, Aai, Baba, garu or "
        "ji forms, no beta, no dear. Just speak to them directly with the respectful you form.",
        "- Friendly and matter-of-fact, like a patient helpline voice. No greetings (hello, namaste, vanakkam) and no "
        "emotional lines such as I am here for you, don't worry or I love you.",
    ]
    if listener_gender:
        lines.append(f"- The listener is {listener_gender}; use matching forms whenever you refer to them.")
    else:
        lines.append("- The listener's gender is unknown; avoid gendered forms for them where you can.")
    if lang["gendered_first_person"]:
        female, male = FIRST_PERSON[language]
        own, other = (female, male) if voice == "female" else (male, female)
        lines.append(f"- You, the narrator, are {voice}. {name} first-person verbs show the speaker's gender, so use "
                     f'{voice} forms for yourself: "{own}", never "{other}".')
    return "\n".join(lines)


def _write_system(language: str, relation: str, custom_name: str | None, phone: str, voice: str) -> str:
    phone_name = config.PHONES[phone]
    sender = "grandchild" if relation in ("dadi", "nani") else "grown-up child"
    return f"""You write the script for a short WhatsApp voice note. It teaches an Indian {LISTENER[relation]} how to do one thing on their {phone_name}. Their {sender} sends it, and a text-to-speech voice reads it aloud. Write for the ear: clear, patient and simple.

{_language_rules(language, relation, custom_name, voice)}

CONTENT
- Use the real, current screens of the app as best you know them, and the simplest common path. If you are unsure of a label, describe the button by its place and look instead of inventing a label.
- Use the buttons, menus and gestures of a {phone_name}. {PHONE_HINTS[phone]} Mention these only when a step needs them.
- 3 to 6 steps (fewer only if the task is truly tiny). One action per step, at most 2 short sentences. Name the exact button and say where it is on the screen (top, bottom, right corner). Mention a colour or icon only if you are sure.
- If the task needs more than 6 steps, cover the first useful part in 6 steps and use "note" to say, in one English sentence, how to split the rest into another voice note.
- Never put "Step 1", numbers or bullets before a step; the audio adds step numbers itself.

PARTS (JSON fields)
- title: 2 to 5 English words in Latin script naming the task, like "Order food on Swiggy".
- intro: in one short sentence say what this voice note shows, say how many steps there are (as a digit, matching the steps list), then tell them to take their time and that they can pause this voice note anytime.
- steps: the steps, in order.
- recap: one breath that runs through all the steps quickly.
- safety: only if the task itself involves paying money, UPI, banking, OTPs, passwords or logging in. Then one or two sentences that say all of this: never tell your OTP or UPI PIN to anyone who calls you, even if they say they are from the bank. For everything else (calls, video calls, messages, photos, settings, sound) it must be null.
- close: one short line: if you get stuck, just call me.
- note: null unless the task needs more than 6 steps.

Reply with one JSON object only."""


def _translate_system(language: str, relation: str, custom_name: str | None, phone: str, voice: str, steps: int) -> str:
    phone_name = config.PHONES[phone]
    name = config.LANGUAGES[language]["name"]
    return f"""You rewrite the script of a short WhatsApp voice note in {name}. It teaches an Indian {LISTENER[relation]} how to do one thing on their {phone_name}, and a text-to-speech voice reads it aloud. Write for the ear: clear, patient and simple. Sound like a native {name} speaker talking, not like a translation.

{_language_rules(language, relation, custom_name, voice)}

FAITHFULNESS
- The user may have edited the source script. Keep every step, in the same order, with the same meaning and details. Same number of steps; never add, drop, merge or split steps.
- Keep app names and button labels exactly as they are in the source.
- If the source calls the listener by name or relation (Maa, Papa, Amma garu and so on), leave that out.
- The intro must say the number of steps as the digit {steps}, and tell them to take their time and that they can pause this voice note anytime.
- safety: translate it if the source has one, keep it null if the source's is null.
- title and note: copy them unchanged.
- Never put "Step 1", numbers or bullets before a step.

Reply with one JSON object with the same fields as the source: title, intro, steps, recap, safety, close, note."""


# --- model call --------------------------------------------------------------------------------

_client: httpx.AsyncClient | None = None


def _http() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=TIMEOUT)
    return _client


async def aclose() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def _complete(model: str, system: str, user: str, temperature: float) -> str:
    """One chat completion that returns the raw reply text (a JSON string)."""
    key = os.environ.get("SARVAM_API_KEY")
    if not key:
        raise ScriptError("SARVAM_API_KEY is not set")
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": temperature,
        "max_tokens": 4096 if REASONING_EFFORT else 2048,
        "reasoning_effort": REASONING_EFFORT,
        "response_format": {"type": "json_schema",
                            "json_schema": {"name": "voice_note_script", "strict": True, "schema": SCRIPT_SCHEMA}},
    }
    for attempt in range(2):
        try:
            r = await _http().post(CHAT_URL, json=body, headers={"api-subscription-key": key})
        except httpx.HTTPError as e:
            if attempt:
                raise ScriptError(f"Could not reach the Sarvam chat API: {e}") from e
            continue
        if r.status_code in (429, 500, 502, 503, 504) and not attempt:
            await asyncio.sleep(1.0)
            continue
        if r.status_code != 200:
            raise ScriptError(f"Sarvam chat API returned {r.status_code}: {r.text[:300]}")
        choice = r.json()["choices"][0]
        return choice["message"].get("content") or ""
    raise ScriptError("Sarvam chat API did not answer")


# --- parsing and cleanup -----------------------------------------------------------------------

_THINK = re.compile(r"<think>.*?</think>", re.S)
_STEP_LABEL = re.compile(r"^\s*(?:step\s*)?\d{1,2}\s*[.):\-–]\s+", re.I)
_MARKDOWN = re.compile(r"[*_#`]+")
_EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F]")


def _clean(text: str) -> str:
    text = text.replace("…", ", ").replace("...", ". ")
    text = re.sub(r"[\"“”«»]", "", text)
    text = _EMOJI.sub("", _MARKDOWN.sub("", text))
    text = re.sub(r"\s+([,.।?!])", r"\1", text)
    return re.sub(r"\s+", " ", text).strip(" ,")


# The voice note never calls the listener "Maa", "Amma garu" and so on. If the model does it anyway, these are
# removed, but only in vocative positions (start or end of a sentence, or between commas).
EXTRA_ADDRESS = {
    "hi-IN": ["मां", "मम्मी", "मम्मी जी", "पापा जी", "दादी जी", "नानी जी", "अम्मा"],
    "te-IN": ["అమ్మా", "అమ్మ", "నాన్నా", "నాన్న", "నానమ్మా", "అమ్మమ్మా"],
    "ta-IN": ["அம்மா", "அப்பா", "பாட்டி"],
    "kn-IN": ["ಅಮ್ಮ", "ಅಪ್ಪ"],
    "mr-IN": ["आई", "बाबा", "आजी"],
    "bn-IN": ["মা", "বাবা"],
    "gu-IN": ["બા", "મમ્મી", "પપ્પા"],
    "pa-IN": ["ਮੰਮੀ", "ਪਾਪਾ", "ਮਾਂ ਜੀ", "ਬੀਜੀ"],
    "en-IN": ["Maa", "Mom", "Mummy", "Papa", "Dad", "Dadi", "Nani"],
}


def _address_words(language: str, custom_name: str | None) -> list[str]:
    words = {w for forms in config.LANGUAGES[language]["address"].values() for w in forms}
    words.update(EXTRA_ADDRESS.get(language, ()))
    words.update(w[:-1] + "ు" for w in list(words) if w.endswith("ూ"))  # Telugu: గారూ and గారు
    if custom_name and custom_name.strip():
        words.add(custom_name.strip())
    return sorted(words, key=len, reverse=True)


def _strip_address(text: str, words: list[str]) -> str:
    alt = "|".join(re.escape(w) for w in words)
    text = re.sub(rf"(^|[.।!?]\s+)(?:{alt})\s*,\s*", r"\1", text)  # "माँ, पहले ..."
    text = re.sub(rf"\s*,\s*(?:{alt})\s*,", ",", text)  # "अब, माँ, Search ..."
    text = re.sub(rf"[\s,]+(?:{alt})\s*([.।!?])", r"\1", text)  # "... call कर लीजिएगा माँ।"
    text = re.sub(r"(^|[.!?]\s+)([a-z])", lambda m: m[1] + m[2].upper(), text)
    return text.strip()


def _without_address(script: dict, language: str, custom_name: str | None) -> dict:
    words = _address_words(language, custom_name)
    for key in ("intro", "recap", "safety", "close"):
        if script.get(key):
            script[key] = _strip_address(script[key], words)
    script["steps"] = [s for s in (_strip_address(s, words) for s in script["steps"]) if s]
    script["intro"] = _fix_step_count(script["intro"], len(script["steps"]))
    return script


def _fix_step_count(intro: str, steps: int) -> str:
    """The LLM sometimes miscounts its own steps; correct the one number in the intro."""
    numbers = list(re.finditer(r"(?<![\d₹])\d{1,2}(?!\d)", intro))
    if len(numbers) == 1 and numbers[0].group() != str(steps):
        m = numbers[0]
        return intro[:m.start()] + str(steps) + intro[m.end():]
    return intro


def _title_from_task(task: str) -> str:
    title = re.sub(r"^\s*how\s+(?:do\s+i|can\s+i|to)\s+", "", task.strip(), flags=re.I).rstrip("?.! ")
    return (title[:1].upper() + title[1:])[:60] or "Phone help"


def _script_share(text: str, script: str) -> float:
    """Fraction of letters written in the given Indic script (code-mixed text is never 100%)."""
    lo, hi = SCRIPT_RANGES[script]
    letters = [c for c in text if c.isalpha() or lo <= ord(c) <= hi]
    if not letters:
        return 0.0
    return sum(lo <= ord(c) <= hi for c in letters) / len(letters)


def _parse(raw: str, language: str) -> dict:
    text = _THINK.sub("", raw)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no JSON object in the reply")
    data = json.loads(text[start:end + 1])
    if not isinstance(data, dict):
        raise ValueError("reply is not a JSON object")

    def text_field(key: str, optional: bool = False) -> str | None:
        value = data.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            if optional:
                return None
            raise ValueError(f"'{key}' is missing")
        if not isinstance(value, str):
            raise ValueError(f"'{key}' is not text")
        return _clean(value)

    steps = data.get("steps")
    if not isinstance(steps, list):
        raise ValueError("'steps' is not a list")
    steps = [_clean(_STEP_LABEL.sub("", s)) for s in steps if isinstance(s, str) and s.strip()]
    if not steps:
        raise ValueError("no steps")

    script = {
        "title": text_field("title"),
        "intro": text_field("intro"),
        "steps": steps[: config.MAX_STEPS],
        "recap": text_field("recap"),
        "safety": text_field("safety", optional=True),
        "close": text_field("close"),
        "note": text_field("note", optional=True),
    }
    script["intro"] = _fix_step_count(script["intro"], len(script["steps"]))

    writing = config.LANGUAGES[language]["script"]
    if writing != "Latin":
        spoken = " ".join([script["intro"], *script["steps"], script["recap"], script["close"]])
        if _script_share(spoken, writing) < 0.25:
            raise ValueError(f"reply is not written in {writing} script")
    return script


async def _generate(model: str, system: str, user: str, language: str, temperature: float,
                    steps_expected: int | None = None) -> dict:
    problem = ""
    for attempt in range(2):
        raw = await _complete(model, system, user, temperature)
        try:
            script = _parse(raw, language)
        except (ValueError, json.JSONDecodeError) as e:
            problem = str(e)
            continue
        if steps_expected and len(script["steps"]) != steps_expected and attempt == 0:
            problem = f"expected {steps_expected} steps, got {len(script['steps'])}"
            continue
        return script
    raise ScriptError(f"The script writer returned an unusable reply ({problem})")


# --- public API --------------------------------------------------------------------------------

async def write_script(task: str, language: str, relation: str, custom_name: str | None, phone: str, voice: str) -> dict:
    """Write a new voice-note script for `task` in `language`."""
    system = _write_system(language, relation, custom_name, phone, voice)
    user = f"Task: {task.strip()}"
    script = await _generate(WRITE_MODEL, system, user, language, WRITE_TEMPERATURE)
    if not script["title"].isascii():
        script["title"] = _title_from_task(task)
    return _without_address(script, language, custom_name)


async def translate_script(script: dict, language: str, relation: str, custom_name: str | None, phone: str, voice: str) -> dict:
    """Rewrite an existing (possibly user-edited) script in `language`, keeping its steps."""
    source = {k: script.get(k) for k in ("title", "intro", "steps", "recap", "safety", "close", "note")}
    system = _translate_system(language, relation, custom_name, phone, voice, len(source["steps"] or []))
    user = "Source script:\n" + json.dumps(source, ensure_ascii=False, indent=2)
    result = await _generate(TRANSLATE_MODEL, system, user, language, TRANSLATE_TEMPERATURE,
                             steps_expected=len(source["steps"] or []))
    result["title"] = source["title"] or result["title"]
    result["note"] = source["note"]
    return _without_address(result, language, custom_name)
