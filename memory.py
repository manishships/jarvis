"""JARVIS ki yaaddasht (SQLite): baatein, yaadein (facts), reminders/timers, contacts, settings, protocols
+ kuch chhote tools (web search, news, websites).

Database ek hi file hai: jarvis_memory.db - isko delete mat karna, backup rakhna.
"""

import json
import sqlite3
import threading
import webbrowser
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote_plus

DB_PATH = Path(__file__).with_name("jarvis_memory.db")
_TS = "%Y-%m-%d %H:%M:%S"
_schema_ready: set[str] = set()
_schema_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY, ts TEXT, role TEXT, content TEXT);
CREATE TABLE IF NOT EXISTS facts (id INTEGER PRIMARY KEY, ts TEXT, fact TEXT);
CREATE TABLE IF NOT EXISTS reminders (id INTEGER PRIMARY KEY, created TEXT, due TEXT, text TEXT, done INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS contacts (name TEXT PRIMARY KEY, phone TEXT);
CREATE TABLE IF NOT EXISTS study (id INTEGER PRIMARY KEY, subject TEXT, start TEXT, planned INTEGER, ended TEXT);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS protocols (name TEXT PRIMARY KEY, steps TEXT);
CREATE TABLE IF NOT EXISTS cards (id INTEGER PRIMARY KEY, subject TEXT, question TEXT, answer TEXT, fsrs TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS usage (day TEXT, label TEXT, seconds INTEGER, PRIMARY KEY (day, label));
"""
MIGRATIONS = [  # purane database me naye columns (pehle se hon to chupchaap skip)
    "ALTER TABLE reminders ADD COLUMN repeat TEXT DEFAULT ''",
    "ALTER TABLE study ADD COLUMN reminder_id INTEGER",
]
DEFAULT_PROTOCOLS = {
    "study": "study_mode chalu karo (subject aur minute na pata ho to poochh lo), volume 30, silent mode on, aur 'All the best, Boss' bolo.",
    "night": "brightness 30, volume 20, kal ke pending reminders (list_reminders) bata do, silent mode on, aur 'Good night, sir' bolo.",
    "party": "volume 80, play_music se party songs chalao.",
    "wake up": "Good morning bolo, get_weather('') se mausam, aaj ke reminders aur news_headlines('') ki 3 khabrein chhote me.",
}


@contextmanager
def _db():
    """Database connection (har kaam ke baad save + band). Kai threads ek saath use kar sakte hain."""
    con = sqlite3.connect(DB_PATH, timeout=15)
    try:
        key = str(DB_PATH)
        if key not in _schema_ready:
            with _schema_lock:
                con.execute("PRAGMA journal_mode=WAL")  # ek saath padhna-likhna (database locked nahi hoga)
                con.executescript(SCHEMA)
                for sql in MIGRATIONS:
                    try:
                        con.execute(sql)
                    except sqlite3.OperationalError:
                        pass
                if not con.execute("SELECT COUNT(*) FROM protocols").fetchone()[0]:
                    con.executemany("INSERT INTO protocols VALUES (?, ?)", DEFAULT_PROTOCOLS.items())
                con.commit()
                _schema_ready.add(key)
        yield con
        con.commit()
    finally:
        con.close()


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def now_s() -> str:
    return datetime.now().strftime(_TS)


# ======================= Settings =======================

def get_setting(key: str) -> str | None:
    with _db() as db:
        row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def set_setting(key: str, value: str) -> None:
    with _db() as db:
        db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))


# ======================= Baatein =======================

def log_message(role: str, content: str) -> None:
    with _db() as db:
        db.execute("INSERT INTO messages (ts, role, content) VALUES (?, ?, ?)", (now(), role, content))


def recent_messages(limit: int) -> list[tuple[str, str]]:
    with _db() as db:
        return db.execute("SELECT role, content FROM messages ORDER BY id DESC LIMIT ?", (limit,)).fetchall()[::-1]


def session_context() -> str:
    """Session shuru hote waqt ek baar: user ke facts + pichli baatein + aane wale reminders."""
    with _db() as db:
        facts = [f for (f,) in db.execute("SELECT fact FROM facts ORDER BY id")]
        recent = db.execute("SELECT ts, role, content FROM messages ORDER BY id DESC LIMIT 12").fetchall()[::-1]
        upcoming = db.execute("SELECT due, text, repeat FROM reminders WHERE done = 0 ORDER BY due LIMIT 10").fetchall()
        first = db.execute("SELECT ts FROM messages ORDER BY id LIMIT 1").fetchone()

    parts = [f"Session shuru: {now()}"]
    if first:
        parts.append(f"Hum {first[0]} se baat kar rahe hain.")
    parts.append("Jo tumhe user ke baare me pata hai:\n" + ("\n".join(f"- {f}" for f in facts) or "- abhi kuch nahi (naya user hai, dheere-dheere jaano)"))
    if recent:
        parts.append("Pichli baatein (last session):\n" + "\n".join(f"[{ts}] {r}: {c[:300]}" for ts, r, c in recent))
    if upcoming:
        parts.append("Aane wale reminders:\n" + "\n".join(f"- {d[:16]}: {t}{f' ({REPEAT_LABEL[r]})' if r in REPEAT_LABEL else ''}" for d, t, r in upcoming))
    return "\n\n".join(parts)


def search_memory(query: str, oldest_first: bool, limit: int) -> str:
    """Purani conversations me dhoondo. 'Pehla sawaal kya tha' jaisa poochhe to query khaali do aur oldest_first true.

    Args:
        query: Keyword jo dhoondhna hai; khaali string = sab messages.
        oldest_first: true = sabse purane pehle, false = sabse naye pehle.
        limit: Kitne results chahiye (1-50).
    """
    order = "ASC" if oldest_first else "DESC"
    with _db() as db:
        rows = db.execute(
            f"SELECT ts, role, content FROM messages WHERE content LIKE ? ORDER BY id {order} LIMIT ?",
            (f"%{query}%", max(1, min(limit, 50))),
        ).fetchall()
    return json.dumps(rows, ensure_ascii=False) if rows else "Kuch nahi mila."


# ======================= Yaadein (facts) =======================

def remember(fact: str) -> str:
    """User ke baare me lambe samay ki important baat save karo (interest, goal, exam date, pasand-napasand, life update).
    Har chhoti plan detail save mat karo.

    Args:
        fact: Ek line ka fact, e.g. 'Board exams March 2027 me hain'.
    """
    with _db() as db:
        db.execute("INSERT INTO facts (ts, fact) VALUES (?, ?)", (now(), fact.strip()))
    return "Saved."


def list_facts() -> str:
    """JARVIS ko user ke baare me jo-jo yaad hai, sab dikhao (user poochhe 'tumhe mere baare me kya pata hai')."""
    with _db() as db:
        rows = db.execute("SELECT id, fact FROM facts ORDER BY id").fetchall()
    return "\n".join(f"#{i}: {f}" for i, f in rows) if rows else "Abhi kuch yaad nahi hai."


def forget_fact(keyword: str) -> str:
    """User bole 'ye bhool jao' to woh yaad mita do (sirf JARVIS ki memory se).

    Args:
        keyword: Yaad ka koi shabd ya '#id' (list_facts se), e.g. 'gym' ya '#3'.
    """
    with _db() as db:
        if keyword.strip().startswith("#") and keyword.strip()[1:].isdigit():
            rows = db.execute("SELECT id, fact FROM facts WHERE id = ?", (int(keyword.strip()[1:]),)).fetchall()
        else:
            rows = db.execute("SELECT id, fact FROM facts WHERE fact LIKE ?", (f"%{keyword.strip()}%",)).fetchall()
        if not rows:
            return f"'{keyword}' se juda kuch yaad nahi mila."
        if len(rows) > 3:
            return "Bahut saari yaadein match ho rahi hain - thoda pakka batao: " + "; ".join(f"#{i} {f}" for i, f in rows[:8])
        db.executemany("DELETE FROM facts WHERE id = ?", [(i,) for i, _ in rows])
    return "Bhool gaya: " + "; ".join(f for _, f in rows)


# ======================= Reminders & timers =======================

REPEATS = {"daily": timedelta(days=1), "weekly": timedelta(days=7)}
REPEAT_LABEL = {"daily": "roz", "weekly": "har hafte"}


def set_reminder(text: str, due: str, repeat: str) -> str:
    """Reminder set karo. Time aane pe JARVIS bol ke (aur phone pe) yaad dilayega.

    Args:
        text: Kis baat ka reminder.
        due: Kab, format 'YYYY-MM-DD HH:MM' (24 ghante wala), current time ke hisaab se calculate karo.
        repeat: '' = ek baar, 'daily' = roz isi time, 'weekly' = har hafte.
    """
    try:
        when = datetime.strptime(due.strip(), "%Y-%m-%d %H:%M")
    except ValueError:
        return "Error: due ka format 'YYYY-MM-DD HH:MM' hona chahiye."
    repeat = repeat.strip().lower()
    if repeat and repeat not in REPEATS:
        return "Error: repeat '', 'daily' ya 'weekly' hona chahiye."
    if when < datetime.now() - timedelta(minutes=1) and not repeat:
        return f"Error: {due} to beet chuka hai. Aage ka time do."
    with _db() as db:
        rid = db.execute("INSERT INTO reminders (created, due, text, repeat) VALUES (?, ?, ?, ?)",
                         (now(), when.strftime(_TS), text.strip(), repeat)).lastrowid
    return f"Reminder #{rid} set: {when:%d %b %H:%M}{' (har roz)' if repeat == 'daily' else ' (har hafte)' if repeat == 'weekly' else ''}."


def set_timer(minutes: float, label: str) -> str:
    """Timer lagao (second tak sahi) - 'paanch minute ka timer', 'maggi ka 2 minute timer'.

    Args:
        minutes: Kitne minute (0.5 = 30 second).
        label: Timer kis cheez ka hai.
    """
    if not 0 < minutes <= 24 * 60:
        return "Timer 1 second se 24 ghante ke beech ka hona chahiye."
    due = datetime.now() + timedelta(minutes=minutes)
    with _db() as db:
        rid = db.execute("INSERT INTO reminders (created, due, text, repeat) VALUES (?, ?, ?, '')",
                         (now(), due.strftime(_TS), f"⏱ Timer khatam: {label.strip() or 'timer'}")).lastrowid
    return f"Timer #{rid}: {minutes:g} minute ({due:%H:%M:%S} pe bajega)."


def list_reminders() -> str:
    """Saare pending (aane wale) reminders aur timers dikhao."""
    with _db() as db:
        rows = db.execute("SELECT id, due, text, repeat FROM reminders WHERE done = 0 ORDER BY due").fetchall()
    if not rows:
        return "Koi pending reminder nahi."
    return "\n".join(f"#{i} {d[:16]} - {t}{f' ({REPEAT_LABEL[r]})' if r in REPEAT_LABEL else ''}" for i, d, t, r in rows)


def cancel_reminder(match: str) -> str:
    """Reminder/timer cancel karo.

    Args:
        match: '#id' (list_reminders se) ya reminder ka koi shabd, e.g. 'revision'.
    """
    with _db() as db:
        if match.strip().startswith("#") and match.strip()[1:].isdigit():
            rows = db.execute("SELECT id, text FROM reminders WHERE done = 0 AND id = ?", (int(match.strip()[1:]),)).fetchall()
        else:
            rows = db.execute("SELECT id, text FROM reminders WHERE done = 0 AND text LIKE ?", (f"%{match.strip()}%",)).fetchall()
        if not rows:
            return f"'{match}' wala koi pending reminder nahi mila."
        if len(rows) > 3:
            return "Kai reminders match hue - '#id' se batao: " + "; ".join(f"#{i} {t}" for i, t in rows[:8])
        db.executemany("UPDATE reminders SET done = 1 WHERE id = ?", [(i,) for i, _ in rows])
    return "Cancel kar diya: " + "; ".join(t for _, t in rows)


def pop_due_reminders() -> list[tuple[str, str]]:
    """Jinka time ho gaya unhe lautao. Ek-baar wale 'done', roz/hafte wale agli baar ke liye aage badh jaate hain."""
    current = datetime.now()
    out = []
    with _db() as db:
        rows = db.execute("SELECT id, due, text, repeat FROM reminders WHERE done = 0 AND due <= ?", (now_s(),)).fetchall()
        for rid, due, text, repeat in rows:
            out.append((due[:16], text))
            if repeat in REPEATS:
                nxt = datetime.strptime(due[:16], "%Y-%m-%d %H:%M")
                while nxt <= current:
                    nxt += REPEATS[repeat]
                db.execute("UPDATE reminders SET due = ? WHERE id = ?", (nxt.strftime(_TS), rid))
            else:
                db.execute("UPDATE reminders SET done = 1 WHERE id = ?", (rid,))
    return out


# ======================= Contacts =======================

def normalize_phone(phone: str) -> str | None:
    """'98765 43210' / '+91-98765-43210' / '098765...' -> '919876543210' (WhatsApp format)."""
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) == 10:
        digits = "91" + digits
    return digits if 11 <= len(digits) <= 15 else None


def save_contact(name: str, phone: str) -> str:
    """Kisi ka WhatsApp number save karo (jo WhatsApp me naam se nahi milte, jaise 'Mummy').

    Args:
        name: Contact ka naam, jaise user bulata hai.
        phone: Mobile number (country code na ho to India +91 maan lenge).
    """
    number = normalize_phone(phone)
    if not number:
        return "Number sahi nahi lag raha. 10 digit ka mobile number chahiye."
    with _db() as db:
        db.execute("INSERT OR REPLACE INTO contacts (name, phone) VALUES (?, ?)", (name.strip().lower(), number))
    return f"{name} ka number save ho gaya: +{number}"


def find_contact(name: str) -> str | None:
    """Naam se number (thoda alag spelling bhi chalega)."""
    from difflib import get_close_matches

    with _db() as db:
        contacts = dict(db.execute("SELECT name, phone FROM contacts").fetchall())
    key = name.strip().lower()
    if key in contacts:
        return contacts[key]
    close = get_close_matches(key, list(contacts), n=1, cutoff=0.75)
    return contacts[close[0]] if close else None


def list_contacts() -> str:
    """Saare saved contacts (naam aur number) dikhao."""
    with _db() as db:
        rows = db.execute("SELECT name, phone FROM contacts ORDER BY name").fetchall()
    return json.dumps(rows, ensure_ascii=False) if rows else "Abhi koi contact save nahi hai."


# ======================= Internet =======================

def open_website(url: str) -> str:
    """User ke apne browser (Edge/Chrome) me koi website kholo.

    Args:
        url: Poora URL, e.g. 'https://www.google.com'.
    """
    if not url.startswith(("http://", "https://", "file:")):
        url = "https://" + url
    webbrowser.open(url)
    return f"Opened {url}"


def play_on_youtube(query: str) -> str:
    """YouTube pe video/lecture/bhajan dhoondh ke user ke browser me kholo (gaane ke liye play_music behtar hai).

    Args:
        query: Kya dhoondhna hai, e.g. 'class 12 physics alternating current one shot'.
    """
    webbrowser.open("https://www.youtube.com/results?search_query=" + quote_plus(query))
    return f"YouTube pe '{query}' khol diya."


def web_search(query: str) -> str:
    """Internet pe search karo - facts, dates, tyohar, exam info confirm karne ke liye. Pakka na pata ho to pehle ye use karo.

    Args:
        query: Kya dhoondhna hai, e.g. 'Hanuman Jayanti 2027 date'.
    """
    from ddgs import DDGS

    try:
        results = DDGS(timeout=8).text(query, max_results=5)
    except Exception:
        results = []
    if results:
        return json.dumps([{"title": r.get("title"), "snippet": (r.get("body") or "")[:300], "url": r.get("href")}
                           for r in results], ensure_ascii=False)
    news = news_headlines(query)  # DuckDuckGo kabhi-kabhi rok deta hai - tab Google News se
    if news.startswith("- "):
        return "Web search abhi nahi chala; Google News pe ye mila:\n" + news
    return "Search abhi nahi ho paya (internet ya search service busy). Pakka nahi pata - user ko honestly batao."


def news_headlines(topic: str) -> str:
    """Taaza khabrein (Google News, India). Topic khaali = aaj ki top headlines.

    Args:
        topic: Kis baare me, e.g. 'CBSE board exam', 'cricket', ya khaali string.
    """
    import urllib.request
    import xml.etree.ElementTree as ET

    url = ("https://news.google.com/rss/search?q=" + quote_plus(topic) if topic.strip()
           else "https://news.google.com/rss?") + "&hl=en-IN&gl=IN&ceid=IN:en"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        root = ET.fromstring(urllib.request.urlopen(req, timeout=15).read())
    except Exception as e:
        return f"News nahi mil payi: {e}"
    items = [(it.findtext("title") or "", (it.findtext("pubDate") or "")[:16]) for it in root.findall(".//item")[:7]]
    return "\n".join(f"- {t} ({d})" for t, d in items) if items else "Koi khabar nahi mili."


# ======================= Settings tools =======================

def set_silent_mode(on: bool) -> str:
    """Silent mode: JARVIS khud se (reminder, alerts, yaad-dihani) bolega nahi - sirf screen/phone pe likhega.
    User ke sawaalon ka jawab bolta rahega.

    Args:
        on: true = silent mode chalu, false = band.
    """
    set_setting("silent", "1" if on else "0")
    return "Silent mode ON - ab khud se nahi bolunga, sirf likhunga." if on else "Silent mode OFF."


def set_voice(style: str) -> str:
    """JARVIS ki aawaz badlo.

    Args:
        style: 'indian' (default), 'british' (movie wala JARVIS), 'hindi', ya 'female'.
    """
    import config
    import lang

    style = style.strip().lower()
    if style not in config.VOICES:
        return f"Ye aawaz nahi hai. Options: {', '.join(config.VOICES)}"
    set_setting("voice_en" if lang.is_english() else "voice", config.VOICES[style])
    return f"Aawaz badal di: {style}. Agla jawab nayi aawaz me (bhasha wahi rahegi)."


def current_voice() -> str:
    import config
    import lang

    if lang.is_english():
        return get_setting("voice_en") or config.ENGLISH_VOICE
    return get_setting("voice") or config.VOICE


# ======================= Protocols (Iron Man style routines) =======================

def save_protocol(name: str, steps: str) -> str:
    """Naya protocol (routine) save karo - baad me 'X protocol' bolne pe ye saare kaam ek saath honge.

    Args:
        name: Protocol ka naam, jaise 'night' ya 'gaming'.
        steps: Kya-kya karna hai, saaf shabdon me (jaise 'brightness 30, volume 20, lofi gaane chalao').
    """
    with _db() as db:
        db.execute("INSERT OR REPLACE INTO protocols VALUES (?, ?)", (name.strip().lower(), steps.strip()))
    return f"'{name}' protocol save ho gaya."


def run_protocol(name: str) -> str:
    """Protocol chalao: ye uske steps lautata hai - phir JARVIS un steps ko tools se ek-ek karke poora kare.

    Args:
        name: Protocol ka naam, jaise 'study', 'night', 'party', 'wake up'.
    """
    from difflib import get_close_matches

    with _db() as db:
        protocols = dict(db.execute("SELECT name, steps FROM protocols").fetchall())
    key = name.strip().lower().removesuffix(" protocol").strip()
    match = key if key in protocols else next(iter(get_close_matches(key, list(protocols), n=1, cutoff=0.6)), None)
    if not match:
        return f"'{name}' naam ka protocol nahi hai. Ye hain: {', '.join(protocols)}"
    return (f"PROTOCOL '{match}' ACTIVATED. Ab ye steps tools se ek-ek karke poore karo, phir Iron Man style me "
            f"chhota sa batao: {protocols[match]}")


def list_protocols() -> str:
    """Saare protocols aur unke steps dikhao."""
    with _db() as db:
        rows = db.execute("SELECT name, steps FROM protocols ORDER BY name").fetchall()
    return "\n".join(f"- {n}: {s}" for n, s in rows) if rows else "Koi protocol nahi hai."


def delete_protocol(name: str) -> str:
    """Protocol hata do.

    Args:
        name: Protocol ka naam.
    """
    with _db() as db:
        n = db.execute("DELETE FROM protocols WHERE name = ?", (name.strip().lower(),)).rowcount
    return f"'{name}' protocol hata diya." if n else f"'{name}' naam ka protocol nahi mila."


TOOLS = [remember, list_facts, forget_fact, search_memory,
         set_reminder, set_timer, list_reminders, cancel_reminder,
         save_contact, list_contacts,
         open_website, play_on_youtube, web_search, news_headlines,
         set_silent_mode, set_voice,
         save_protocol, run_protocol, list_protocols, delete_protocol]
