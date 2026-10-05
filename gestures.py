"""Haath ke ishaare (webcam, MediaPipe) - Iron Man style control. Sab laptop pe hi: koi photo save/bheji nahi jaati.

✌️ Victory      -> JARVIS ko bulao (sunne lagega)
✋ Khula haath   -> gaana/video play-pause
👋 Haath jhatko  -> daayein = agla gaana, baayein = pichhla
👍 / 👎         -> volume +10 / -10 (pakde raho to badhta/ghatta rahega)
✊ Mutthi       -> JARVIS bol raha ho to chup

Battery bachane ke liye: on-demand ('gesture mode on'), aur kaafi der haath na dikhe to apne aap band.
"""

import logging
import threading
import time
import urllib.request
from collections import deque
from pathlib import Path

log = logging.getLogger("jarvis")
MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/"
             "float16/latest/gesture_recognizer.task")
MODEL_PATH = Path(__file__).with_name("models") / "gesture_recognizer.task"

HOLD = {"Victory": 0.5, "Open_Palm": 0.7, "Thumb_Up": 0.5, "Thumb_Down": 0.5, "Closed_Fist": 0.5}
REPEAT = {"Thumb_Up", "Thumb_Down"}   # pakde raho to har 0.8 sec dobara
EVENTS = {"Victory": "wake", "Open_Palm": "play_pause", "Thumb_Up": "volume_up", "Thumb_Down": "volume_down",
          "Closed_Fist": "stop"}

CONTROLLER = None  # hud_app set karta hai


def ensure_model() -> Path:
    if not MODEL_PATH.exists():
        MODEL_PATH.parent.mkdir(exist_ok=True)
        tmp = MODEL_PATH.with_suffix(".part")
        urllib.request.urlretrieve(MODEL_URL, tmp)  # Google ka official model (~8 MB), ek hi baar
        tmp.replace(MODEL_PATH)
    return MODEL_PATH


class GestureController:
    """Webcam se haath dekh ke on_event('wake' | 'play_pause' | 'next' | 'previous' | 'volume_up' | 'volume_down' | 'stop')."""

    def __init__(self, on_event, auto_off_minutes: float = 10, camera: int = 0):
        self.on_event = on_event
        self.auto_off = auto_off_minutes * 60
        self.camera = camera
        self._thread = None
        self._stop = threading.Event()
        self.running = False
        self.error = ""

    def start(self) -> str:
        if self.running or (self._thread is not None and self._thread.is_alive()):
            return "Gesture mode pehle se ON hai (ya chalu ho raha hai)."
        self._stop.clear()
        self.error = ""
        ready = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(ready,), daemon=True)
        self._thread.start()
        ready.wait(20)
        if self.error:
            return f"Gesture mode start nahi hua: {self.error}"
        return "Gesture mode ON: ✌️ bulao · ✋ play/pause · 👋 agla/pichhla · 👍👎 volume · ✊ chup."

    def stop(self) -> str:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(5)  # webcam sach me band ho jaye tab tak ruko
        return "Gesture mode OFF (webcam band)."

    def _run(self, ready: threading.Event):
        import cv2
        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision

        cap = None
        try:
            options = vision.GestureRecognizerOptions(
                base_options=mp_python.BaseOptions(model_asset_path=str(ensure_model())),
                running_mode=vision.RunningMode.VIDEO, num_hands=1,
                min_hand_detection_confidence=0.6, min_hand_presence_confidence=0.6, min_tracking_confidence=0.5)
            recognizer = vision.GestureRecognizer.create_from_options(options)
            for _attempt in range(3):  # pehli baar webcam kabhi-kabhi nahi khulti - 3 try
                cap = cv2.VideoCapture(self.camera, cv2.CAP_DSHOW)
                if cap.isOpened() and cap.read()[0]:
                    break
                cap.release()
                time.sleep(1)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
            if not cap.isOpened():
                raise RuntimeError("webcam nahi khuli (koi aur app use kar raha hai? ya privacy setting me camera band?)")
        except Exception as e:
            self.error = str(e)
            log.exception("gesture start failed")
            if cap is not None:
                cap.release()
            ready.set()
            return
        self.running = True
        ready.set()
        log.info("gesture mode on")
        current, since, last_fire, last_seen = None, 0.0, 0.0, time.time()
        wrist = deque(maxlen=8)  # pichhle ~0.6 sec ki kalai ki position (jhatka pehchanne ke liye)
        start = time.time()
        try:
            while not self._stop.is_set():
                ok, frame = cap.read()
                if not ok:
                    time.sleep(0.1)
                    continue
                frame = cv2.flip(frame, 1)  # selfie jaisa: daayein = daayein
                image = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                result = recognizer.recognize_for_video(image, int((time.time() - start) * 1000))
                now = time.time()
                name = result.gestures[0][0].category_name if result.gestures else None
                score = result.gestures[0][0].score if result.gestures else 0.0
                if result.hand_landmarks:
                    last_seen = now
                    wrist.append((now, result.hand_landmarks[0][0].x))
                    swipe = self._swipe(wrist)
                    if swipe and now - last_fire > 1.2:
                        self._fire(swipe)
                        last_fire, current = now, None
                        wrist.clear()
                        continue
                else:
                    wrist.clear()
                xs = [x for _, x in wrist]
                still = len(xs) < 2 or max(xs) - min(xs) < 0.1  # ishaara tab maano jab haath ruka ho (jhatke ke beech nahi)
                if name in HOLD and score > 0.6:
                    if name != current:
                        current, since = name, now
                    elif still and now - since >= HOLD[name] and now - last_fire > (0.8 if name in REPEAT else 1.5):
                        self._fire(EVENTS[name])
                        last_fire = now
                        if name not in REPEAT:
                            since = now + 10  # ek baar - haath hatao phir dobara
                else:
                    current = None
                if now - last_seen > self.auto_off:
                    log.info("gesture mode auto-off (haath nahi dikha)")
                    break
                time.sleep(0.05)
        finally:
            cap.release()
            recognizer.close()
            self.running = False
            log.info("gesture mode off")

    @staticmethod
    def _swipe(wrist) -> str | None:
        """0.6 sec me kalai screen ke ~35% se zyada daayein/baayein gayi = jhatka."""
        if len(wrist) < 4:
            return None
        (t0, x0), (t1, x1) = wrist[0], wrist[-1]
        if t1 - t0 > 0.7:
            return None
        if x1 - x0 > 0.35:
            return "next"
        if x0 - x1 > 0.35:
            return "previous"
        return None

    def _fire(self, event: str):
        log.info("GESTURE %s", event)
        try:
            self.on_event(event)
        except Exception:
            log.exception("gesture event failed")


def gesture_mode(on: bool) -> str:
    """Haath ke ishaaron se control (webcam): ✌️ JARVIS bulao, ✋ play/pause, 👋 agla/pichhla gaana, 👍👎 volume, ✊ chup.

    Args:
        on: true = chalu (webcam on), false = band.
    """
    if CONTROLLER is None:
        return "Gesture mode sirf JARVIS.bat / JARVIS_eng.bat (HUD) me chalta hai."
    return CONTROLLER.start() if on else CONTROLLER.stop()


TOOLS = [gesture_mode]
