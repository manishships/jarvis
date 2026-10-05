"""JARVIS ki aawaz aur kaan.

- Bolna: edge-tts, vaakya-dar-vaakya (pehla vaakya bante hi bolna shuru - jawab jaldi sunai deta hai)
- Sunna: Groq Whisper (Hinglish, Roman me) ya Google
- Jagna: 'Hey Jarvis' (offline openWakeWord) ya do taali (khud ka detector)
- Bolte waqt 'Hey Jarvis' bolo to beech me ruk jata hai
- Sound effects (boot, wake, ack...) - khud bante hain, koi download nahi
"""

import contextlib
import logging
import os
import queue
import re
import tempfile
import threading
import time
import wave
from pathlib import Path

import edge_tts
import numpy as np
import pyaudio
import speech_recognition as sr

import lang

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame  # noqa: E402

pygame.mixer.init(frequency=24000, size=-16, channels=1)
log = logging.getLogger("jarvis")
_recognizer = sr.Recognizer()
_wake_model = None
_wake_lock = threading.Lock()
_speak_lock = threading.Lock()
_stop_flag = threading.Event()
_level = {"env": None, "start": 0.0}  # bolte waqt aawaz ka loudness (reactor isse dhadakta hai)
SOUNDS_DIR = Path(__file__).with_name("sounds")
_own_sound = {"t": 0.0}  # JARVIS ne khud aawaz kab nikali (uski beep ko taali na samjho)
STYLE = {"rate": "+0%", "pitch": "+0Hz", "fx": False}  # English JARVIS: thoda dheema, gehra + "AI system" effect


def _jarvis_fx(x: np.ndarray, sr: int = 24000) -> np.ndarray:
    """Movie jaisa halka 'AI system' rang: thodi si metallic doubling + chhote kamre ki goonj + saaf highs."""
    x = x.astype(np.float32) / 32768
    y = x.copy()

    def delayed(sig, ms, gain):
        d = int(sr * ms / 1000)
        out = np.zeros_like(sig)
        out[d:] = sig[:-d] * gain
        return out

    y += delayed(x, 9, 0.16)                                                        # doubling (AI sheen)
    y += delayed(x, 29, 0.10) + delayed(x, 43, 0.07) + delayed(x, 67, 0.05)        # chhota kamra
    y[1:] += 0.18 * (y[1:] - y[:-1])                                                # presence (saaf aawaz)
    y *= (np.sqrt(np.mean(x ** 2)) / max(np.sqrt(np.mean(y ** 2)), 1e-9))          # loudness pehle jitni
    peak = np.abs(y).max()
    if peak > 0.95:
        y *= 0.95 / peak
    return (y * 32767).astype(np.int16)


