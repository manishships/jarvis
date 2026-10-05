"""JARVIS Self Test - sab hisse check karo (kuch bhejta/badalta nahi, asli memory ko nahi chhoota).
Run: python selftest.py   (ya Self Test.bat)"""

import io
import json
import os
import sqlite3
import sys
import tempfile
import time
import traceback

for stream in (sys.stdout, sys.stderr):
    stream.reconfigure(encoding="utf-8")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
HERE = os.path.dirname(os.path.abspath(__file__))

import memory  # noqa: E402

REAL_DB = str(memory.DB_PATH)
memory.DB_PATH = memory.Path(tempfile.gettempdir()) / "jarvis_selftest.db"  # asli memory ko mat chhuo
if memory.DB_PATH.exists():
    memory.DB_PATH.unlink()

import jarvis  # noqa: E402
import pc_control  # noqa: E402
import study  # noqa: E402

results = []


def check(name, fn):
    start = time.time()
    try:
        detail = fn()
        results.append(True)
        print(f"[PASS] {name} ({time.time() - start:.1f}s) {detail or ''}")
    except Exception as e:
        results.append(False)
        print(f"[FAIL] {name}: {e}")
        with open(os.path.join(HERE, "jarvis.log"), "a", encoding="utf-8") as f:
            f.write(f"SELFTEST FAIL {name}\n")
            traceback.print_exc(limit=3, file=f)


jarvis.load_keys()
brain = None
pc_control.os.startfile = lambda path: None  # test me koi file/browser na khule


def t_brain():
    global brain
    brain = jarvis.make_brain()
    reply = jarvis.answer(brain, "selftest: sirf 'OK' likho", voice_mode=False)
    assert reply and not reply.startswith("⚠️"), reply
    return f"-> {reply[:30]!r} (model: {getattr(brain, 'model', '?')})"


def t_tool_call():
    reply = jarvis.answer(brain, "laptop ki battery kitni hai? tool se check karke number batao", voice_mode=False)
    assert any(c.isdigit() for c in reply), reply
    return f"-> {reply[:60]!r}"


def t_groq():
    if jarvis._groq is None:
        return "(GROQ_API_KEY nahi - optional, skip)"
    reply = jarvis._groq.ask("selftest: sirf OK likho")
    assert reply, "khaali jawab"
    return f"-> {reply[:20]!r} ({jarvis._groq.model})"


def t_groq_whisper():
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if not key:
        return "(skip)"
    import edge_tts
    import voice
    path = os.path.join(tempfile.gettempdir(), "jarvis_selftest_stt.mp3")
    edge_tts.Communicate("Jarvis, kal subah saat baje physics ka revision yaad dilana", "hi-IN-MadhurNeural").save_sync(path)
    text = voice.groq_whisper(open(path, "rb").read(), key, "a.mp3", "audio/mpeg")
    assert text and "physics" in text.lower(), text
    return f"-> {text[:50]!r}"


def t_vision():
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (500, 120), "white")
    ImageDraw.Draw(img).text((10, 50), "2 + 3 = ?", fill="black")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    reply = pc_control.VISION(buf.getvalue(), "Answer with just the number.")
    assert "5" in reply, reply
    return f"-> {reply.strip()[:20]!r}"


def t_memory():
    memory.log_message("user", "pehla test sawaal")
    assert "pehla test" in memory.search_memory("pehla test", True, 1)
    memory.remember("test fact gym")
    assert "gym" in memory.list_facts()
    assert "Bhool gaya" in memory.forget_fact("gym")
    assert memory.normalize_phone("98765 43210") == "919876543210"
    return ""


def t_reminders():
    from datetime import datetime, timedelta
    assert "Reminder" in memory.set_reminder("roz test", datetime.now().strftime("%Y-%m-%d %H:%M"), "daily")
    assert "Timer" in memory.set_timer(0.01, "selftest")
    time.sleep(1)
    due = memory.pop_due_reminders()
    assert len(due) == 2, due
    assert "roz test" in memory.list_reminders(), "roz wala reminder aage nahi badha"
    assert "Cancel" in memory.cancel_reminder("roz test")
    return "roz wala + timer + cancel"


def t_protocols():
    assert "ACTIVATED" in memory.run_protocol("night protocol")
    assert "save" in memory.save_protocol("selftest", "volume 10")
    assert "hata" in memory.delete_protocol("selftest")
    return ""


def t_yes_no():
    cases = {"haan": True, "हां भाई भेज दो": True, "bhej do na": True, "nahi": False, "मत भेजो": False,
             "rehne do": False, "kya?": None, None: None}
    bad = {k: jarvis.yes_no(k) for k, v in cases.items() if jarvis.yes_no(k) is not v}
    assert not bad, bad
    return ""


def t_intent_guard():
    study.INTENT.update(user="physics ke notes bana do", jarvis="")
    assert study.start_study("Physics", 45).startswith("RUKO"), "bina pooche session khul gaya!"
    study.INTENT.update(user="45 minute physics padhna hai")
    assert "shuru" in study.start_study("Physics", 45)
    assert "band" in study.stop_study()
    return "bina pooche session nahi khulta"


