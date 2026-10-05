# J.A.R.V.I.S. 🤍

**A Hinglish + English voice assistant for Windows.** Talk to it in Hinglish (`JARVIS.bat`) or in English with a British "movie JARVIS" voice (`JARVIS_eng.bat`). It has a study mode (backlog planner, flashcards, board-style quizzes, notes from YouTube lectures), long-term memory, reminders, laptop control, and a Telegram link to your phone. Built as a personal project, pair-programming with Claude and Codex.

> Fan project. Not affiliated with Marvel or Disney.

Tumhara personal AI dost: padhai, reminders, hamesha ki memory, laptop control, aur phone (Telegram), Iron Man style.

## Setup
**Chahiye:** Windows 10/11, Python 3.12, Microsoft Edge, mic (gestures ke liye webcam optional), internet.

```
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
copy keys.env.example keys.env
```
1. `keys.env` me apni keys daalo. Sirf `GEMINI_API_KEY` zaroori hai, baaki optional.
2. `config_local.py` banao aur apna naam aur shehar likho. Ye file git me nahi jaati:
   ```python
   USER_NAME = "Aman"
   HOME_CITY = "Lucknow"
   ```
3. Pehli baar chalne pe "hey jarvis" wake word aur gesture model internet se download hote hain.

## Chalana
- **`JARVIS.bat`** ⭐: Iron Man HUD. Jagane ke 4 tareeke: **"Hey Jarvis"** bolo · **do baar taali** 👏👏 · **Ctrl+Alt+J** · neeche box me **likho**.
  - JARVIS bol raha ho aur rokna ho: "Hey Jarvis" bolo ya Ctrl+Alt+J.
  - Reactor ka rang: neela = standby, hara = sun raha, peela = soch raha, narangi = kaam kar raha.
  - Peeli line: chal raha padhai session, due flashcards, silent mode.
- **`JARVIS_eng.bat`** 🇬🇧: movie wala JARVIS. Shaant British aawaz (halke "AI system" effect ke saath), sirf English, butler style ("Yes, sir?", "Right away, sir."). Tum Hinglish me bologe tab bhi English me jawab dega.
  - Hinglish JARVIS chal raha ho aur `JARVIS_eng` kholo, to woh khud band ho jata hai aur English wala aa jata hai (ulta bhi). Dono ki memory ek hi hai.
  - Aawaz/effect: `config.py` me `ENGLISH_VOICE`, `ENGLISH_VOICE_FX`. Personality: `soul_en.md`.
- `JARVIS (Voice).bat` / `JARVIS (Text).bat`: bina HUD wale modes.
- `Auto Start ON.bat`: laptop on hote hi JARVIS chalu (band: `Auto Start OFF.bat`).

## Kya bol sakte ho
| Bolo | Kya hoga |
|---|---|
| "Maths me Integration ke 6 lecture, 3D ke 4 baaki hain" | Backlog save (ek baar batao, chapter-wise) |
| "Roz 4 ghante, plan bana do" / "Aaj kya padhun?" | CBSE weightage ke hisaab se roz ka plan (din chhoote to khud adjust) |
| "Integration ke 2 lecture ho gaye" | Backlog ghatega, plan aage badhega |
| "Physics chemistry ki practice karao" | Mixed board-style sawaal, ek-ek karke; galat wale galti-diary me |
| "Weak chapters batao" | Galtiyon ka hisaab (concept / calculation / silly) |
| "Gesture mode on" ya HUD ka 🖐 button | Webcam se: ✌️ JARVIS bulao · ✋ play/pause · 👋 agla/pichhla gaana · 👍👎 volume · ✊ chup |
| "45 minute Physics padhna hai" | Timer + hisaab (bina tumhare bole session kabhi shuru nahi hota) |
| "Electrostatics ke 10 flashcards bana do" → "Quiz lo" | Ek-ek sawaal, galat wale jaldi dobara (Anki wala schedule) |
| "AC chapter ke notes bana do" | Notes page (formulas ke saath) browser me + Print/PDF |
| Lecture ka **YouTube** link | Notes + flashcards + 5 board-style sawaal |
| Doubt poochho | Pehle hint; "seedha answer do" bologe to poora solution |
| "Study mode, 45 minute chemistry" | Timer, aur Insta/Shorts khole to halka sa yaad dilayega |
| "Aaj screen time kitna gaya?" / "Review" (raat ko) | Sach-sach hisaab + kal ka plan |
| "Maggi ka 2 minute timer" / "Roz 6 baje uthne ka reminder" | Second tak sahi timer / roz wala reminder |
| "Lofi study music chalao" | YouTube Music pe bajega (check karta hai ki sach me baj raha hai) |
| "Aaj ki news" / "Delhi ka mausam" | Taaza khabrein / mausam |
| "Night protocol" / "Study protocol" / "Party protocol" | Ek baar me kai kaam (apne bhi bana sakte ho: "gaming protocol banao: ...") |
| "British aawaz me bolo" | Movie wala JARVIS voice (bhasha Hinglish hi rahegi) |
| "Rahul ko WhatsApp karo ki..." | Poochh ke bhejega, aur confirm karega ki gaya ✓ |
| "Notes mere phone pe bhejo" / "Screenshot phone pe bhejo" | Telegram pe aa jayega |
| "Mere baare me kya yaad hai?" / "Gym wali baat bhool jao" | Yaadein dekhna / mitaana |
| "Silent mode on" | Khud se nahi bolega, sirf likhega |
| "Calculator kholo, 12 times 8 karo" / "Screen pe ye error kya hai?" | Apps me khud kaam / screen dekh ke samjhana |

