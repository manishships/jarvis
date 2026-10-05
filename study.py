"""Padhai ke tools: study session (Pomodoro), flashcards (FSRS - Anki wala smart schedule), lecture -> notes,
screen-time hisaab aur study mode.

Research: khud yaad karke jawab dena (active recall) + sahi waqt pe dohrana (spaced repetition) padhai ka sabse
asardaar tareeka hai - isliye JARVIS quiz leta hai, seedha jawab nahi deta.
"""

import ctypes
import json
import re
import threading
import time
import webbrowser
from datetime import datetime, timedelta, timezone

import psutil
from fsrs import Card, Rating, Scheduler

import lang
import memory

_TS = "%Y-%m-%d %H:%M:%S"
_scheduler = Scheduler()
_grade_lock = threading.Lock()

# jarvis.py har baat pe bharta hai - taaki JARVIS bina pooche session shuru na kare
INTENT = {"user": "", "jarvis": ""}
START_WORDS = re.compile(r"shuru|start|timer|session|pomodoro|study mode|protocol|laga ?do|lagao|chalu|chalao|"
                         r"शुरू|स्टार्ट|टाइमर|सेशन|चालू|लगा|प्रोटोकॉल", re.I)
YES_WORDS = re.compile(r"\b(haan|han|ha|yes|ok|okay|theek|thik|chalo|karo|kar do|ready|bilkul)\b|हाँ|हां|ठीक|रेडी|करो", re.I)


def _asked_to_start() -> bool:
    """User ne session/timer shuru karne ko saaf bola? (ya JARVIS ke poochhne pe haan/minute bataya)"""
    user, jarvis = INTENT["user"], INTENT["jarvis"]
    if START_WORDS.search(user) or re.search(r"\d+\s*(min|मिनट|ghant|घंट|hour)", user, re.I):
        return True
    asked = re.search(r"session|timer|pomodoro|shuru|start", jarvis, re.I)
    return bool(asked and (YES_WORDS.search(user) or re.search(r"\d", user)))


BLOCKED = ("RUKO: user ne session/timer shuru karne ko saaf nahi bola. Pehle ek line me poochho "
           "(jaise '{subject} ka kitne minute ka session shuru karun?') - haan bole tabhi tool chalana.")


# ======================= Study session =======================

def _start_session(subject: str, minutes: int) -> str:
    _stop_session()
    start = datetime.now()
    due = start + timedelta(minutes=minutes)
    with memory._db() as db:
        rid = db.execute("INSERT INTO reminders (created, due, text, repeat) VALUES (?, ?, ?, '')",
                         (memory.now(), due.strftime(_TS),
                          lang.t("session_done", subject=subject, minutes=minutes))).lastrowid
        db.execute("INSERT INTO study (subject, start, planned, reminder_id) VALUES (?, ?, ?, ?)",
                   (subject.strip(), start.strftime(_TS), minutes, rid))
    return f"{subject} ka {minutes} min session shuru ({start:%H:%M} se {due:%H:%M} tak)."


def _stop_session() -> str | None:
    with memory._db() as db:
        row = db.execute("SELECT id, subject, start, planned, reminder_id FROM study WHERE ended IS NULL "
                         "ORDER BY id DESC LIMIT 1").fetchone()
        if not row:
            return None
        sid, subject, start, planned, rid = row
        begin = datetime.strptime(start, _TS)
        end = min(datetime.now(), begin + timedelta(minutes=planned))
        db.execute("UPDATE study SET ended = ? WHERE id = ?", (end.strftime(_TS), sid))
        if rid:  # iska "session poora" wala reminder ab nahi bajna chahiye
            db.execute("UPDATE reminders SET done = 1 WHERE id = ? AND done = 0", (rid,))
    return f"{subject} session band: {int((end - begin).total_seconds() // 60)} minute padhai hui."


def start_study(subject: str, minutes: int) -> str:
    """Padhai ka focus session (Pomodoro) shuru karo - SIRF tab jab user saaf bole (jaise '45 minute physics padhna hai',
    'timer lagao', 'session shuru karo'). Time poora hone pe JARVIS break batayega aur hisaab rakhega.

    Args:
        subject: Kya padh rahe ho, jaise 'Physics' ya 'Maths - Integration'.
        minutes: Kitne minute (jaise 25, 45, 60).
    """
    if not _asked_to_start():
        return BLOCKED.format(subject=subject)
    return _start_session(subject, max(5, min(int(minutes), 240)))


