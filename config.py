"""J.A.R.V.I.S. ki settings - sab kuch yahin badlo. (JARVIS ki personality badalni ho to soul.md kholo.)"""

# ----- Tum -----
# Apni asli details config_local.py me likho (ye file git me nahi jaati). Example neeche file ke end me hai.
USER_NAME = "Boss"
HOME_CITY = "Delhi"                           # mausam isi shehar ka (jab tak koi aur shehar na bolo)

# ----- Boards -----
BOARD_EXAM_DATE = "2027-02-15"                # pakki date aaye to badal dena (plan isi se banta hai)
STUDY_HOURS_PER_DAY = 4                       # "aaj ka plan" kitne ghante ka bane
LECTURE_MINUTES = 75                          # ek lecture me lagbhag kitne minute (1.5x speed pe)

# ----- Dimaag -----
BRAIN = "gemini"                              # "gemini" = free | "claude" = paid, sabse smart
GEMINI_MODEL = "gemini-flash-lite-latest"     # tez aur free limit zyada
GEMINI_BACKUP_MODELS = ("gemini-flash-latest", "gemini-3.1-flash-lite")  # main busy ho to ye
GROQ_MODEL = "openai/gpt-oss-120b"            # Gemini busy ho to Groq (keys.env me GROQ_API_KEY)
CLAUDE_MODEL = "claude-opus-5-5"              # BRAIN = "claude" ho tab (sasta: "claude-sonnet-5-5")

# ----- Aawaz -----
VOICE = "en-IN-PrabhatNeural"                 # default aawaz (JARVIS se "aawaz badlo" bhi bol sakte ho)
VOICES = {                                    # "British aawaz me bolo" -> set_voice("british")
    "indian": "en-IN-PrabhatNeural",
    "british": "en-GB-RyanNeural",            # movie wala JARVIS
    "hindi": "hi-IN-MadhurNeural",
    "female": "en-IN-NeerjaExpressiveNeural",
}
LISTEN_LANGUAGE = "hi-IN"                     # Google se sunte waqt (Groq key ho to Groq Whisper use hota hai)

# ----- English JARVIS (JARVIS_eng.bat) - movie wala British butler, sirf English -----
ENGLISH_VOICE = "en-GB-ThomasNeural"          # shaant, gehri British aawaz (dusra option: "en-GB-RyanNeural")
ENGLISH_VOICE_RATE = "-4%"                    # thoda dheema = zyada classy
ENGLISH_VOICE_PITCH = "-3Hz"                  # thoda gehra
ENGLISH_VOICE_FX = True                       # halka "AI system" effect (pasand na aaye to False)
ENGLISH_LISTEN_LANGUAGE = "en-IN"             # Google se sunte waqt (Indian English accent)
ENGLISH_SPOKEN_ACKS = True                    # kaam shuru karte waqt "Right away, sir." bole
SPEAK_IN_TEXT_MODE = False                    # JARVIS (Text).bat me bhi bolke jawab de?

# ----- HUD mode (JARVIS.bat) -----
HOTKEY = "ctrl+alt+j"                         # dabao = JARVIS sune | bolte waqt dabao = chup
CLAP_WAKE = True                              # do baar taali = JARVIS jaage
MORNING_BRIEFING = True                       # start pe greeting + mausam + reminders
REVIEW_TIME = "21:30"                         # roz din ka 2 minute review offer ("" = band)
SCREEN_BREAK_MINUTES = 50                     # itne minute lagatar screen ke baad aankhon ka break yaad dilaye (0 = band)
GESTURE_AUTO_OFF_MINUTES = 10                 # haath ke ishaare: itni der haath na dikhe to webcam apne aap band
INSTANCE_PORT = 47653                         # ek waqt pe ek hi JARVIS chale (iska lock)

# ----- Safety -----
ASK_BEFORE_RISKY = True                       # .exe/.bat jaisi file chalane, terminal kholne, ya bahar ki file phone pe bhejne se pehle 'haan' poochhe

# ----- Apni settings (git me nahi jaati) -----
# config_local.py banao aur usme sirf wahi likho jo badalna hai, jaise:
#   USER_NAME = "Aman"
#   HOME_CITY = "Lucknow"
try:
    from config_local import *  # noqa: F401,F403
except ImportError:
    pass
