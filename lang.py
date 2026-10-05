"""JARVIS ki bhasha: 'hi' = Hinglish (JARVIS.bat, default) | 'en' = British English, movie wala JARVIS (JARVIS_eng.bat).
Jo vaakya JARVIS khud bolta hai (dimaag se nahi) - woh sab yahan dono bhashaon me."""

import random

LANG = "hi"

PHRASES = {
    "hi": {
        "wake": ["Ji?", "Haan Boss?", "Boliye?"],
        "acks": [],  # Hinglish me kaam ke time sirf chhoti si 'beep' (roz ke use me tez rahe)
        "stay": "Theek hai, main yahin hoon.",
        "on_screen": "Jawab screen pe likh diya hai, Boss.",
        "goodbye": "Chalo Boss, milte hain.",
        "confirm_ask": "{q} Haan ya nahi?",
        "confirm_retry": "Samajh nahi aaya. Haan ya nahi?",
        "confirm_hint": "(haan/nahi - bolo ya likho)",
        "interrupted": "(theek hai, ruk gaya - bolo)",
        "listening_more": "(sun raha hoon... aage bolo)",
        "heard_nothing": "(kuch sunai nahi diya)",
        "clap": "👏👏 taali suni",
        "mic_setup": "Mic set ho raha hai, 1 second chup raho...",
        "step_error": "⚠️ Ek kaam me gadbad hui (jarvis.log me details). Main chalu hoon - dobara bolo.",
        "online_phone": "🟢 JARVIS laptop pe online hai, Boss.",
        "reminder": "Reminder: {text}",
        "you": "Tum",
        "you_phone": "Tum (phone)",
        "hint": "'Hey Jarvis' bolo  •  👏👏  •  Ctrl+Alt+J  •  ya yahan likho",
        "busy": "⚠️ {e} 1-2 minute baad dobara bolo.",
        "error": "⚠️ Kuch gadbad ho gayi (jarvis.log me details hain). Dobara bolo.",
        "ask_again": "Ji Boss, boliye kya karun?",
        "go_on": "Haan, aage bolo...",
        "voice_note_fail": "Voice note samajh nahi aaya 😅 Ek baar likh ke bhej do.",
        "heard_voice_note": "🎙️ Suna: {text}",
        "memories": "{n} yaadein loaded",
        "battery_full": "Boss, battery full ho gayi hai. Charger nikal sakte ho.",
        "battery_low": "Boss, battery {p} percent hai. Charger laga lo.",
        "battery_critical": "Boss, battery sirf {p} percent bachi hai! Turant charger lagao.",
        "review": "Boss, din khatam hone wala hai. 2 minute ka review karein? 'Review' bolo - aaj ka hisaab aur kal ka plan set kar denge.",
        "screen_break": "Boss, {m} minute se lagatar screen pe ho. 20 second door kisi cheez ko dekho - aankhon ko aaram milega. 👀",
        "distraction": "Boss, {subject} ka session chal raha hai aur {label} khula hai. Wapas aa jao? 🙂",
        "session_done": "{subject} ka {minutes} minute ka session poora! Shabaash. 5-10 minute ka break lo, paani piyo.",
        "greeting_fallback": "{greet}, {name}. JARVIS online.",
        "voice_hint": "🎙",
        "finish": ("[SYSTEM: user ne apni baat khatam kar di hai (ab chup hai). Ab tak usne jo bola uska jawab do. "
                   "[SUNO] mat likho. Matlab saaf na ho to ek chhota sawaal poochho.]"),
        "phone_prefix": "[phone se Telegram pe]",
        "photo_only": ("(sirf photo bheji, kuch likha nahi - agar koi question/homework hai to solve karke samjhao, "
                       "warna dost ki tarah 2-3 line me natural jawab do)"),
        "photo_caption": "(photo bheji) {caption}",
    },
    "en": {
        "wake": ["Yes, sir?", "At your service, sir.", "Sir?", "I'm listening, sir."],
        "acks": ["Right away, sir.", "On it, sir.", "Certainly, sir.", "Very good, sir.", "One moment, sir."],
        "stay": "Very well, sir. I'll be right here.",
        "on_screen": "I've put the details on your screen, sir.",
        "goodbye": "Goodbye, sir. JARVIS signing off.",
        "confirm_ask": "{q} Shall I proceed, sir?",
        "confirm_retry": "My apologies, sir. Was that a yes or a no?",
        "confirm_hint": "(yes/no - say it or type it)",
        "interrupted": "(stopped - go ahead, sir)",
        "listening_more": "(listening... go on)",
        "heard_nothing": "(didn't catch anything)",
        "clap": "👏👏 clap detected",
        "mic_setup": "Calibrating microphone - a moment of silence, please...",
        "step_error": "⚠️ That task ran into a problem (details in jarvis.log). I'm still online, sir.",
        "online_phone": "🟢 JARVIS is online, sir.",
        "reminder": "Sir, a reminder: {text}",
        "you": "You",
        "you_phone": "You (phone)",
        "hint": "Say 'Hey Jarvis'  •  👏👏  •  Ctrl+Alt+J  •  or type here",
        "busy": "⚠️ My apologies, sir - the servers are rather busy. Please try again in a minute or two.",
        "error": "⚠️ Something went wrong, sir (details in jarvis.log). Please try again.",
        "ask_again": "How may I help, sir?",
        "go_on": "Go on, sir...",
        "voice_note_fail": "I couldn't make out that voice note, sir. Could you type it instead?",
        "heard_voice_note": "🎙️ Heard: {text}",
        "memories": "{n} memories loaded",
        "battery_full": "Sir, the battery is fully charged. You may unplug the charger.",
        "battery_low": "Sir, battery is at {p} percent. I'd recommend plugging in.",
        "battery_critical": "Sir, battery is critically low at {p} percent. Please plug in immediately.",
        "review": "Sir, the day is nearly done. Shall we do a quick two-minute review? Just say 'review'.",
        "screen_break": "Sir, you've been at the screen for {m} minutes straight. Might I suggest a twenty-second break for your eyes?",
        "distraction": "Sir, your {subject} session is still running, and {label} appears to be open. Shall we get back to it?",
        "session_done": "Sir, your {minutes}-minute {subject} session is complete. Well done. I suggest a short break.",
        "greeting_fallback": "{greet}, sir. All systems are online.",
        "voice_hint": "🎙",
        "finish": ("[SYSTEM: The user has finished speaking. Respond to everything they have said so far. "
                   "Do not write [SUNO]. If it is unclear, ask one short question.]"),
        "phone_prefix": "[from phone via Telegram]",
        "photo_only": ("(sent only a photo, no text - if it's a question or homework, solve and explain it; "
                       "otherwise reply naturally in 1-2 lines)"),
        "photo_caption": "(sent a photo) {caption}",
    },
}


def set_lang(code: str) -> None:
    global LANG
    LANG = "en" if code == "en" else "hi"


def is_english() -> bool:
    return LANG == "en"


def t(key: str, **kwargs) -> str:
    value = PHRASES[LANG][key]
    if isinstance(value, list):
        value = random.choice(value) if value else ""
    return value.format(**kwargs) if kwargs else value
