"""Languages, address forms, voices and audio settings. Single source of truth for the API and the UI."""

# Who the voice note is for. The address form per language lives in LANGUAGES[...]["address"].
RELATIONS = {
    "maa": {"label": "Maa", "listener_gender": "female"},
    "papa": {"label": "Papa", "listener_gender": "male"},
    "dadi": {"label": "Dadi", "listener_gender": "female"},
    "nani": {"label": "Nani", "listener_gender": "female"},
    "custom": {"label": "Someone else", "listener_gender": None},
}

# address: relation -> (native script, Latin) forms of address. The voice note never uses them: llm.py strips them if the model adds one.
# style: register guidance passed to the LLM
LANGUAGES = {
    "hi-IN": {
        "name": "Hindi", "native": "हिन्दी", "script": "Devanagari", "gendered_first_person": True,
        "address": {"maa": ("माँ", "Maa"), "papa": ("पापा", "Papa"), "dadi": ("दादी", "Dadi"), "nani": ("नानी", "Nani")},
        "style": "Use the respectful आप form (कीजिए, दबाइए). Everyday spoken Hindi with natural Hinglish, not formal शुद्ध Hindi.",
    },
    "te-IN": {
        "name": "Telugu", "native": "తెలుగు", "script": "Telugu", "gendered_first_person": False,
        "address": {"maa": ("అమ్మగారూ", "Amma garu"), "papa": ("నాన్నగారూ", "Nanna garu"), "dadi": ("నానమ్మగారూ", "Nanamma garu"), "nani": ("అమ్మమ్మగారూ", "Ammamma garu")},
        "style": "Use the respectful మీరు form with -ండి endings (చేయండి, నొక్కండి). Spoken Telugu, not bookish.",
    },
    "ta-IN": {
        "name": "Tamil", "native": "தமிழ்", "script": "Tamil", "gendered_first_person": False,
        "address": {"maa": ("அம்மா", "Amma"), "papa": ("அப்பா", "Appa"), "dadi": ("பாட்டி", "Paati"), "nani": ("பாட்டி", "Paati")},
        "style": "Use respectful spoken Tamil with -ங்க endings (பண்ணுங்க, அழுத்துங்க), the way people talk, not formal written Tamil.",
    },
    "kn-IN": {
        "name": "Kannada", "native": "ಕನ್ನಡ", "script": "Kannada", "gendered_first_person": False,
        "address": {"maa": ("ಅಮ್ಮಾ", "Amma"), "papa": ("ಅಪ್ಪಾ", "Appa"), "dadi": ("ಅಜ್ಜಿ", "Ajji"), "nani": ("ಅಜ್ಜಿ", "Ajji")},
        "style": "Use the respectful ನೀವು form (ಮಾಡಿ, ಒತ್ತಿ). Everyday spoken Kannada.",
    },
    "mr-IN": {
        "name": "Marathi", "native": "मराठी", "script": "Devanagari", "gendered_first_person": True,
        "address": {"maa": ("आई", "Aai"), "papa": ("बाबा", "Baba"), "dadi": ("आजी", "Aaji"), "nani": ("आजी", "Aaji")},
        "style": "Use the polite तुम्ही form (करा, दाबा). Everyday spoken Marathi.",
    },
    "bn-IN": {
        "name": "Bengali", "native": "বাংলা", "script": "Bengali", "gendered_first_person": False,
        "address": {"maa": ("মা", "Maa"), "papa": ("বাবা", "Baba"), "dadi": ("ঠাকুমা", "Thakuma"), "nani": ("দিদিমা", "Didima")},
        "style": "Use the warm তুমি form (করো, টিপে দাও), as people speak to their parents. Spoken চলিত Bengali.",
    },
    "gu-IN": {
        "name": "Gujarati", "native": "ગુજરાતી", "script": "Gujarati", "gendered_first_person": True,
        "address": {"maa": ("મમ્મી", "Mummy"), "papa": ("પપ્પા", "Pappa"), "dadi": ("દાદી", "Dadi"), "nani": ("નાની", "Nani")},
        "style": "Use the polite તમે form (કરો, દબાવો). Everyday spoken Gujarati.",
    },
    "pa-IN": {
        "name": "Punjabi", "native": "ਪੰਜਾਬੀ", "script": "Gurmukhi", "gendered_first_person": True,
        "address": {"maa": ("ਮੰਮੀ ਜੀ", "Mummy ji"), "papa": ("ਪਾਪਾ ਜੀ", "Papa ji"), "dadi": ("ਦਾਦੀ ਜੀ", "Dadi ji"), "nani": ("ਨਾਨੀ ਜੀ", "Nani ji")},
        "style": "Use the respectful ਤੁਸੀਂ form (ਕਰੋ, ਦਬਾਓ). Everyday spoken Punjabi.",
    },
    "en-IN": {
        "name": "English", "native": "English", "script": "Latin", "gendered_first_person": False,
        "address": {"maa": ("Maa", "Maa"), "papa": ("Papa", "Papa"), "dadi": ("Dadi", "Dadi"), "nani": ("Nani", "Nani")},
        "style": "Simple, warm Indian English. Short, everyday words.",
    },
}

PHONES = {"android": "Android", "iphone": "iPhone"}