**Phone (Telegram):** Telegram pe @BotFather se apna bot banao, token `keys.env` me `TELEGRAM_BOT_TOKEN` me daalo. Pehli baar laptop ki HUD pe 6 digit ka code dikhega, woh apne bot ko bhejo. Phir text, voice note, ya question ki photo bhejo. (Laptop pe JARVIS chalu hona chahiye.)

## Settings
- **`config.py`**: roz ke ghante, aawaz, taali on/off, waghera. Apna naam/shehar `config_local.py` me.
- **`soul.md`**: JARVIS ki personality (Notepad me khol ke badal sakte ho).
- **`keys.env`**: API keys. Ye file kisi ko mat bhejna.

## Dimaag
Gemini main hai. Google busy ho to JARVIS khud **Groq** (backup) pe chala jata hai, aur 90 second baad Gemini dobara try karta hai. `config.py` me `BRAIN = "claude"` karke Claude bhi use kar sakte ho.

## ⚠️ Safety, privacy, terms
- **Laptop control:** JARVIS AI ko apps kholne, keys dabane, type karne, files kholne aur screen padhne deta hai. AI galti kar sakta hai, aur web pages ya messages me chhupe instructions (prompt injection) usse galat kaam karwa sakte hain. `config.py` me `ASK_BEFORE_RISKY = True` rakho: tab .exe/.bat jaisi files chalane, terminal kholne, ya bahar ki file phone pe bhejne se pehle JARVIS "haan" poochhega. Shutdown, restart, app band karna aur WhatsApp bhejna hamesha poochh ke hota hai.
- **Telegram:** pairing ke baad phone se JARVIS ka poora control milta hai. Bot token kisi ko mat do.
- **Data:** baatein, memory, screenshots, clipboard aur WhatsApp messages AI provider ko jaate hain. Free tier pe Google data ko review aur training ke liye use kar sakta hai, isliye sensitive cheezein mat bhejo. Gemini API ki terms 18+ users ke liye hain. Jo bhi AI provider use karo, uski terms khud padho.
- **WhatsApp:** WhatsApp Web ko automate karna WhatsApp ki terms ke khilaaf hai, account ban ho sakta hai. Nahi chahiye to `WhatsApp Login.bat` mat chalao.
- **Ye files kabhi share ya upload mat karna** (GitHub issues me bhi nahi): `keys.env`, `config_local.py`, `jarvis.log`, `jarvis_memory.db`, `browser_profile/`. Inme tumhari keys, baatein, contacts aur logged-in sessions hain.

## Kuch gadbad lage
1. **`Self Test.bat`**: 30 cheezein check karta hai. Ye asli API calls karta hai aur Edge kholta hai, par koi message nahi bhejta aur kuch permanently nahi badalta.
2. **`Mic Test.bat`**: mic aur taali ka test.
3. Har kaam `jarvis.log` me likha jaata hai. Ye sirf tumhare laptop pe rehta hai.

`jarvis_memory.db` = JARVIS ki yaaddasht. Isko delete mat karna, kabhi-kabhi backup bana lena.

## Credits and licenses
- Code: MIT ([LICENSE](LICENSE)).
- Wake word: [openWakeWord](https://github.com/dscripka/openWakeWord). Its pre-trained models (including "hey jarvis") are CC BY-NC-SA 4.0, so no commercial use.
- Hand gestures: Google MediaPipe Gesture Recognizer model, downloaded on first use.
- Voices: [edge-tts](https://github.com/rany2/edge-tts) (Microsoft Edge Read Aloud voices).
- AI: Google Gemini, Groq, and optionally Anthropic Claude.
