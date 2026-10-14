# Samjhao

**Phone help for parents, as one voice note in their language.**

You type what your parent needs help with, like "how to order food on Swiggy". Samjhao writes short, clear steps in their language, you check them, and Sarvam's Bulbul v4 Flash turns them into one warm, patient voice note that you share on WhatsApp. Your parent plays it and follows along on their phone.

> It explains things to Maa the way you would: in her language, with the real button names, and with patience.

![Samjhao on a phone: pick the task and who it's for, check the steps in Telugu, and the voice note starts playing in under 300 ms](docs/screenshot.png)

Built for the Sarvam Bulbul Build Challenge.

## Why a voice note

Long step-by-step texts are hard for many parents to follow, but they already listen to WhatsApp voice notes every day. A voice note in their own language, with a pause after each step to actually do it, fits a habit they already have.

## What it shows off in Bulbul v4 Flash

| Bulbul v4 Flash | In Samjhao |
|---|---|
| Native voices across Indian languages, with respectful speech | Each language uses its polite form of "you" (आप, మీరు, நீங்க), and verbs agree with the listener's and the narrator's gender |
| Natural code-mixing | App words stay in English inside native-script sentences: "Swiggy app open कीजिए", "Where to? అని ఉన్న box మీద tap చేయండి" |
| Numbers, OTPs and ₹ amounts | Digits and ₹ amounts are left to Bulbul's preprocessing, and money or login tasks get a scam-safety line about OTPs and UPI PINs |
| Speed | The note starts playing about a quarter of a second after you tap, and the app shows Bulbul's measured time to first audio |

## How it works

1. **Write.** Sarvam-105B writes a one-line intro naming the task, 1 to 6 steps, a one-breath recap, and a safety line for money or login tasks. It writes in the language's own script, keeps button names exactly as they appear on screen, uses the polite form of "you" without pet names or filler, and gets gendered verb forms right in languages that have them. The safety line itself is fixed, hand-checked wording in each language rather than LLM output, so the warning can't come out garbled.
2. **Review.** The steps appear as editable cards. An LLM doesn't know today's exact app screens, so you fix anything that's off before it becomes audio.
3. **Speak.** Every part goes to Bulbul v4 Flash over HTTP streaming. The intro goes first; the other parts are generated in parallel as soon as it is flowing.
4. **Play while it's still being made.** Bulbul streams plain MP3 frames (24 kHz, mono, 128 kbps CBR, no headers). Samjhao encodes its pauses (4 seconds after each step) in exactly the same format, so all parts join byte for byte into one stream. The browser plays the intro while later steps are still being generated, and the same bytes become the shareable MP3 (remuxed with ffmpeg to add a duration header, no re-encoding).
5. **Share.** The Web Share API hands the MP3 to WhatsApp, with Download as a fallback.
6. **Hear it in another language.** One tap translates your *edited* script, keeping your fixes and the English button names, then plays it.

Measured on a home connection in India: Bulbul's first audio in about 210 to 290 ms, a full 85-second Hindi note generated in under 3 seconds, and a script written in about 1.5 seconds.

## Sarvam APIs used

| API | Endpoint | Used for |
|---|---|---|
| Bulbul v4 Flash text to speech | `POST /text-to-speech/stream`, model `bulbul:v4-flash` | Every part of the voice note. Lively persona styles such as `ishita_enhi_customer_expressive` and `vaibhav_hi_social` for Hindi, `enable_preprocessing: true`, pace 1.0 (slower pacing sounded flat and delays the first audio) |
| Sarvam-105B chat completion | `POST /v1/chat/completions`, model `sarvam-105b` | Writing the steps and translating an edited script, with reasoning off and strict JSON-schema output |

## Run it

You need Python 3.10+, ffmpeg and a [Sarvam API key](https://dashboard.sarvam.ai).

```bash
git clone <this repo> samjhao && cd samjhao
cp .env.example .env          # then put your SARVAM_API_KEY in .env
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --port 8000
```

Open http://localhost:8000.

Sharing a file to WhatsApp needs an HTTPS page, so to try it on your phone run a tunnel and open the URL it prints:

```bash
cloudflared tunnel --protocol http2 --url http://localhost:8000
```

## Project layout

```
app/
  main.py     FastAPI routes; serves the page
  llm.py      writing and translating the steps (Sarvam-105B)
  tts.py      Bulbul v4 Flash streaming client
  audio.py    voice-note builder: parallel synthesis, live stream, final MP3
  config.py   languages, voices, step labels, pauses
static/       the one-page app (plain HTML, CSS and JavaScript)
scripts/      smoke tests for the TTS and LLM calls
```

## Privacy

Nothing you type is stored. Scripts exist only for the request, and voice notes are kept in memory for 30 minutes so you can share or download them.