# Scam-safety line for tasks involving money or login. Fixed text, not LLM-written: a dropped negation here
# ("believe them" instead of "don't believe them") would be dangerous.
SAFETY_LINE = {
    "hi-IN": "कोई भी call करके OTP या UPI PIN माँगे, तो कभी मत बताइए, चाहे वो कहे कि bank से बोल रहा है।",
    "te-IN": "ఎవరైనా call చేసి OTP లేదా UPI PIN అడిగితే, ఎప్పుడూ చెప్పకండి. Bank నుంచి అని చెప్పినా నమ్మకండి.",
    "ta-IN": "யாராவது call பண்ணி OTP அல்லது UPI PIN கேட்டா, ஒருபோதும் சொல்லாதீங்க. Bank-ல இருந்து பேசறோம்னு சொன்னாலும் நம்பாதீங்க.",
    "kn-IN": "ಯಾರಾದರೂ call ಮಾಡಿ OTP ಅಥವಾ UPI PIN ಕೇಳಿದರೆ, ಯಾವತ್ತೂ ಹೇಳಬೇಡಿ. Bank ಇಂದ ಮಾತಾಡ್ತಿದ್ದೀವಿ ಅಂದರೂ ನಂಬಬೇಡಿ.",
    "mr-IN": "कोणी call करून OTP किंवा UPI PIN विचारला, तर कधीच सांगू नका. Bank मधून बोलतोय असं सांगितलं तरी विश्वास ठेवू नका.",
    "bn-IN": "কেউ call করে OTP বা UPI PIN চাইলে, কখনও বলবেন না। Bank থেকে বলছি বললেও বিশ্বাস করবেন না।",
    "gu-IN": "કોઈ call કરીને OTP કે UPI PIN માંગે, તો ક્યારેય કહેશો નહીં. Bank માંથી બોલું છું એમ કહે તો પણ વિશ્વાસ કરશો નહીં.",
    "pa-IN": "ਜੇ ਕੋਈ call ਕਰਕੇ OTP ਜਾਂ UPI PIN ਮੰਗੇ, ਤਾਂ ਕਦੇ ਨਾ ਦੱਸੋ। ਭਾਵੇਂ ਉਹ ਕਹੇ ਕਿ bank ਤੋਂ ਬੋਲ ਰਿਹਾ ਹਾਂ, ਯਕੀਨ ਨਾ ਕਰੋ।",
    "en-IN": "Never tell your OTP or UPI PIN to anyone who calls you, even if they say they are from the bank.",
}

# Bulbul v4 Flash speaker IDs per language, picked from the live speaker list. Hindi uses the livelier styles
# (expressive, social) chosen by ear; the calm "customer"/"narration" styles sounded flat.
# Tamil has no female persona on v4 Flash yet.
VOICES: dict[str, dict[str, str]] = {
    "hi-IN": {"female": "ishita_enhi_customer_expressive", "male": "vaibhav_hi_social"},
    "te-IN": {"female": "kavitha_te_conversation", "male": "tarun_te_narration"},
    "ta-IN": {"male": "gokul_ta_narration"},
    "kn-IN": {"female": "chaitra_kn_conversation", "male": "chetan_kn_conversation"},
    "mr-IN": {"female": "ishita_mr_conversational", "male": "nilesh_mr_conversation"},
    "bn-IN": {"female": "roopa_bn_conversational", "male": "arnab_bn_conversation"},
    "gu-IN": {"female": "pooja_gu_customer", "male": "bhavik_gu_conversation"},
    "pa-IN": {"female": "harpreet_pa_narration", "male": "anand_pa_customer"},
    "en-IN": {"female": "ishita_enhi_customer_expressive", "male": "shubh_en_narration_gentle"},
}

# Spoken before each step: "<ordinal> step." Native ordinals, English "step" (natural code-mixing).
STEP_ORDINALS = {
    "hi-IN": ["पहला", "दूसरा", "तीसरा", "चौथा", "पाँचवाँ", "छठा"],
    "te-IN": ["మొదటి", "రెండవ", "మూడవ", "నాలుగవ", "ఐదవ", "ఆరవ"],
    "ta-IN": ["முதல்", "இரண்டாவது", "மூன்றாவது", "நான்காவது", "ஐந்தாவது", "ஆறாவது"],
    "kn-IN": ["ಮೊದಲನೇ", "ಎರಡನೇ", "ಮೂರನೇ", "ನಾಲ್ಕನೇ", "ಐದನೇ", "ಆರನೇ"],
    "mr-IN": ["पहिली", "दुसरी", "तिसरी", "चौथी", "पाचवी", "सहावी"],
    "bn-IN": ["প্রথম", "দ্বিতীয়", "তৃতীয়", "চতুর্থ", "পঞ্চম", "ষষ্ঠ"],
    "gu-IN": ["પહેલું", "બીજું", "ત્રીજું", "ચોથું", "પાંચમું", "છઠ્ઠું"],
    "pa-IN": ["ਪਹਿਲਾ", "ਦੂਜਾ", "ਤੀਜਾ", "ਚੌਥਾ", "ਪੰਜਵਾਂ", "ਛੇਵਾਂ"],
    "en-IN": ["Step one", "Step two", "Step three", "Step four", "Step five", "Step six"],
}


def step_label(language: str, index: int) -> str:
    ordinal = STEP_ORDINALS[language][index]
    return ordinal if language == "en-IN" else f"{ordinal} step"


TTS_MODEL = "bulbul:v4-flash"
# Normal speed: 0.85 sounded flat, and any pace other than 1.0 also adds ~100 ms before the first audio.
TTS_PACE = 1.0
TTS_SAMPLE_RATE = 24000

# Silence (seconds) inserted after each part of the voice note.
PAUSE_AFTER_INTRO = 1.0
PAUSE_AFTER_STEP = 4.0
PAUSE_AFTER_RECAP = 1.0
PAUSE_AFTER_SAFETY = 0.8
MAX_STEPS = 6


def address_for(language: str, relation: str, custom_name: str | None = None) -> str:
    """Native-script form used to address the listener. Custom names are passed through as typed."""
    if relation == "custom":
        return (custom_name or "").strip()
    return LANGUAGES[language]["address"][relation][0]