def t_flashcards():
    assert "save" in study.add_flashcards("Test", "2+2? | 4\nSun kis disha me ugta hai? | Purab")
    card = json.loads(study.quiz_next("Test"))
    assert "Saved" in study.quiz_grade(card["card_id"], "good")
    return f"{card['cards_due_total']} due the, ek grade kiya"


def t_notes_html():
    path = pc_control.write_document("Selftest notes", "## Formula\n$E = mc^2$ aur **bold**\n\n| a | b |\n|---|---|\n| 1 | 2 |").split("Path: ")[1]
    html = open(path, encoding="utf-8").read()
    os.remove(path)
    assert "$E = mc^2$" in html and "<table>" in html and "MathJax" in html
    return "HTML + formulas + table"


def t_system():
    s = pc_control.system_status()
    assert "battery_percent" in s
    return s[:90]


def t_volume_brightness_same():
    s = json.loads(pc_control.system_status())
    pc_control.set_volume(s["volume_percent"])
    if s["brightness_percent"] is not None:
        pc_control.set_brightness(s["brightness_percent"])
    return "(abhi wali value pe hi set kiya)"


def t_apps():
    apps = pc_control._start_apps()
    assert len(apps) > 10
    return f"{len(apps)} apps mile"


def t_ui_controls():
    return pc_control.screen_controls().splitlines()[0][:60]


def t_web():
    result = memory.web_search("Delhi weather")
    assert "title" in result or "Google News" in result, result[:200]
    assert "temp_c" in pc_control.get_weather("")
    assert memory.news_headlines("").startswith("- ")
    return "search + mausam + news"


def t_tts():
    import edge_tts
    path = os.path.join(tempfile.gettempdir(), "jarvis_selftest.mp3")
    edge_tts.Communicate("test", memory.current_voice()).save_sync(path)
    assert os.path.getsize(path) > 1000
    return memory.current_voice()


def t_mic():
    import numpy as np
    import pyaudio
    pa = pyaudio.PyAudio()
    stream = pa.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=1280)
    audio = np.concatenate([np.frombuffer(stream.read(1280, exception_on_overflow=False), dtype=np.int16) for _ in range(12)])
    stream.close()
    pa.terminate()
    level = int(np.sqrt(np.mean(audio.astype(float) ** 2)))
    assert level > 0, "mic se bilkul aawaz nahi aa rahi (mute? privacy setting?)"
    return f"mic chalu (level {level})"


def t_clap_detector():
    """Banawati taali (asli mic jaisi) + chuppi -> do taali pakdi jaye, ek taali pe nahi."""
    import numpy as np
    import voice
    rng = np.random.default_rng(7)

    def clap(peak):
        t = np.arange(int(16000 * 0.12)) / 16000
        return rng.normal(0, 1, t.size) * np.minimum(1, t / 0.002) * np.exp(-t / 0.012) * peak

    def scene(clap_times):
        audio = rng.normal(0, 4, 16000 * 4)
        for at in clap_times:
            c = clap(4000)
            i = int(at * 16000)
            audio[i:i + c.size] += c
        return audio.astype(np.int16)

    def run(audio):
        det = voice.ClapDetector()
        return sum(det.feed(audio[n * 1280:(n + 1) * 1280], n * 0.08, 99.0, False) for n in range(len(audio) // 1280))

    double, single = run(scene([1.0, 1.4])), run(scene([1.0]))
    assert double == 1 and single == 0, (double, single)
    return "do taali ✓, ek taali ✗"


def t_wake_model():
    import numpy as np
    import openwakeword.utils
    from openwakeword.model import Model
    openwakeword.utils.download_models(model_names=["hey_jarvis"])
    Model(wakeword_models=["hey_jarvis"], inference_framework="onnx").predict(np.zeros(1280, dtype=np.int16))
    return ""


def t_browser():
    import browser
    if jarvis.already_running():
        return "(skip - JARVIS chal raha hai, browser usi ke paas hai)"
    text = browser.browse_open("https://example.com")
    assert "Example Domain" in text, text[:200]
    page, err = browser._whatsapp_ready()
    browser.close()
    return "WhatsApp: logged in ✓" if page else f"WhatsApp: {err[:60]}..."


def t_study_report():
    report = study.study_report(1)
    assert "streak" in report.lower(), report
    return report[:70]


def t_screen_tracker():
    title, proc = study.active_window()
    return f"abhi: {study.label_for(title, proc)}"


def t_sounds():
    import voice
    voice._make_sounds()
    return ", ".join(sorted(p.stem for p in voice.SOUNDS_DIR.glob("*.wav")))


def t_hud():
    import threading
    import hud
    ui = hud.HUD("test", on_text=lambda t: None, status=lambda: "📚 test")
    ui.say("JARVIS", "test")
    threading.Timer(1.5, ui.close).start()
    ui.run()
    return ""


def t_planner():
    import planner
    assert "integrals" in planner.set_backlog("Maths", "Integration", 4)
    assert "alternating current" in planner.set_backlog("Physics", "AC", 2)
    plan = json.loads(planner.study_plan(3, 0))
    assert plan["days_needed"] >= 1 and plan["first_7_days"], plan
    assert planner.today_plan().startswith("Aaj:")
    assert "baaki" in planner.lectures_done("maths", "integrals", 1)
    assert "diary" in planner.log_mistake("Physics", "AC", "Phase in pure L?", "V leads I by 90 deg", "same phase", "concept")
    assert "weak_chapters" in planner.mistake_report(7)
    assert len(json.loads(planner.practice_set("Physics, Chemistry", 5))["questions"]) == 5
    return f"plan {plan['days_needed']} din, {plan['lectures_per_day']} lec/din"


def t_gesture_model():
    import mediapipe as mp
    import numpy as np
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision

    import gestures
    rec = vision.GestureRecognizer.create_from_options(vision.GestureRecognizerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=str(gestures.ensure_model())),
        running_mode=vision.RunningMode.IMAGE))
    blank = rec.recognize(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.zeros((240, 320, 3), np.uint8)))
    assert not blank.gestures, "khaali image me haath dikh gaya?"
    sample = os.path.join(tempfile.gettempdir(), "victory.jpg")
    if os.path.exists(sample):
        top = rec.recognize(mp.Image.create_from_file(sample)).gestures[0][0]
        assert top.category_name == "Victory", top
        return f"model ✓, ✌️ sample -> {top.category_name} ({top.score:.2f})"
    return "model ✓ (webcam test nahi kiya)"


