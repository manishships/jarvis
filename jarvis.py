"""
J.A.R.V.I.S. - tumhara personal AI dost (padhai + dharm + mann ki baat + reminders + memory + voice + laptop control)

HUD (main):  JARVIS.bat           (python jarvis.py --hud)
Text mode:   JARVIS (Text).bat    (python jarvis.py)
Voice mode:  JARVIS (Voice).bat   (python jarvis.py --voice)
Settings:    config.py   |   Personality: soul.md   |   Gadbad: jarvis.log / Self Test.bat
"""

import atexit
import functools
import json
import logging
import os
import re
import sys
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

import config
import lang

HERE = Path(__file__).parent
_handler = RotatingFileHandler(HERE / "jarvis.log", maxBytes=1_500_000, backupCount=2, encoding="utf-8")
_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logging.basicConfig(level=logging.INFO, handlers=[_handler])
for noisy in ("httpx", "httpcore", "google_genai", "urllib3", "comtypes", "screen_brightness_control"):
    logging.getLogger(noisy).setLevel(logging.WARNING)
log = logging.getLogger("jarvis")

import browser  # noqa: E402
import memory  # noqa: E402
import pc_control  # noqa: E402
import gestures  # noqa: E402
import planner  # noqa: E402
import study  # noqa: E402
from brains import BrainError, ClaudeBrain, GeminiBrain, GroqBrain  # noqa: E402

USER_NAME = config.USER_NAME
VOICE = config.VOICE  # purane code/self-test ke liye (asli aawaz: memory.current_voice())
STOP_WORDS = {"bye", "goodbye", "exit", "quit", "band karo", "so jao", "that's all", "thats all", "that will be all",
              "go to sleep", "बाय", "बंद करो"}


def _load_persona() -> str:
    """soul.md (Hinglish) ya soul_en.md (English JARVIS) - bhasha ke hisaab se."""
    name = "soul_en.md" if lang.is_english() else "soul.md"
    try:
        text = (HERE / name).read_text(encoding="utf-8")
    except OSError:
        text = "Tum J.A.R.V.I.S. ho - {USER_NAME} ke Hinglish bolne wale AI dost. Chhote, sach aur madadgar jawab do."
    return text.replace("{USER_NAME}", config.USER_NAME).replace("{HOME_CITY}", config.HOME_CITY)


def _groq_persona() -> str:
    return GROQ_PERSONA_EN if lang.is_english() else GROQ_PERSONA


GROQ_PERSONA_EN = f"""You are J.A.R.V.I.S., {config.USER_NAME}'s AI butler in the style of Iron Man's JARVIS: refined British English,
calm, dry wit, call him "sir". ALWAYS reply in English, even if he speaks Hinglish. Report exactly what tools return. Never act
unprompted. Never invent facts (use tools for news/facts). No lectures. Cut-off sentence -> reply only [SUNO]. Study doubt ->
hint first, full solution when asked. "X protocol" -> run_protocol then do its steps. Notes -> write_document (Markdown, $formulas$).
No city for weather -> get_weather("") = {config.HOME_CITY}. Message starting with 🎙 -> 1-3 short spoken sentences, no markdown."""
GROQ_PERSONA = f"""Tum J.A.R.V.I.S. ho - {config.USER_NAME} ke Hinglish bolne wale AI dost (Tony Stark ke JARVIS jaise, "Boss" bulao).
Niyam: chhote natural Hinglish jawab. Tool ka result jo bole wahi batao. Bina pooche koi kaam mat karo. Kuch banao mat
(news/facts ke liye tool). Lecture mat do. Adhoori baat (vaakya beech me kata) -> sirf [SUNO] likho.
Padhai ka doubt -> pehle hint do, "seedha answer do" bole tab poora. "X protocol" -> run_protocol phir uske steps tools se.
Notes -> write_document (Markdown, formula $...$). Mausam me shehar na ho to get_weather("") = {config.HOME_CITY}.
"🎙" se shuru message = bolke aaya: 2-3 line, bina markdown. "[phone se Telegram pe]" ho to chhota likhit jawab."""