def stop_study() -> str:
    """Chal raha padhai session abhi rok do (jitna padha utna count hoga)."""
    return _stop_session() or "Koi session chal nahi raha."


def session_status() -> tuple[str, int] | None:
    """Abhi chal raha session: (subject, kitne minute bache) - warna None."""
    with memory._db() as db:
        row = db.execute("SELECT subject, start, planned FROM study WHERE ended IS NULL ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        return None
    subject, start, planned = row
    left = planned - (datetime.now() - datetime.strptime(start, _TS)).total_seconds() / 60
    return (subject, int(left) + 1) if left > 0 else None


def study_session_active() -> str | None:
    status = session_status()
    return status[0] if status else None


def _studied_minutes(start: str, planned: int, ended: str | None) -> int:
    begin = datetime.strptime(start, _TS)
    end = datetime.strptime(ended, _TS) if ended else min(datetime.now(), begin + timedelta(minutes=planned))
    return max(0, int((end - begin).total_seconds() // 60))


def study_report(days: int) -> str:
    """Padhai ka hisaab: pichhle kuch dino me subject-wise kitne minute padha, aur roz ki streak.

    Args:
        days: Kitne din ka hisaab (1 = aaj, 7 = hafta).
    """
    since = (datetime.now() - timedelta(days=max(1, days) - 1)).strftime("%Y-%m-%d 00:00:00")
    with memory._db() as db:
        rows = db.execute("SELECT subject, start, planned, ended FROM study").fetchall()
    per_subject, per_day = {}, {}
    for subject, start, planned, ended in rows:
        mins = _studied_minutes(start, planned, ended)
        per_day[start[:10]] = per_day.get(start[:10], 0) + mins
        if start >= since:
            per_subject[subject] = per_subject.get(subject, 0) + mins
    streak, day = 0, datetime.now().date()
    while per_day.get(day.isoformat(), 0) > 0:
        streak, day = streak + 1, day - timedelta(days=1)
    if not per_subject:
        return f"Pichhle {days} din me koi study session record nahi hua. Streak: {streak} din."
    return json.dumps({"days": days, "total_minutes": sum(per_subject.values()), "per_subject_minutes": per_subject,
                       "streak_days": streak}, ensure_ascii=False)


def study_mode(subject: str, minutes: int, open_pw: bool) -> str:
    """'Study mode' - ek baar me: padhai ka timer, PW kholna, brightness theek, distraction watch.
    SIRF tab jab user ne study mode / session maanga ho.

    Args:
        subject: Kya padhna hai, jaise 'Physics backlog'.
        minutes: Session kitne minute ka (user na bataye to poochh lo).
        open_pw: Physics Wallah website kholni hai ya nahi.
    """
    import pc_control

    if not _asked_to_start():
        return BLOCKED.format(subject=subject)
    done = [_start_session(subject, max(5, min(int(minutes), 240)))]
    if open_pw:
        webbrowser.open("https://www.pw.live/study")
        done.append("PW khol diya")
    try:
        pc_control.set_brightness(70)
        done.append("brightness 70%")
    except Exception:
        pass
    done.append("distraction watch on (Insta/Shorts khule to yaad dilaunga)")
    return "Study mode ON: " + "; ".join(done)


# ======================= Flashcards (FSRS) =======================

def add_flashcards(subject: str, cards: str) -> str:
    """Flashcards save karo (chapter, lecture notes, photo ya user ki baat se banakar). Har line me ek card: 'sawaal | jawab'.
    Sawaal chhote aur board-exam style, jawab 1-2 line ka.

    Args:
        subject: Subject aur chapter, jaise 'Physics - Electrostatics'.
        cards: Har line 'sawaal | jawab', e.g. 'Coulomb ka niyam kya hai? | F = kq1q2/r^2'.
    """
    rows = []
    for line in cards.splitlines():
        if "|" in line:
            q, _, a = line.partition("|")
            q = re.sub(r"^\s*(\d+[.)]|[-•*])\s*", "", q).strip()
            if q and a.strip():
                rows.append((subject.strip(), q, a.strip(), json.dumps(Card().to_dict()), memory.now()))
    if not rows:
        return "Koi card nahi bana - har line 'sawaal | jawab' format me chahiye."
    with memory._db() as db:
        db.executemany("INSERT INTO cards (subject, question, answer, fsrs, created) VALUES (?, ?, ?, ?, ?)", rows)
    return f"{len(rows)} flashcards '{subject}' me save ho gaye."


def _due_cards(subject: str = ""):
    current = datetime.now(timezone.utc)
    with memory._db() as db:
        rows = db.execute("SELECT id, subject, question, answer, fsrs FROM cards WHERE subject LIKE ?", (f"%{subject}%",)).fetchall()
    due = []
    for cid, subj, q, a, raw in rows:
        card = Card.from_dict(json.loads(raw))
        if card.due <= current:
            due.append((card.due, cid, subj, q, a))
    return [d[1:] for d in sorted(due)]


def due_count() -> int:
    return len(_due_cards())


def quiz_next(subject: str) -> str:
    """Quiz ka agla card lo (jo dohraane ka time aa gaya hai). User ko SIRF sawaal poochho, jawab mat batao.
    User jawab de to khud check karo, sahi jawab batao, aur quiz_grade se result save karo.

    Args:
        subject: Kis subject ka quiz (khaali = sab subjects).
    """
    due = _due_cards(subject)
    if not due:
        return "Abhi koi card due nahi hai - sab up to date! (Naye cards add_flashcards se bana sakte ho.)"
    cid, subj, q, a = due[0]
    return json.dumps({"card_id": cid, "subject": subj, "question": q, "correct_answer_for_checking_only": a,
                       "cards_due_total": len(due)}, ensure_ascii=False)


def quiz_grade(card_id: int, result: str) -> str:
    """Quiz card ka result save karo - isi se agla review kab hoga ye decide hota hai.

    Args:
        card_id: quiz_next se mila card_id.
        result: 'again' (galat/bhool gaya), 'hard' (mushkil se sahi), 'good' (sahi), 'easy' (turant sahi).
    """
    rating = {"again": Rating.Again, "hard": Rating.Hard, "good": Rating.Good, "easy": Rating.Easy}.get(result.lower().strip())
    if rating is None:
        return "result 'again', 'hard', 'good' ya 'easy' hona chahiye."
    with _grade_lock, memory._db() as db:
        row = db.execute("SELECT fsrs, subject, question, answer FROM cards WHERE id = ?", (card_id,)).fetchone()
        if not row:
            return "Ye card nahi mila."
        card, _ = _scheduler.review_card(Card.from_dict(json.loads(row[0])), rating)
        db.execute("UPDATE cards SET fsrs = ? WHERE id = ?", (json.dumps(card.to_dict()), card_id))
    if rating == Rating.Again:  # galat jawab -> galtiyon ki diary me bhi
        import planner
        planner.record_quiz_miss(row[1], row[2], row[3])
    gap = card.due - datetime.now(timezone.utc)
    when = f"{int(gap.total_seconds() // 60)} minute" if gap.days < 1 else f"{gap.days} din"
    return f"Saved. Ye card {when} baad dobara aayega. Abhi {due_count()} cards due hain."


def flashcard_stats() -> str:
    """Flashcards ka hisaab: kitne cards, kitne abhi due, subject-wise."""
    with memory._db() as db:
        rows = db.execute("SELECT subject, COUNT(*) FROM cards GROUP BY subject").fetchall()
    if not rows:
        return "Abhi koi flashcard nahi hai."
    due = {}
    for _, subj, _, _ in _due_cards():
        due[subj] = due.get(subj, 0) + 1
    return json.dumps({subj: {"total": n, "due_now": due.get(subj, 0)} for subj, n in rows}, ensure_ascii=False)


# ======================= Lecture -> notes =======================

def youtube_lecture(url: str) -> str:
    """YouTube lecture (jaise Physics Wallah ka YouTube video) ka transcript lao, taaki usse short notes (write_document),
    flashcards (add_flashcards) aur 5 board-style sawaal bana sako. (pw.live ke links login maangte hain - unke liye
    chapter ka naam poochh ke apne gyaan se notes banao.)

    Args:
        url: YouTube video ka link.
    """
    from youtube_transcript_api import YouTubeTranscriptApi

    match = re.search(r"(?:v=|youtu\.be/|shorts/|live/|embed/)([\w-]{11})", url)
    if not match:
        return "Ye YouTube link nahi lag raha. (PW app/website ke links ke liye chapter ka naam batao.)"
    try:
        transcript = YouTubeTranscriptApi().fetch(match.group(1), languages=["hi", "en", "en-IN"])
    except Exception as e:
        return f"Is video ka transcript nahi mila ({type(e).__name__}). Shayad captions band hain."
    text = " ".join(s.text for s in transcript)
    note = "" if len(text) <= 25000 else " (lamba lecture - pehla hissa)"
    return (f"Transcript{note}:\n{text[:25000]}\n\n[JARVIS ke liye: isse saaf Hinglish notes banao (write_document), "
            f"8-12 flashcards (add_flashcards) aur 5 board-style sawaal. User ko chhota summary batao.]")


# ======================= Screen time (khud ka tracker) =======================

LABELS = [  # window title me ye mile to ye naam (pehla match)
    ("Physics Wallah", r"physics ?wallah|pw\.live|\bPW\b"), ("Instagram", r"instagram"), ("YouTube Shorts", r"shorts"),
    ("YouTube Music", r"youtube music"), ("YouTube", r"youtube"), ("WhatsApp", r"whatsapp"), ("ChatGPT", r"chatgpt"),
    ("Claude", r"\bclaude\b"), ("Netflix", r"netflix"), ("Hotstar", r"hotstar"), ("Reddit", r"reddit"),
    ("Discord", r"discord"), ("Roblox", r"roblox"), ("Google Search", r"- google search"), ("JARVIS", r"j\.a\.r\.v\.i\.s"),
]
DISTRACTING = {"Instagram", "YouTube Shorts", "Netflix", "Hotstar", "Reddit", "Discord", "Roblox"}
APP_NAMES = {"msedge": "Edge (browsing)", "chrome": "Chrome (browsing)", "brave": "Brave (browsing)", "code": "VS Code",
             "explorer": "File Explorer", "winword": "Word", "pythonw": "JARVIS", "claude": "Claude"}


def active_window() -> tuple[str, str]:
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    pid = ctypes.c_ulong()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    try:
        proc = psutil.Process(pid.value).name().removesuffix(".exe")
    except psutil.Error:
        proc = "?"
    return buf.value, proc


def label_for(title: str, proc: str) -> str:
    for label, pattern in LABELS:
        if re.search(pattern, title, re.I):
            return label
    return APP_NAMES.get(proc.lower(), proc)


def idle_seconds() -> float:
    """Kitne second se keyboard/mouse nahi chhua."""
    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
    info = LASTINPUTINFO(ctypes.sizeof(LASTINPUTINFO), 0)
    ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info))
    return (ctypes.windll.kernel32.GetTickCount() - info.dwTime) / 1000


def activity_tracker(warn, interval: int = 20) -> None:
    """Background: har 20 sec active app note karo. Padhai session ke beech distraction ho to (10 min me ek baar) halka sa yaad dilao."""
    last_warn, distracted_for = 0.0, 0
    while True:
        time.sleep(interval)
        try:
            title, proc = active_window()
            if not title or idle_seconds() > 300:  # 5 min se laptop nahi chhua - count mat karo
                continue
            label = label_for(title, proc)
            with memory._db() as db:
                db.execute("INSERT INTO usage (day, label, seconds) VALUES (?, ?, ?) "
                           "ON CONFLICT(day, label) DO UPDATE SET seconds = seconds + ?",
                           (datetime.now().strftime("%Y-%m-%d"), label, interval, interval))
            subject = study_session_active()
            if subject and label in DISTRACTING:
                distracted_for += interval
                if distracted_for >= 60 and time.time() - last_warn > 600:
                    warn(lang.t("distraction", subject=subject, label=label))
                    last_warn = time.time()
            else:
                distracted_for = 0
        except Exception:
            pass


def screen_time_report(days: int) -> str:
    """Laptop pe kis app/website pe kitna time gaya (JARVIS khud track karta hai). Sirf sach batao, lecture nahi.

    Args:
        days: 1 = aaj, 7 = pichhla hafta.
    """
    since = (datetime.now() - timedelta(days=max(1, days) - 1)).strftime("%Y-%m-%d")
    with memory._db() as db:
        rows = db.execute("SELECT label, SUM(seconds) FROM usage WHERE day >= ? GROUP BY label ORDER BY 2 DESC", (since,)).fetchall()
    if not rows:
        return "Abhi screen time ka data nahi hai (JARVIS chalu rehne pe track hota hai)."

    def fmt(s):
        return f"{s // 3600}h {s % 3600 // 60}m" if s >= 3600 else f"{s // 60}m"
    distracting = sum(s for label, s in rows if label in DISTRACTING)
    return json.dumps({"days": days, "top_apps": {label: fmt(s) for label, s in rows[:12]},
                       "distracting_total": fmt(distracting), "total": fmt(sum(s for _, s in rows))}, ensure_ascii=False)


TOOLS = [start_study, stop_study, study_report, study_mode,
         add_flashcards, quiz_next, quiz_grade, flashcard_stats, youtube_lecture, screen_time_report]
