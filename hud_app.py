"""Iron Man mode: arc reactor HUD + 'Hey Jarvis' / do taali / Ctrl+Alt+J + type box + Telegram (phone)
+ briefing + reminders + battery/distraction/aankhon ke alerts.
JARVIS.bat = Hinglish | JARVIS_eng.bat = British English (movie wala JARVIS) - bhasha lang.py se.

Saare kaam ek hi 'worker' thread me hote hain (dimaag, browser, tools) - mic, type box aur phone ke messages ek
queue (inbox) me aate hain. Koi ek kaam fail ho to JARVIS band nahi hota, agle kaam pe chalta rehta hai.
"""

import logging
import os
import queue
import threading
import time

import config
import gestures
import hud
import jarvis
import lang
import memory
import pc_control
import proactive
import study
import voice

log = logging.getLogger("jarvis")


class App:
    def __init__(self, brain):
        self.brain = brain
        self.english = lang.is_english()
        if self.english:  # movie wala JARVIS: shaant British aawaz + halka AI effect
            voice.STYLE.update(rate=config.ENGLISH_VOICE_RATE, pitch=config.ENGLISH_VOICE_PITCH, fx=config.ENGLISH_VOICE_FX)
        self.listen_lang = config.ENGLISH_LISTEN_LANGUAGE if self.english else config.LISTEN_LANGUAGE
        self.inbox: queue.Queue = queue.Queue()   # ("text", t) | ("wake",) | ("telegram"/"telegram_photo"/"telegram_voice", ...)
        self.ui = hud.HUD("J.A.R.V.I.S." + ("  [EN]" if self.english else ""), on_text=lambda t: self.inbox.put(("text", t)),
                          level=voice.level, status=self.status_line, hint=lang.t("hint"), on_hand=self.toggle_gestures)
        self.gestures = gestures.GestureController(self.on_gesture, config.GESTURE_AUTO_OFF_MINUTES)
        gestures.CONTROLLER = self.gestures
        self.groq_key = os.environ.get("GROQ_API_KEY", "").strip()
        self.source = "laptop"                    # request kahan se aayi - confirm wahi poochha jayega
        self.acked = False
        self.bot = None
        self._due_cache = (0.0, 0)
        jarvis.UI_STATE = self.ui.set_state
        jarvis.UI_STEP = self.show_step
        jarvis._instance["on_switch"] = self.shutdown_for_switch
        pc_control.CONFIRM = self.confirm
        self._setup_hotkey()
        self._setup_telegram()

    # ---------------- setup ----------------
    def _setup_hotkey(self):
        try:
            import keyboard

            keyboard.add_hotkey(config.HOTKEY, self.on_hotkey)
        except Exception:
            log.exception("hotkey setup failed")

    def on_hotkey(self):
        if voice.is_speaking():
            voice.stop_speaking()  # bolte waqt hotkey = chup ho jao
        else:
            self.inbox.put(("wake",))

    def _setup_telegram(self):
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            return
        import telegram_bot

        def paired(chat_id):
            memory.set_setting("telegram_owner", str(chat_id))
            self.ui.say("info", "✅ Telegram paired.")

        owner = memory.get_setting("telegram_owner")
        bot = telegram_bot.TelegramBot(
            token, int(owner) if owner else None,
            on_text=lambda t: self.inbox.put(("telegram", t)),
            on_photo=lambda img, caption: self.inbox.put(("telegram_photo", img, caption)),
            on_voice=lambda audio, mime: self.inbox.put(("telegram_voice", audio, mime)),
            on_paired=paired,
        )
        try:
            name = bot.check_token()
        except Exception:
            log.exception("Telegram token check failed")
            self.ui.say("info", "⚠️ Telegram bot offline - keys.env me TELEGRAM_BOT_TOKEN check karo.")
            return
        self.bot = bot
        pc_control.PHONE = bot
        if bot.pair_code:
            self.ui.say("info", f"📱 Telegram pairing: @{name} → {bot.pair_code}")
        threading.Thread(target=bot.run, daemon=True).start()

    def shutdown_for_switch(self):
        """Doosri bhasha wala JARVIS khul raha hai - ye wala chupchaap band."""
        voice.stop_speaking()
        self.ui.close()
        threading.Timer(2.5, lambda: os._exit(0)).start()

    # ---------------- HUD helpers ----------------
    def status_line(self) -> str:
        """HUD ki peeli line: chal raha session, due flashcards, silent mode."""
        parts = []
        session = study.session_status()
        if session:
            parts.append(f"📚 {session[0]} · {session[1]}m {'left' if self.english else 'bache'}")
        now = time.time()
        if now - self._due_cache[0] > 30:
            try:
                self._due_cache = (now, study.due_count())
            except Exception:
                pass
        if self._due_cache[1]:
            parts.append(f"🃏 {self._due_cache[1]} cards due")
        if memory.get_setting("silent") == "1":
            parts.append("🔕 silent")
        if self.gestures.running:
            parts.append("🖐 gestures")
        return "   ".join(parts)

    # ---------------- haath ke ishaare ----------------
    def toggle_gestures(self):
        """HUD ka 🖐 button."""
        def work():
            message = self.gestures.stop() if self.gestures.running else self.gestures.start()
            self.ui.say("info", message)
        threading.Thread(target=work, daemon=True).start()

    GESTURE_LABELS = {"wake": "✌️ JARVIS", "play_pause": "✋ play/pause", "next": "👉 next", "previous": "👈 previous",
                      "volume_up": "👍 volume", "volume_down": "👎 volume", "stop": "✊ stop"}

    def on_gesture(self, event: str):
        """Webcam thread se: ishaara -> kaam (turant, dimaag ki zarurat nahi)."""
        label = self.GESTURE_LABELS.get(event, event)
        if event == "wake":
            self.inbox.put(("wake",))
        elif event == "stop":
            voice.stop_speaking()
        elif event in ("play_pause", "next", "previous"):
            pc_control.media_control(event)
        elif event in ("volume_up", "volume_down"):
            label += f" {pc_control.change_volume(10 if event == 'volume_up' else -10)}%"
        voice.play("ack")
        self.ui.say("info", f"🖐 {label}")

    def show_step(self, name, kwargs):
        if not self.acked:  # har kaam ki shuruaat pe: Hinglish = chhoti 'beep', English = "Right away, sir."
            self.acked = True
            ack = lang.t("acks") if config.ENGLISH_SPOKEN_ACKS else ""
            if ack:
                voice.say_quick(ack, memory.current_voice(), wait=False)  # saath-saath bajta hai, kaam nahi rukta
            else:
                voice.play("ack")
        detail = next((str(v) for v in kwargs.values() if isinstance(v, (str, int, float)) and str(v).strip()), "")
        self.ui.say("info", f"▸ {name.replace('_', ' ')}{(': ' + detail[:50]) if detail else ''}")

    def speak(self, text: str, then: str = "sleeping", interruptible: bool = True) -> bool:
        """Bolo; 'Hey Jarvis' bolke beech me rok sakte ho. True = toka gaya."""
        self.ui.set_state("speaking")
        interrupted = voice.speak(text, memory.current_voice(), interruptible=interruptible)
        if interrupted:
            voice.play("wake")
            self.ui.say("info", lang.t("interrupted"))
            then = "listening"
        self.ui.set_state(then)
        return interrupted

    def notify(self, text: str, phone: bool = False, proactive_: bool = False):
        """JARVIS khud se kuch bataye (reminder, alert). Silent mode me sirf likhe, bole nahi."""
        self.ui.say("JARVIS", text)
        if phone and self.bot:
            self.bot.send(f"🔔 {text}")
        if proactive_ and memory.get_setting("silent") == "1":
            voice.play("alert")
            return
        self.ui.set_state("speaking")
        voice.speak(text, memory.current_voice())  # doosre thread se - beech me tokna nahi (wake word worker ka hai)
        self.ui.set_state("sleeping")

    def notify_phone(self, text: str):   # reminders, battery: phone pe bhi
        self.notify(text, phone=True, proactive_=True)

    def notify_soft(self, text: str):    # distraction / aankhon ka break: sirf laptop pe, halke se
        self.notify(text, proactive_=True)

    # ---------------- confirm (haan/nahi) ----------------
    def confirm(self, question: str) -> bool:
        if self.source == "telegram" and self.bot:
            reply = self.bot.ask(f"❓ {question}\n{lang.t('confirm_hint')}")
            answer_ = jarvis.yes_no(reply)
            log.info("CONFIRM (telegram) %r reply=%r -> %s", question, reply, answer_)
            return bool(answer_)
        self.ui.say("JARVIS", f"{question} {lang.t('confirm_hint')}")
        self.speak(lang.t("confirm_ask", q=question), then="listening", interruptible=False)
        for _ in range(2):
            heard = voice.listen(self.listen_lang, report_silence=False, groq_key=self.groq_key)
            if heard is None and not self.inbox.empty() and self.inbox.queue[0][0] == "text":
                heard = self.inbox.get()[1]
            answer_ = jarvis.yes_no(heard)
            log.info("CONFIRM %r heard=%r -> %s", question, heard, answer_)
            if answer_ is not None:
                self.ui.say(lang.t("you"), voice.to_roman(heard))
                self.ui.set_state("working")
                return answer_
            self.speak(lang.t("confirm_retry"), then="listening", interruptible=False)
        self.ui.set_state("working")
        return False

    # ---------------- baatcheet ----------------
    def handle(self, text: str, spoken: bool) -> bool:
        """True = JARVIS ne jawab diya, False = baat adhoori samjhi (chup hai, aage sun raha hai)."""
        self.ui.say(lang.t("you"), voice.to_roman(text) if spoken else text)
        self.ui.set_state("thinking")
        self.acked = False
        reply = jarvis.answer(self.brain, text, voice_mode=spoken)
        if not reply:
            if not spoken:  # likh ke bheja hai to adhoora nahi hota - turant jawab do
                reply = jarvis.finish_turn(self.brain)
            else:
                self.ui.say("info", lang.t("listening_more"))
                self.ui.set_state("listening")
                return False
        self.ui.say("JARVIS", reply)
        if spoken or len(reply) < 350:
            self.speak(reply, then="listening" if spoken else "sleeping")
        else:
            self.speak(lang.t("on_screen"))
        return True

    def conversation(self):
        """Jagne ke baad: jab tak user bolta rahe, sunte raho."""
        voice.play("wake")
        self.ui.set_state("speaking")
        voice.say_quick(lang.t("wake"), memory.current_voice())  # pehle se bana hua - turant
        first, pending = True, False
        while True:
            self.ui.set_state("listening")
            heard = voice.listen(self.listen_lang, report_silence=first, timeout=4 if pending else 10,
                                 groq_key=self.groq_key)
            if not heard:
                if pending:  # JARVIS chup tha aur user bhi ruk gaya -> ab jawab do
                    pending = False
                    self.ui.set_state("thinking")
                    reply = jarvis.finish_turn(self.brain)
                    self.ui.say("JARVIS", reply)
                    self.speak(reply, then="listening")
                    continue
                if first:
                    self.ui.say("info", lang.t("heard_nothing"))
                return
            first = False
            if heard.lower().strip(" .!?।") in jarvis.STOP_WORDS:
                self.speak(lang.t("stay"))
                return
            pending = not self.handle(heard, spoken=True)

    def handle_phone(self, kind: str, rest: list):
        self.source = "telegram"
        self.ui.set_state("thinking")
        self.acked = True  # phone se aaye kaam pe laptop pe "Right away, sir" bolne ki zarurat nahi
        try:
            image = None
            if kind == "telegram":
                text = rest[0]
            elif kind == "telegram_voice":
                audio, mime = rest
                text = (voice.groq_whisper(audio, self.groq_key, "voice.ogg", mime) if self.groq_key else None) \
                    or self.brain.transcribe(audio, mime)
                if not text:
                    self.bot.send(lang.t("voice_note_fail"))
                    return
                self.bot.send(lang.t("heard_voice_note", text=text))
            else:  # photo: baatcheet ke andar hi, taaki pichli baat ke hisaab se jawab de
                image, caption = rest
                text = lang.t("photo_caption", caption=caption) if caption else lang.t("photo_only")
            self.ui.say(lang.t("you_phone"), ("[photo] " if image else "") + text)
            reply = jarvis.answer(self.brain, f"{lang.t('phone_prefix')} {text}", voice_mode=False, image=image) \
                or lang.t("go_on")
            self.ui.say("JARVIS", reply)
            self.bot.send(jarvis.plain_text(reply))
        finally:
            self.source = "laptop"
            self.ui.set_state("sleeping")

    # ---------------- start ----------------
    def boot_sequence(self):
        """Movie wala boot: aawaz + systems check."""
        voice.play("boot")
        with memory._db() as db:
            facts = db.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
        checks = [
            ("Voice & wake systems", "online" + (" · clap sensor armed" if config.CLAP_WAKE else "")),
            ("Speech engine", "Groq Whisper" if self.groq_key else "Google"),
            ("Language", "British English" if self.english else "Hinglish"),
            ("Memory core", lang.t("memories", n=facts)),
            ("Telegram uplink", "online" if self.bot and self.bot.owner_id else "offline"),
            ("Backup brain (Groq)", "standby" if self.groq_key else "offline"),
            ("Neural link (Gemini)", "online"),
        ]
        for name, status in checks:
            self.ui.say("info", f"▸ {name} ... {status}")
            time.sleep(0.25)

    def start_background(self):
        threads = [(self._reminder_loop, ()),
                   (proactive.battery_watcher, (self.notify_phone,)),
                   (study.activity_tracker, (self.notify_soft,))]
        if config.REVIEW_TIME:
            threads.append((proactive.daily_review_watcher, (config.REVIEW_TIME, self.notify_phone)))
        if config.SCREEN_BREAK_MINUTES:
            threads.append((proactive.screen_break_watcher, (config.SCREEN_BREAK_MINUTES, self.notify_soft)))
        for target, args in threads:
            threading.Thread(target=target, args=args, daemon=True).start()

    def _reminder_loop(self):
        while True:
            try:
                for _due, text in memory.pop_due_reminders():
                    is_timer_or_session = text.startswith("⏱") or "session" in text.lower()
                    self.notify_phone(text if is_timer_or_session else lang.t("reminder", text=text))
            except Exception:
                log.exception("reminder loop")
            time.sleep(5)

    def _prepare_phrases(self):
        """Chhote tay vaakya pehle se bana lo (baad me turant bolein)."""
        for key in ("wake", "acks"):
            for text in lang.PHRASES[lang.LANG][key]:
                try:
                    voice.prepare_phrase(text, memory.current_voice())
                except Exception:
                    pass

    def worker(self):
        try:
            self.ui.say("info", lang.t("mic_setup"))
            voice.calibrate()
            self.acked = True  # briefing ke tools pe "Right away, sir" nahi
            threading.Thread(target=self._prepare_phrases, daemon=True).start()
            self.boot_sequence()
            if config.MORNING_BRIEFING:
                self.ui.set_state("thinking")
                try:
                    briefing = jarvis.ask_brain(self.brain, proactive.briefing_prompt(config.USER_NAME))
                except Exception as e:
                    log.warning("briefing failed: %s", e)
                    briefing = lang.t("greeting_fallback", greet=proactive.greeting(), name=config.USER_NAME)
                briefing = jarvis.clean_reply(briefing)
                memory.log_message("jarvis", briefing)
                self.ui.say("JARVIS", briefing)
                self.speak(briefing)
            else:
                self.speak(lang.t("greeting_fallback", greet=proactive.greeting(), name=config.USER_NAME))
        except Exception:
            log.exception("startup failed")
        self.start_background()
        if self.bot and self.bot.owner_id:
            self.bot.send(lang.t("online_phone"))
        while True:
            try:
                if not self._loop_once():
                    return
            except Exception:  # ek kaam fail -> JARVIS chalta rahe
                log.exception("worker step failed")
                self.ui.say("info", lang.t("step_error"))
                self.ui.set_state("sleeping")
                time.sleep(1)

    def _loop_once(self) -> bool:
        self.ui.set_state("sleeping")
        trigger = voice.wait_for_wake_word(interrupt=lambda: not self.inbox.empty(), allow_clap=config.CLAP_WAKE)
        if trigger == "clap":
            self.ui.say("info", lang.t("clap"))
        if trigger in ("wake", "enter", "clap"):
            self.conversation()
            return True
        kind, *rest = self.inbox.get()
        if kind == "wake":
            self.conversation()
        elif kind.startswith("telegram"):
            self.handle_phone(kind, rest)
        else:
            text = rest[0]
            if text.lower() in jarvis.STOP_WORDS:
                self.speak(lang.t("goodbye"), interruptible=False)
                self.ui.close()
                return False
            self.handle(text, spoken=False)
        return True

    def run(self):
        threading.Thread(target=self.worker, daemon=True).start()
        self.ui.run()  # Tkinter main thread me


def run(brain):
    App(brain).run()