def load_keys():
    """keys.env file se API keys padho (Notepad me key paste karna kaafi hai)."""
    keys_file = HERE / "keys.env"
    if keys_file.exists():
        for line in keys_file.read_text(encoding="utf-8").splitlines():
            name, sep, value = line.partition("=")
            if sep and value.strip() and not name.strip().startswith("#"):
                os.environ.setdefault(name.strip(), value.strip())


# ======================= Tools + dimaag =======================

UI_STATE = lambda state: None        # HUD: arc reactor ki halat
UI_STEP = lambda name, kwargs: None  # HUD: 'abhi kya kar raha hoon'


def logged(fn):
    """Har tool call jarvis.log me (kya chala, kya result) + HUD pe dikhao."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        start = time.time()
        log.info("TOOL %s %s", fn.__name__, json.dumps(kwargs, ensure_ascii=False)[:400])
        UI_STATE("working")
        UI_STEP(fn.__name__, kwargs)
        try:
            result = fn(*args, **kwargs)
        except Exception as e:
            log.exception("TOOL %s FAILED", fn.__name__)
            return f"Error: {type(e).__name__}: {e}"  # dimaag ko batao, crash mat karo
        log.info("TOOL %s -> (%.1fs) %s", fn.__name__, time.time() - start, str(result)[:400])
        return result
    return wrapper


ALL_TOOLS = [logged(t) for t in memory.TOOLS + pc_control.TOOLS + browser.TOOLS + study.TOOLS + planner.TOOLS + gestures.TOOLS]
_groq: GroqBrain | None = None
_last_reply = {"text": ""}


def make_brain():
    global _groq
    system = _load_persona() + "\n\n" + memory.session_context()
    if config.BRAIN == "claude":
        brain = ClaudeBrain(config.CLAUDE_MODEL, system, ALL_TOOLS)
    else:
        brain = GeminiBrain(config.GEMINI_MODEL, system, ALL_TOOLS, config.GEMINI_BACKUP_MODELS)
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if key:
        _groq = GroqBrain(key, config.GROQ_MODEL, _groq_persona(), ALL_TOOLS, facts=memory.list_facts)
    pc_control.VISION = brain.see
    pc_control.DEFAULT_CITY = config.HOME_CITY
    return brain


# ======================= Haan / nahi =======================

YES_WORDS = {"haan", "haa", "han", "ha", "hn", "yes", "yeah", "yep", "sure", "proceed", "affirmative", "ok", "okay",
             "theek", "thik", "bilkul", "zaroor", "bhej",
             "bhejo", "send", "karo", "chalo", "हाँ", "हां", "हा", "हम्म", "ओके", "ठीक", "बिल्कुल", "ज़रूर", "भेज", "भेजो",
             "करो", "कर", "यस", "चलो"}
NO_WORDS = {"nahi", "nahin", "nhi", "no", "nope", "negative", "don", "stop", "mat", "ruko", "cancel", "rehne", "chhodo",
            "नहीं", "नही", "मत", "रुको", "नो",
            "छोड़ो", "रहने"}


def yes_no(text: str | None) -> bool | None:
    """True = haan, False = nahi, None = samajh nahi aaya."""
    words = set(re.findall(r"[\wऀ-ॿ]+", (text or "").lower()))
    if words & NO_WORDS:
        return False
    if words & YES_WORDS:
        return True
    return None


def confirm_by_typing(question: str) -> bool:
    answer_ = yes_no(input(f"\nJARVIS: {question} (haan/nahi): "))
    log.info("CONFIRM %r -> %s", question, answer_)
    return bool(answer_)


def confirm_by_voice(question: str) -> bool:
    import voice

    print(f"\nJARVIS: {question} (haan/nahi bolo)")
    voice.speak(question + " Haan ya nahi?", memory.current_voice())
    for attempt in range(2):
        heard = voice.listen(config.LISTEN_LANGUAGE, groq_key=os.environ.get("GROQ_API_KEY", ""))
        answer_ = yes_no(heard)
        log.info("CONFIRM %r heard=%r -> %s", question, heard, answer_)
        if answer_ is not None:
            return answer_
        if attempt == 0:
            voice.speak("Samajh nahi aaya. Haan ya nahi?", memory.current_voice())
    return False


# ======================= Jawab =======================

GEMINI_COOLDOWN = 90  # Gemini fail ho to itne second seedha Groq (baar-baar 15 sec intezaar nahi)
_route = {"gemini_down_until": 0.0, "missed": []}  # missed: jab Gemini busy tha tab ki baatein (wapas aane pe batao)


_LEAKED = re.compile(r"\[(?:voice mode|system|note)[^\]]*\]|\[SUNO\]|🎙", re.I)


def clean_reply(reply: str) -> str:
    """Andar ki instructions ([voice mode...], [SYSTEM...], 🎙) jawab me aa jaayein to hata do - JARVIS unhe bole nahi."""
    return re.sub(r"\n{3,}", "\n\n", _LEAKED.sub("", reply)).strip()


def ask_brain(brain, prompt: str, image: bytes | None = None) -> str:
    """Pehle Gemini; woh fail ho (ya abhi-abhi fail hua ho) to Groq. Photo ho to Gemini hi (Groq dekh nahi sakta)."""
    gemini_ok = time.time() >= _route["gemini_down_until"] or _groq is None or image is not None
    if gemini_ok:
        try:
            if _route["missed"]:
                gap = "\n".join(f"{r}: {t[:200]}" for r, t in _route["missed"][-8:])
                prompt = f"[Note: jab tum busy the tab ye baatein hui (backup ne jawab diya):\n{gap}]\n\n{prompt}"
            reply = brain.ask(prompt, image=image)
            _route["missed"] = []
            return reply
        except BrainError as e:
            if _groq is None:
                raise
            log.warning("Gemini down (%s) -> %ss tak Groq", e, GEMINI_COOLDOWN)
            _route["gemini_down_until"] = time.time() + GEMINI_COOLDOWN
    reply = _groq.ask(prompt, history=memory.recent_messages(7)[:-1], image=image)
    log.info("(groq) %s", reply[:200])
    _route["missed"] += [("user", prompt), ("jarvis", reply)]
    return reply


def answer(brain, user_text: str, voice_mode: bool, image: bytes | None = None) -> str:
    """JARVIS ka jawab. Khaali string = user ki baat adhoori hai, chup rehkar aage suno."""
    memory.log_message("user", user_text + (" [photo]" if image else ""))
    study.INTENT.update(user=user_text, jarvis=_last_reply["text"])
    prompt = (f"{lang.t('voice_hint')} " if voice_mode else "") + f"[{memory.now()}] {user_text}"
    log.info("USER %s%s", user_text, " [photo]" if image else "")
    try:
        reply = ask_brain(brain, prompt, image)
        if reply.strip().upper().startswith("[SUNO]") or not reply.strip():
            log.info("JARVIS [SUNO] - baat adhoori, sun raha hai")
            return ""
    except BrainError as e:
        log.warning("BRAIN ERROR %s", e)
        return lang.t("busy", e=e)
    except Exception:
        log.exception("UNEXPECTED ERROR")
        return lang.t("error")
    reply = clean_reply(reply)
    log.info("JARVIS %s", reply)
    memory.log_message("jarvis", reply)
    _last_reply["text"] = reply
    return reply


def finish_turn(brain) -> str:
    """JARVIS ne [SUNO] bola tha aur user ruk gaya - ab tak ki baat ka jawab nikalo (kabhi sannata nahi)."""
    try:
        reply = ask_brain(brain, f"{lang.t('voice_hint')} [{memory.now()}] {lang.t('finish')}")
    except Exception as e:
        log.warning("finish_turn failed: %s", e)
        return lang.t("ask_again")
    reply = clean_reply(reply) or lang.t("ask_again")
    log.info("JARVIS (finish) %s", reply)
    memory.log_message("jarvis", reply)
    _last_reply["text"] = reply
    return reply


def plain_text(text: str) -> str:
    """Telegram me markdown ke ### aur ** ajeeb dikhte hain - saaf text bana do."""
    text = re.sub(r"^\s*#{1,6}\s*", "", text, flags=re.M)        # headings
    text = re.sub(r"^\s*[-—_*]{3,}\s*$", "", text, flags=re.M)   # --- lines
    text = re.sub(r"^(\s*)[*-]\s+", r"\1• ", text, flags=re.M)   # bullets
    text = text.replace("**", "").replace("__", "").replace("`", "")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# ======================= Console modes =======================