def _synth(text: str, voice: str, path_base: str) -> str:
    """Text -> audio file (style ke saath). Effect ho to WAV, warna MP3."""
    mp3 = path_base + ".mp3"
    edge_tts.Communicate(text, voice, rate=STYLE["rate"], pitch=STYLE["pitch"]).save_sync(mp3)
    if not STYLE["fx"]:
        return mp3
    samples = pygame.sndarray.array(pygame.mixer.Sound(mp3))
    samples = samples[:, 0] if samples.ndim > 1 else samples
    wav = path_base + ".wav"
    with wave.open(wav, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(pygame.mixer.get_init()[0])
        w.writeframes(_jarvis_fx(samples, pygame.mixer.get_init()[0]).tobytes())
    os.remove(mp3)
    return wav


_phrase_lock = threading.Lock()


def prepare_phrase(text: str, voice: str) -> Path:
    """Chhota tay vaakya ek baar bana ke sounds/phrases me rakh lo (baad me turant bajta hai)."""
    import hashlib

    folder = SOUNDS_DIR / "phrases"
    folder.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(f"{voice}|{sorted(STYLE.items())}|{text}".encode()).hexdigest()[:16]
    with _phrase_lock:  # do thread ek saath ek hi file na banayein
        cached = next(iter(folder.glob(key + ".*")), None)
        if cached is None:
            cached = Path(_synth(text, voice, str(folder / key)))
    return cached


def say_quick(text: str, voice: str, wait: bool = True) -> None:
    """Chhote tay vaakya ('Yes, sir?', 'Right away, sir.') turant bolo. wait=False: saath-saath bajta hai (kaam nahi rukta)."""
    if not text:
        return
    try:
        sound = pygame.mixer.Sound(str(prepare_phrase(text, voice)))
        _own_sound["t"] = time.time() + sound.get_length()
        channel = sound.play()
        while wait and channel is not None and channel.get_busy():
            time.sleep(0.03)
    except Exception as e:
        print(f"(aawaz nahi aa payi: {e})")


# ======================= Sound effects =======================

def _tone(freqs, duration, volume=0.35, rate=24000, fade=0.02):
    t = np.linspace(0, duration, int(rate * duration), endpoint=False)
    f = np.linspace(freqs[0], freqs[-1], t.size) if len(freqs) == 2 else np.full(t.size, freqs[0])
    wave_ = np.sin(2 * np.pi * np.cumsum(f) / rate) * 0.7 + np.sin(4 * np.pi * np.cumsum(f) / rate) * 0.3
    env = np.minimum(1, np.minimum(t / fade, (duration - t) / fade))
    return wave_ * env * volume


def _write(name, samples, rate=24000):
    SOUNDS_DIR.mkdir(exist_ok=True)
    with wave.open(str(SOUNDS_DIR / f"{name}.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((np.clip(samples, -1, 1) * 32767).astype(np.int16).tobytes())


def _make_sounds():
    """Iron Man style chhoti aawazein ek baar bana lo."""
    if (SOUNDS_DIR / "boot.wav").exists():
        return
    gap = lambda s: np.zeros(int(24000 * s))
    boot = np.concatenate([_tone([180, 900], 0.9, 0.25), gap(0.05), _tone([660], 0.12), gap(0.03),
                           _tone([880], 0.12), gap(0.03), _tone([1320], 0.35, 0.3, fade=0.08)])
    _write("boot", boot)
    _write("wake", np.concatenate([_tone([880], 0.07), gap(0.02), _tone([1320], 0.1)]))
    _write("ack", _tone([1200, 1600], 0.06, 0.2))
    _write("done", np.concatenate([_tone([1320], 0.07), gap(0.02), _tone([990], 0.1)]))
    _write("alert", np.concatenate([_tone([700], 0.12), gap(0.05), _tone([700], 0.12)]))


def play(name: str) -> None:
    """Sound effect chalao (turant, rukta nahi)."""
    try:
        _make_sounds()
        _own_sound["t"] = time.time() + 0.5
        pygame.mixer.Sound(str(SOUNDS_DIR / f"{name}.wav")).play()
    except Exception:
        pass


# ======================= Bolna =======================

def _clean_for_speech(text: str) -> str:
    text = re.sub(r"https?://\S+", "", text)                          # links bolne ka fayda nahi
    text = re.sub(r"\$+([^$]*)\$+", r"\1", text)                       # $formula$ ke dollar
    text = re.sub(r"[*#_`>|~\\]", "", text)                            # markdown symbols
    text = re.sub(r"[\U0001F300-\U0001FAFF☀-➿]", "", text)   # emojis
    return re.sub(r"\s+", " ", text).strip()


def _chunks(text: str, first_max: int = 120, max_len: int = 260) -> list[str]:
    """Vaakya me todo - pehla chhota (jaldi bolna shuru ho), baaki thode bade."""
    sentences = [s for s in re.split(r"(?<=[.!?।])\s+", text) if s.strip()]
    out, cur = [], ""
    for s in sentences:
        limit = first_max if not out else max_len
        if cur and len(cur) + len(s) > limit:
            out.append(cur)
            cur = s
        else:
            cur = f"{cur} {s}".strip()
    if cur:
        out.append(cur)
    return out


def speak(text: str, voice: str, interruptible: bool = False) -> bool:
    """Bolo. interruptible=True pe user 'Hey Jarvis' bolke beech me rok sakta hai. True lautaye = beech me toka gaya."""
    text = _clean_for_speech(text)
    if not text:
        return False
    with _speak_lock:  # reminder aur jawab ek saath na bolein
        return _speak(text, voice, interruptible)


def _envelope(path: str):
    """Aawaz ka loudness har 40ms pe (reactor ke liye)."""
    try:
        samples = pygame.sndarray.array(pygame.mixer.Sound(path)).astype(np.float32)
        if samples.ndim > 1:
            samples = samples.mean(axis=1)
        step = int(pygame.mixer.get_init()[0] * 0.04)
        rms = np.array([np.sqrt(np.mean(samples[i:i + step] ** 2)) for i in range(0, len(samples), step)])
        return rms / (rms.max() or 1)
    except Exception:
        return None


def level() -> float:
    """Abhi JARVIS kitni zor se bol raha hai (0..1)."""
    env = _level["env"]
    if env is None or not pygame.mixer.music.get_busy():
        return 0.0
    i = int((time.time() - _level["start"]) / 0.04)
    return float(env[i]) if 0 <= i < len(env) else 0.0


def _speak(text: str, voice: str, interruptible: bool) -> bool:
    _stop_flag.clear()
    interrupted = threading.Event()
    files: queue.Queue = queue.Queue()
    pieces = _chunks(text)

    def producer():  # agla vaakya pehle se ban raha hota hai jab tak pichla bol raha hai
        for i, piece in enumerate(pieces):
            if _stop_flag.is_set():
                break
            try:
                path = _synth(piece, voice, os.path.join(tempfile.gettempdir(), f"jarvis_{time.time_ns()}_{i}"))
                if _stop_flag.is_set():  # beech me rok diya gaya - ye file ab kaam ki nahi
                    os.remove(path)
                    break
                files.put(path)
            except Exception as e:
                print(f"(aawaz nahi aa payi: {e})")
                break
        files.put(None)

    threading.Thread(target=producer, daemon=True).start()
    if interruptible:
        def watch():
            if wait_for_wake_word(threshold=0.6, interrupt=lambda: _stop_flag.is_set() or not _speak_lock.locked(),
                                  allow_enter=False, allow_clap=False) == "wake":
                interrupted.set()
                stop_speaking()
        threading.Thread(target=watch, daemon=True).start()

    played = []
    try:
        while not _stop_flag.is_set():
            try:
                path = files.get(timeout=20)
            except queue.Empty:
                break
            if path is None:
                break
            played.append(path)
            _level["env"] = _envelope(path)
            pygame.mixer.music.load(path)
            pygame.mixer.music.play()
            _level["start"] = time.time()
            while pygame.mixer.music.get_busy() and not _stop_flag.is_set():
                _own_sound["t"] = time.time()
                time.sleep(0.03)
            pygame.mixer.music.unload()
    finally:
        _stop_flag.set()  # interrupt-watcher aur producer ko band karo
        _level["env"] = None
        while True:  # bachi hui files bhi saaf
            try:
                path = files.get_nowait()
            except queue.Empty:
                break
            if path:
                played.append(path)
        for path in played:
            try:
                os.remove(path)
            except OSError:
                pass
    return interrupted.is_set()


def stop_speaking() -> None:
    """Bolte hue JARVIS ko beech me chup karao (hotkey / 'Hey Jarvis' se)."""
    _stop_flag.set()
    try:
        pygame.mixer.music.stop()
    except Exception:
        pass


def is_speaking() -> bool:
    return _speak_lock.locked()


def to_roman(text: str) -> str:
    """Hindi (Devanagari) ko Roman me badlo - sirf screen pe dikhane ke liye."""
    if not re.search(r"[ऀ-ॿ]", text):
        return text
    from indic_transliteration import sanscript

    words = []
    for word in sanscript.transliterate(text, sanscript.DEVANAGARI, sanscript.ITRANS).split():
        if len(word) > 2 and word.endswith("a") and not word.endswith("aa"):
            word = word[:-1]  # 'kala' -> 'kal', 'subaha' -> 'subah'
        word = word.replace(".N", "n").replace("~N", "n").replace("M", "n")
        words.append(word.lower())
    return " ".join(words)


# ======================= Sunna =======================

def calibrate() -> None:
    """Shuru me ek baar, chup-chaap kamre ka noise naap lo (bolte waqt naapa to tumhari aawaz ko noise samajh leta hai)."""
    print("[mic] 1 second chup raho, mic set ho raha hai...")
    with sr.Microphone() as source:
        _recognizer.adjust_for_ambient_noise(source, duration=1.0)
    # Laptop mic dheemi hoti hai - threshold zyada ho gaya to normal aawaz bhi nahi pakdega
    _recognizer.energy_threshold = min(max(_recognizer.energy_threshold, 150), 1500)
    _recognizer.pause_threshold = 2.0  # 2 sec chup rahoge tab baat khatam maanega (beech ke chhote ruke pe nahi)
    _recognizer.non_speaking_duration = 0.8
    print(f"[mic] ready (level {int(_recognizer.energy_threshold)})")


DUCK_LEVEL = 0.12  # sunte waqt baaki apps (gaana/video/ad) ki aawaz itni kar do


@contextlib.contextmanager
def ducked():
    """Sunte waqt gaana/video/ad dheema - warna mic speaker ki aawaz ko user ki baat samajh leta hai (Alexa jaisa)."""
    lowered = []
    try:
        import comtypes
        from pycaw.pycaw import AudioUtilities

        comtypes.CoInitialize()
        for s in AudioUtilities.GetAllSessions():
            if s.Process is None or s.ProcessId == os.getpid():
                continue  # system sounds aur JARVIS ki apni aawaz nahi
            vol = s.SimpleAudioVolume
            before = vol.GetMasterVolume()
            if before > DUCK_LEVEL:
                vol.SetMasterVolume(DUCK_LEVEL, None)
                lowered.append((vol, before))
    except Exception:
        log.debug("duck failed", exc_info=True)
    try:
        yield
    finally:
        for vol, before in lowered:
            try:
                if abs(vol.GetMasterVolume() - DUCK_LEVEL) < 0.01:  # user ne beech me khud nahi badla to wapas
                    vol.SetMasterVolume(before, None)
            except Exception:
                pass


def listen(language: str, report_silence: bool = True, timeout: float = 10, groq_key: str = "") -> str | None:
    """Mic se ek baat suno aur text me badlo. Groq key ho to Whisper (Hinglish Roman me), warna Google. Na samjhe to None."""
    with ducked(), sr.Microphone() as source:
        print(">> Sun raha hoon... ab bolo")
        try:
            audio = _recognizer.listen(source, timeout=timeout, phrase_time_limit=90)  # lambi baat bhi poori suno
        except sr.WaitTimeoutError:
            if report_silence:
                print("   (10 second me koi aawaz nahi pakdi - mic ke paas aake thoda zor se bolo)")
            return None
    print("   (samajh raha hoon...)")
    if groq_key:
        text = groq_whisper(audio.get_wav_data(), groq_key)
        if text:
            return text
    try:
        return _recognizer.recognize_google(audio, language=language)
    except sr.UnknownValueError:
        print("   (aawaz aayi par shabd samajh nahi aaye - thoda saaf aur dheere bolo)")
        return None
    except sr.RequestError as e:
        print(f"   (speech service error, internet check karo: {e})")
        return None


WHISPER_PROMPT_EN = "A conversation with JARVIS, an AI assistant. For example: Jarvis, what's the weather like? Play some music."
WHISPER_PROMPT = ("Hinglish baatcheet JARVIS ke saath, Roman script me. Jaise: Jarvis, physics ka quiz lo. "
                  "Rahul ko WhatsApp karo ki main late aaunga.")
WHISPER_JUNK = ("thank you for watching", "thanks for watching", "subscribe", "subtitles by", "please like",
                "rahul ko whatsapp karo ki main late aaunga", "physics ka quiz lo", "what's the weather like? play some music")


def groq_whisper(audio: bytes, key: str, filename: str = "a.wav", mime: str = "audio/wav") -> str | None:
    """Groq ka free Whisper - Hindi-English mix (Hinglish) achhe se samajhta hai, aur Roman me likhta hai."""
    import json
    import urllib.request
    import uuid

    boundary = uuid.uuid4().hex
    parts = []
    for name, value in (("model", "whisper-large-v3-turbo"), ("response_format", "verbose_json"), ("temperature", "0"),
                        ("prompt", WHISPER_PROMPT_EN if lang.is_english() else WHISPER_PROMPT)):
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
                 f"Content-Type: {mime}\r\n\r\n".encode() + audio + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/audio/transcriptions", data=b"".join(parts),
        headers={"Authorization": f"Bearer {key}", "Content-Type": f"multipart/form-data; boundary={boundary}",
                 "User-Agent": "JARVIS"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.load(r)
        text = (data.get("text") or "").strip()
        segments = data.get("segments") or []
        if segments and sum(s.get("avg_logprob", 0) for s in segments) / len(segments) < -1.0:
            log.info("STT discarded (low confidence): %r", text)  # shor ko shabd samajh liya tha
            return None
    except Exception as e:
        print(f"   (Groq nahi chala, Google se try: {e})")
        return None
    low = text.lower().strip(" .!?")
    if len(low) < 2 or any(junk in low for junk in WHISPER_JUNK):  # chuppi pe Whisper kabhi-kabhi kuch bhi bol deta hai
        return None
    return text


# ======================= Taali detector =======================

class ClapDetector:
    """Do taali pehchano. Taali = achanak (10ms me) poori taakat, chhoti (<50ms), pehle chuppi, aur goonj ke saath khatam.
    Do aisi taaliyan 0.15-1 sec ke gap pe, lagbhag barabar zor ki, aur BEECH ME CHUPPI (bolne me beech me 'aa' jaisi
    aawaz hoti hai). Typing/mouse ke waqt aur laptop pe gaana bajte waqt ignore. (Asli mic recordings se tune kiya.)"""

    CHUNK = 80          # 5 ms (16 kHz pe)
    MIN_LEVEL = 100     # bilkul shaant kamre me bhi itna to chahiye

    def __init__(self):
        from collections import deque

        self.floor = None
        self.history = np.zeros(0, dtype=np.float32)   # pichle ~240ms ke 5ms chunks
        self.recent = deque(maxlen=340)                 # pichle ~1.7 sec: (time, level)
        self.events: list[tuple[float, float]] = []     # (taali ka time, zor)
        self.last_event = 0.0

    def feed(self, frame: np.ndarray, now: float, input_idle: float = 99.0, speaker_busy: bool = False) -> bool:
        x = frame.astype(np.float32)
        chunks = np.sqrt((x[: len(x) // self.CHUNK * self.CHUNK].reshape(-1, self.CHUNK) ** 2).mean(axis=1))
        n = len(chunks)
        for k, c in enumerate(chunks):
            self.recent.append((now - (n - 1 - k) * 0.005, float(c)))
        frame_floor = float(np.median(chunks))
        if self.floor is None:
            self.floor = max(frame_floor, 3.0)
        h = np.concatenate([self.history, chunks])[-48:]
        self.history = h
        found = False
        start, end = len(h) - 32, len(h) - 16  # beech wala frame (aage-peeche dono taraf ka data mile)
        if start >= 4:
            i = start + int(np.argmax(h[start:end]))
            peak = float(h[i])
            t_peak = now - (len(h) - 1 - i) * 0.005
            loud = peak > max(self.MIN_LEVEL, self.floor * 20)
            j0 = next((j for j in range(max(0, i - 12), i + 1) if h[j] > 0.1 * peak), i)
            rise = next((j for j in range(j0, i + 1) if h[j] >= 0.6 * peak), i) - j0
            sharp = rise <= 2                                                          # 10ms me poori taakat (bolna dheere uthta hai)
            short = int((h[max(0, i - 2):i + 12] > peak / 2).sum()) <= 10             # ~50ms se chhoti
            fades = float(h[i + 8:i + 16].mean()) < peak * 0.5 if i + 16 <= len(h) else False  # goonj ke saath khatam
            quiet_before = float(np.median(h[max(0, i - 16):max(1, i - 3)])) < peak * 0.05  # pehle chuppi
            if loud and sharp and short and fades and quiet_before and t_peak - self.last_event > 0.12:
                self.last_event = t_peak
                log.info("CLAP candidate peak=%.0f floor=%.1f idle=%.1fs speaker=%s", peak, self.floor, input_idle, speaker_busy)
                if input_idle >= 0.6 and not speaker_busy:  # typing ya gaana nahi chal raha
                    self.events = [e for e in self.events if t_peak - e[0] < 1.5] + [(t_peak, peak)]
                    if len(self.events) >= 2:
                        (t1, p1), (t2, p2) = self.events[-2:]
                        gap = [lvl for t, lvl in self.recent if t1 + 0.12 <= t <= t2 - 0.02]
                        quiet_gap = not gap or max(gap) < 0.35 * min(p1, p2)
                        if 0.15 <= t2 - t1 <= 1.5 and 1 / 3 <= p1 / p2 <= 3 and quiet_gap:
                            self.events = []
                            found = True
                        elif not quiet_gap:
                            self.events = [(t2, p2)]  # beech me baat ho rahi thi - naye jode se shuru
        if not found and h.max() < self.floor * 8:  # shor ka level dheere-dheere seekho (taali ke waqt nahi)
            self.floor = 0.97 * self.floor + 0.03 * max(frame_floor, 3.0)
        return found


def _speaker_busy() -> bool:
    """Laptop se koi aawaz (gaana/video) aa rahi hai? Tab taali ko ignore karo."""
    try:
        from ctypes import POINTER, cast

        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioMeterInformation

        meter = cast(AudioUtilities.GetSpeakers()._dev.Activate(IAudioMeterInformation._iid_, CLSCTX_ALL, None),
                     POINTER(IAudioMeterInformation))
        return meter.GetPeakValue() > 0.02
    except Exception:
        return False


def _enter_pressed() -> bool:
    try:
        import msvcrt
        return msvcrt.kbhit() and msvcrt.getwch() == "\r"
    except Exception:  # console nahi hai (HUD mode)
        return False


def wait_for_wake_word(threshold: float = 0.4, interrupt=None, allow_enter: bool = True, allow_clap: bool = False) -> str:
    """Jab tak 'Hey Jarvis' na bole / do taali na baje / Enter na dabe / interrupt() True na ho, chupchaap suno (offline).
    Lautata hai: 'wake', 'clap', 'enter' ya 'interrupt'."""
    global _wake_model
    with _wake_lock:
        if _wake_model is None:
            import openwakeword.utils
            from openwakeword.model import Model

            openwakeword.utils.download_models(model_names=["hey_jarvis"])
            _wake_model = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")
    clap = ClapDetector() if allow_clap else None
    idle = None
    if clap:
        from study import idle_seconds as idle

    pa = pyaudio.PyAudio()
    stream = pa.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=1280)
    try:
        last_hint = 0.0
        while True:
            if interrupt and interrupt():
                return "interrupt"
            if allow_enter and _enter_pressed():  # Enter dabaya = bina wake word ke baat
                return "enter"
            frame = np.frombuffer(stream.read(1280, exception_on_overflow=False), dtype=np.int16)
            with _wake_lock:
                score = _wake_model.predict(frame)["hey_jarvis"]
            if score >= threshold:
                with _wake_lock:
                    _wake_model.reset()
                return "wake"
            if clap is not None:
                now = time.time()
                peaky = float(np.abs(frame).max()) > clap.MIN_LEVEL  # mehnga check sirf tez aawaz pe
                own = now - _own_sound["t"] < 1.0  # JARVIS ki apni beep/aawaz
                if clap.feed(frame, now, idle() if peaky else 99.0, (own or _speaker_busy()) if peaky else False):
                    return "clap"
            if score >= 0.1 and time.time() - last_hint > 3:
                print(f"   (kuch suna, par pakka nahi - 'Hey Jarvis' thoda saaf aur zor se bolo) [{score:.2f}]")
                last_hint = time.time()
    finally:
        stream.stop_stream()
        stream.close()
        pa.terminate()


if __name__ == "__main__":
    # Mic Test.bat: python voice.py
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    print("=== TAALI TEST (40 second) ===")
    print("Do baar taali bajao (jaise JARVIS ko bulate ho). Har pakdi gayi taali yahan turant dikhegi.\n")
    det = ClapDetector()
    pa = pyaudio.PyAudio()
    stream = pa.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=1280)
    t0, seen, doubles = time.time(), 0.0, 0
    while time.time() - t0 < 40:
        frame = np.frombuffer(stream.read(1280, exception_on_overflow=False), dtype=np.int16)
        if det.feed(frame, time.time(), 99.0, False):
            doubles += 1
            print("   👏👏 DO TAALI PAKDI GAYI! JARVIS yahi pe jaagega.\n")
        if det.last_event != seen:
            seen = det.last_event
            print(f"   👏 taali suni (zor {int(det.history.max())}, kamre ka shor {det.floor:.0f})")
    stream.close()
    pa.terminate()
    print(f"\nNateeja: {doubles} baar do-taali pakdi. ✓" if doubles else
          "\nDo-taali nahi pakdi. Upar '👏 taali suni' bhi nahi dikha to laptop ke thoda paas, zor se bajao.")

    print("\n=== MIC TEST (bolke dekho) ===")
    calibrate()
    for i in range(2):
        print(f"\nTest {i + 1}/2 - kuch bhi bolo (jaise 'tum kya kar rahe ho')")
        print("Suna:", listen("hi-IN"))
    input("\nEnter dabao band karne ke liye...")