def t_english_mode():
    import lang
    import voice
    missing = set(lang.PHRASES["hi"]) ^ set(lang.PHRASES["en"])
    assert not missing, f"phrase keys missing: {missing}"
    lang.set_lang("en")
    try:
        persona = jarvis._load_persona()
        assert "British English" in persona, "soul_en.md nahi mila"
        assert memory.current_voice().startswith("en-GB"), memory.current_voice()
        old_style = dict(voice.STYLE)
        voice.STYLE.update(rate="-4%", pitch="-3Hz", fx=True)
        try:
            path = voice._synth("Good evening, sir.", memory.current_voice(), os.path.join(tempfile.gettempdir(), "jarvis_selftest_en"))
        finally:
            voice.STYLE.clear()
            voice.STYLE.update(old_style)
        assert path.endswith(".wav") and os.path.getsize(path) > 10000
        return f"{memory.current_voice()} + AI effect, '{lang.t('acks')}'"
    finally:
        lang.set_lang("hi")


def t_telegram():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        return "(token abhi keys.env me nahi hai - skip)"
    import telegram_bot
    name = telegram_bot.TelegramBot(token, None, None, None, None).check_token()
    row = sqlite3.connect(REAL_DB).execute("SELECT value FROM settings WHERE key = 'telegram_owner'").fetchone()
    return f"@{name} ✓ (pairing: {'ho chuki' if row else 'baaki'})"


print("JARVIS Self Test (kuch bhejta/badalta nahi)\n")
if jarvis.already_running():
    print("(JARVIS abhi chal raha hai - browser wala test skip hoga)\n")
check("Dimaag (Gemini) jawab deta hai", t_brain)
if brain:
    check("Tool use (battery)", t_tool_call)
    check("Screen/photo vision", t_vision)
check("Backup dimaag (Groq)", t_groq)
check("Groq Whisper (Hinglish sunna)", t_groq_whisper)
check("Memory / yaadein", t_memory)
check("Reminders (roz wala, timer, cancel)", t_reminders)
check("Protocols", t_protocols)
check("Haan/nahi samajhna", t_yes_no)
check("Bina pooche session nahi", t_intent_guard)
check("Flashcards + quiz", t_flashcards)
check("Study report", t_study_report)
check("Notes (HTML + formula)", t_notes_html)
check("Laptop status", t_system)
check("Volume/brightness control", t_volume_brightness_same)
check("Installed apps list", t_apps)
check("App buttons padhna (UI Automation)", t_ui_controls)
check("Internet: search + mausam + news", t_web)
check("Aawaz banana (TTS)", t_tts)
check("Mic", t_mic)
check("Taali detector", t_clap_detector)
check("'Hey Jarvis' model", t_wake_model)
check("JARVIS browser + WhatsApp", t_browser)
check("Screen time tracker", t_screen_tracker)
check("Sound effects", t_sounds)
check("HUD window", t_hud)
check("Telegram bot", t_telegram)
check("English JARVIS (JARVIS_eng)", t_english_mode)
check("Backlog planner + galti diary + practice", t_planner)
check("Haath ke ishaare (gesture model)", t_gesture_model)

print(f"\n{sum(results)}/{len(results)} PASS")
if not all(results):
    print("Jo FAIL hue unki details jarvis.log me hain.")
if "--no-pause" not in sys.argv:
    input("\nEnter dabao band karne ke liye...")