def reminder_watcher(speak_aloud: bool):
    while True:
        try:
            for due, text in memory.pop_due_reminders():
                print(f"\n[!] REMINDER ({due}): {text}\n")
                if speak_aloud:
                    import voice
                    voice.speak(f"{USER_NAME}, reminder: {text}", memory.current_voice())
        except Exception:
            log.exception("reminder watcher")
        time.sleep(5)


def text_mode(brain):
    pc_control.CONFIRM = confirm_by_typing
    speak = None
    if config.SPEAK_IN_TEXT_MODE:
        import voice
        speak = voice.speak
    while True:
        try:
            user_text = input("\nTum: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user_text:
            continue
        if user_text.lower() in STOP_WORDS:
            break
        reply = answer(brain, user_text, voice_mode=False) or finish_turn(brain)  # likha message adhoora nahi hota
        print(f"\nJARVIS: {reply}")
        if speak:
            speak(reply, memory.current_voice())


def voice_mode(brain):
    import voice

    groq_key = os.environ.get("GROQ_API_KEY", "")
    pc_control.CONFIRM = confirm_by_voice
    voice.calibrate()
    voice.speak(f"JARVIS online. Jab zarurat ho, Hey Jarvis boliye {USER_NAME}.", memory.current_voice())
    while True:
        print("\n[zzz] 'Hey Jarvis' bolo, do taali bajao ya Enter dabao... (Ctrl+C = band)")
        voice.wait_for_wake_word(allow_clap=config.CLAP_WAKE)
        print("JARVIS: Ji?")
        voice.speak("Ji?", memory.current_voice())
        first, pending = True, False
        while True:
            heard = voice.listen(config.LISTEN_LANGUAGE, report_silence=first, timeout=4 if pending else 10, groq_key=groq_key)
            first = False
            if not heard:
                if pending:  # JARVIS chup tha aur user bhi ruk gaya -> ab jawab do
                    pending = False
                    reply = finish_turn(brain)
                    print(f"\nJARVIS: {reply}")
                    voice.speak(reply, memory.current_voice())
                    continue
                break
            print(f"\nTum: {voice.to_roman(heard)}")
            if heard.lower().strip(" .!?।") in STOP_WORDS:
                voice.speak("Theek hai, main yahin hoon.", memory.current_voice())
                break
            reply = answer(brain, heard, voice_mode=True)
            if not reply:
                print("   (sun raha hoon... aage bolo)")
                pending = True
                continue
            pending = False
            print(f"\nJARVIS: {reply}")
            voice.speak(reply, memory.current_voice())


# ======================= Start =======================

_instance = {"server": None, "on_switch": None}


def already_running() -> bool:
    """Doosra JARVIS chal raha hai? (dono ek saath chalein to mic/browser pe ladte hain)"""
    import socket

    probe = socket.socket()
    try:
        probe.bind(("127.0.0.1", config.INSTANCE_PORT))
        return False
    except OSError:
        return True
    finally:
        probe.close()


def start_instance_server() -> bool:
    """Ek hi JARVIS chale: port pe suno. Doosra JARVIS (jaise JARVIS_eng) 'switch en' bheje to - bhasha same ho to
    'same', alag ho to 'bye' bol ke ye wala band ho jata hai (naya wala uski jagah le leta hai)."""
    import socket

    srv = socket.socket()
    try:
        srv.bind(("127.0.0.1", config.INSTANCE_PORT))
        srv.listen(2)
    except OSError:
        srv.close()
        return False
    _instance["server"] = srv

    def loop():
        while True:
            try:
                conn, _ = srv.accept()
            except OSError:
                return
            with conn:
                try:
                    msg = conn.recv(64).decode(errors="ignore").strip()
                except OSError:
                    continue
                if not msg.startswith("switch"):
                    continue
                if msg.split()[-1] == lang.LANG:
                    conn.sendall(b"same\n")
                    continue
                conn.sendall(b"bye\n")
                log.info("Doosra JARVIS (%s) aa raha hai - ye wala band", msg.split()[-1])
                srv.close()
                (_instance["on_switch"] or (lambda: os._exit(0)))()
                return

    threading.Thread(target=loop, daemon=True).start()
    return True


def ask_running_instance(want: str) -> str | None:
    import socket

    try:
        with socket.create_connection(("127.0.0.1", config.INSTANCE_PORT), timeout=3) as conn:
            conn.sendall(f"switch {want}\n".encode())
            return conn.recv(16).decode(errors="ignore").strip()
    except OSError:
        return None


def disable_console_freeze():
    """Windows me cmd window pe click karte hi 'Select' mode aa jaata hai aur program ruk jaata hai. Use band karo."""
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-10)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, (mode.value & ~0x0040) | 0x0080)
    except Exception:
        pass


def _show_error(use_hud: bool, message: str):
    if use_hud:
        from tkinter import messagebox
        messagebox.showinfo("J.A.R.V.I.S.", message)


def main():
    disable_console_freeze()
    for stream in (sys.stdout, sys.stderr, sys.stdin):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    use_voice, use_hud = "--voice" in sys.argv, "--hud" in sys.argv
    lang.set_lang("en" if "--english" in sys.argv else "hi")
    if not start_instance_server():
        # Pehle se JARVIS chal raha hai: alag bhasha ka ho to use hata ke khud chalo (Hinglish <-> English switch)
        if use_hud and ask_running_instance(lang.LANG) == "bye":
            for _ in range(50):
                time.sleep(0.2)
                if start_instance_server():
                    break
        if _instance["server"] is None:
            message = ("JARVIS is already running, sir." if lang.is_english() else
                       "JARVIS pehle se chal raha hai! Pehle wali window use karo (ya use band karke dobara kholo).")
            _show_error(use_hud, message)
            sys.exit(message)
    load_keys()
    atexit.register(browser.close)
    log.info("===== JARVIS start (brain=%s, mode=%s, lang=%s) =====", config.BRAIN,
             "hud" if use_hud else "voice" if use_voice else "text", lang.LANG)
    try:
        brain = make_brain()
    except Exception as e:
        message = f"JARVIS start nahi ho paya: {e}\nkeys.env file me apni API key daali hai? README.md dekho."
        log.exception("START FAILED")
        _show_error(use_hud, message)
        sys.exit("⚠️ " + message)
    if use_hud:
        import hud_app
        hud_app.run(brain)
        return
    print(f"J.A.R.V.I.S. online  (dimaag: {config.BRAIN}, mode: {'voice' if use_voice else 'text'})")
    threading.Thread(target=reminder_watcher, args=(use_voice or config.SPEAK_IN_TEXT_MODE,), daemon=True).start()
    try:
        voice_mode(brain) if use_voice else text_mode(brain)
    except KeyboardInterrupt:
        pass
    print("\nJARVIS: Chalo, milte hain. Take care 🤍")


if __name__ == "__main__":
    main()
