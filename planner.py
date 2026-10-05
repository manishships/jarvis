"""Boards ki taiyari: backlog planner (CBSE weightage ke hisaab se roz ka plan), galtiyon ki diary, board-style practice.

- Plan har baar BACHE hue lectures se naya banta hai - koi din chhoot jaye to apne aap aage adjust ho jata hai.
- Zyada marks / kam lectures wale chapter pehle; subjects mila-jula ke (interleaving - research me isse yaad zyada rehta hai).
- Galat jawab -> galtiyon ki diary + flashcard (taaki woh sawaal dobara aaye).
"""

import json
import re
from datetime import date, datetime, timedelta
from difflib import get_close_matches

import config
import memory

# CBSE Class 12 (2024-25 pattern) - har chapter ke lagbhag marks (unit ke marks chapters me baante gaye)
WEIGHTAGE = {
    "physics": {
        "electric charges and fields": 5, "electrostatic potential and capacitance": 5, "current electricity": 6,
        "moving charges and magnetism": 5, "magnetism and matter": 3, "electromagnetic induction": 4,
        "alternating current": 5, "electromagnetic waves": 3, "ray optics": 9, "wave optics": 6,
        "dual nature of radiation and matter": 4, "atoms": 4, "nuclei": 4, "semiconductor electronics": 7,
    },
    "chemistry": {
        "solutions": 7, "electrochemistry": 9, "chemical kinetics": 7, "d and f block elements": 7,
        "coordination compounds": 7, "haloalkanes and haloarenes": 6, "alcohols phenols and ethers": 6,
        "aldehydes ketones and carboxylic acids": 8, "amines": 6, "biomolecules": 7,
    },
    "maths": {
        "relations and functions": 4, "inverse trigonometric functions": 4, "matrices": 5, "determinants": 5,
        "continuity and differentiability": 8, "application of derivatives": 7, "integrals": 9,
        "application of integrals": 5, "differential equations": 6, "vectors": 7, "three dimensional geometry": 7,
        "linear programming": 5, "probability": 8,
    },
}
SUBJECT_ALIASES = {"math": "maths", "mathematics": "maths", "phy": "physics", "chem": "chemistry"}
CHAPTER_ALIASES = {
    "ac": "alternating current", "emi": "electromagnetic induction", "em waves": "electromagnetic waves",
    "electrostatics": "electric charges and fields", "capacitance": "electrostatic potential and capacitance",
    "magnetism": "moving charges and magnetism", "optics": "ray optics", "dual nature": "dual nature of radiation and matter",
    "semiconductors": "semiconductor electronics", "semiconductor": "semiconductor electronics",
    "d block": "d and f block elements", "d and f block": "d and f block elements", "coordination": "coordination compounds",
    "haloalkanes": "haloalkanes and haloarenes", "alcohols": "alcohols phenols and ethers",
    "aldehydes": "aldehydes ketones and carboxylic acids", "carbonyl": "aldehydes ketones and carboxylic acids",
    "kinetics": "chemical kinetics", "integration": "integrals", "integral": "integrals", "aod": "application of derivatives",
    "derivatives": "application of derivatives", "aoi": "application of integrals", "continuity": "continuity and differentiability",
    "differentiation": "continuity and differentiability", "de": "differential equations", "3d": "three dimensional geometry",
    "lpp": "linear programming", "itf": "inverse trigonometric functions", "inverse trigo": "inverse trigonometric functions",
    "relations": "relations and functions", "functions": "relations and functions",
}
DEFAULT_WEIGHT = 5  # English, CS waghera (weightage list me nahi)


def _subject(name: str) -> str:
    key = name.strip().lower()
    return SUBJECT_ALIASES.get(key, key)


def _chapter(subject: str, name: str) -> str:
    key = re.sub(r"[^a-z0-9 ]", " ", name.lower()).strip()
    key = re.sub(r"\s+", " ", key)
    key = CHAPTER_ALIASES.get(key, key)
    chapters = list(WEIGHTAGE.get(subject, {}))
    if key in chapters:
        return key
    match = get_close_matches(key, chapters, n=1, cutoff=0.6) or [c for c in chapters if key and key in c][:1]
    return match[0] if match else key


def _weight(subject: str, chapter: str) -> int:
    return WEIGHTAGE.get(subject, {}).get(chapter, DEFAULT_WEIGHT)


def _schema(db):
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS backlog (subject TEXT, chapter TEXT, remaining INTEGER, updated TEXT,
                                            PRIMARY KEY (subject, chapter));
        CREATE TABLE IF NOT EXISTS mistakes (id INTEGER PRIMARY KEY, ts TEXT, subject TEXT, chapter TEXT, question TEXT,
                                             my_answer TEXT, correct TEXT, reason TEXT);
        """
    )


def _days_to_exam() -> int:
    exam = datetime.strptime(config.BOARD_EXAM_DATE, "%Y-%m-%d").date()
    return (exam - date.today()).days


# ======================= Backlog =======================

def set_backlog(subject: str, chapter: str, lectures_left: int) -> str:
    """Kisi chapter ke kitne lectures BAAKI hain, ye save/update karo (backlog). 0 = chapter khatam.

    Args:
        subject: 'Physics', 'Chemistry', 'Maths' (ya koi aur subject).
        chapter: Chapter ka naam, jaise 'Alternating Current', 'Integration', 'Coordination Compounds'.
        lectures_left: Kitne lectures abhi baaki hain.
    """
    subj = _subject(subject)
    chap = _chapter(subj, chapter)
    with memory._db() as db:
        _schema(db)
        db.execute("INSERT OR REPLACE INTO backlog VALUES (?, ?, ?, ?)", (subj, chap, max(0, int(lectures_left)), memory.now()))
    return f"Backlog: {subj} - {chap}: {max(0, int(lectures_left))} lectures baaki (CBSE weightage ~{_weight(subj, chap)} marks)."


def lectures_done(subject: str, chapter: str, count: int) -> str:
    """User ne kisi chapter ke kuch lectures poore kar liye - backlog ghatao (plan apne aap adjust ho jata hai).

    Args:
        subject: Subject.
        chapter: Chapter ka naam.
        count: Kitne lectures poore kiye.
    """
    subj = _subject(subject)
    chap = _chapter(subj, chapter)
    with memory._db() as db:
        _schema(db)
        row = db.execute("SELECT remaining FROM backlog WHERE subject = ? AND chapter = ?", (subj, chap)).fetchone()
        if not row:
            return f"{subj} - {chap} backlog me nahi hai. (set_backlog se pehle add karo.)"
        left = max(0, row[0] - int(count))
        db.execute("UPDATE backlog SET remaining = ?, updated = ? WHERE subject = ? AND chapter = ?", (left, memory.now(), subj, chap))
    return f"Shabaash! {subj} - {chap}: {count} lectures done, ab {left} baaki." + (" Chapter khatam! 🎉" if left == 0 else "")


def backlog_status() -> str:
    """Poora backlog: subject/chapter-wise bache lectures, marks weightage, aur exam me kitne din."""
    with memory._db() as db:
        _schema(db)
        rows = db.execute("SELECT subject, chapter, remaining FROM backlog WHERE remaining > 0 ORDER BY subject").fetchall()
    if not rows:
        return "Backlog khaali hai (ya abhi tak bataya nahi). User se poochho: kis subject ke kaunse chapter ke kitne lectures baaki hain?"
    per_subject = {}
    for s, c, r in rows:
        per_subject.setdefault(s, []).append(f"{c} ({r} lec, ~{_weight(s, c)} marks)")
    total = sum(r for _, _, r in rows)
    return json.dumps({"days_to_exam": _days_to_exam(), "total_lectures_left": total, "backlog": per_subject}, ensure_ascii=False)


def _schedule(hours_per_day: float, days: int):
    """Bache lectures ko din-wise baanto. Lautata hai: (plan list, kitne lectures nahi samaye)."""
    with memory._db() as db:
        _schema(db)
        rows = db.execute("SELECT subject, chapter, remaining FROM backlog WHERE remaining > 0").fetchall()
        mistakes = dict(db.execute("SELECT chapter, COUNT(*) FROM mistakes GROUP BY chapter").fetchall())
    per_day = max(1, int(hours_per_day * 60 // config.LECTURE_MINUTES))
    # har subject ki queue: zyada marks per lecture (+ zyada galtiyan) wale chapter pehle
    queues = {}
    for s, c, r in rows:
        priority = _weight(s, c) / max(1, r) + 0.1 * mistakes.get(c, 0)
        queues.setdefault(s, []).append([priority, c, r])
    for q in queues.values():
        q.sort(key=lambda x: -x[0])
    order = sorted(queues, key=lambda s: -sum(_weight(s, c) for _, c, _ in queues[s]))
    plan, day = [], date.today()
    for n in range(max(1, days)):
        slots, today = per_day, []
        rotated = order[n % len(order):] + order[:n % len(order)] if order else []  # har din alag subject se shuru
        while slots and any(queues.values()):
            for s in rotated:  # subjects baari-baari, ek baar me max 2 lecture ek chapter ke
                if not slots or not queues[s]:
                    continue
                item = queues[s][0]
                take = min(2, item[2], slots)
                today.append((s, item[1], take))
                item[2] -= take
                slots -= take
                if item[2] == 0:
                    queues[s].pop(0)
        if not today:
            break
        plan.append((day, today))
        day += timedelta(days=1)
    left_over = sum(item[2] for q in queues.values() for item in q)
    return plan, left_over, per_day


def study_plan(hours_per_day: float, days: int) -> str:
    """Backlog se roz ka study plan banao (CBSE weightage + galtiyon ke hisaab se). Har baar bache lectures se naya plan
    banta hai, isliye din chhoot jaye to bhi theek. Lamba plan ho to write_document se sundar page bhi bana sakte ho.

    Args:
        hours_per_day: Roz kitne ghante lecture dekh sakta hai (jaise 4).
        days: Kitne din me backlog khatam karna hai (0 = exam se 30 din pehle tak, revision ke liye time chhod ke).
    """
    if days <= 0:
        days = max(1, _days_to_exam() - 30)
    plan, left_over, per_day = _schedule(hours_per_day, days)
    if not plan:
        return backlog_status()
    out = {
        "lectures_per_day": per_day, "days_needed": len(plan), "finish_date": plan[-1][0].strftime("%d %b"),
        "days_to_exam": _days_to_exam(),
        "first_7_days": {d.strftime("%a %d %b"): [f"{s}: {c} x{n}" for s, c, n in items] for d, items in plan[:7]},
    }
    if left_over:
        out["warning"] = (f"{left_over} lectures {days} din me nahi samaye - roz ka time badhao ya din badhao.")
    return json.dumps(out, ensure_ascii=False)


def today_plan() -> str:
    """Aaj ke liye kya padhna hai (backlog plan se, config ke roz ke ghante ke hisaab se)."""
    plan, _, _ = _schedule(config.STUDY_HOURS_PER_DAY, 1)
    if not plan:
        return "Aaj ke liye backlog plan nahi hai (backlog khaali hai ya bataya nahi)."
    return "Aaj: " + "; ".join(f"{s.title()} - {c} ({n} lec)" for s, c, n in plan[0][1])


# ======================= Galtiyon ki diary =======================

def log_mistake(subject: str, chapter: str, question: str, correct_answer: str, my_answer: str, reason: str) -> str:
    """Galti diary me likho (quiz/practice me galat jawab) - aur uska flashcard bhi bana do taaki dobara aaye.

    Args:
        subject: Subject.
        chapter: Chapter.
        question: Sawaal (chhota).
        correct_answer: Sahi jawab (1-2 line).
        my_answer: User ne kya jawab diya tha.
        reason: Galti kyun hui: 'concept', 'calculation', 'formula', 'silly' ya 'unknown'.
    """
    import study

    subj = _subject(subject)
    chap = _chapter(subj, chapter)
    reason = reason.strip().lower() if reason.strip().lower() in ("concept", "calculation", "formula", "silly") else "unknown"
    with memory._db() as db:
        _schema(db)
        db.execute("INSERT INTO mistakes (ts, subject, chapter, question, my_answer, correct, reason) VALUES (?, ?, ?, ?, ?, ?, ?)",
                   (memory.now(), subj, chap, question.strip(), my_answer.strip(), correct_answer.strip(), reason))
    study.add_flashcards(f"{subj.title()} - {chap} (galti)", f"{question.strip().replace('|', '/')} | {correct_answer.strip().replace('|', '/')}")
    return f"Galti diary me likh li ({reason}) + flashcard bana diya - ye sawaal jald dobara aayega."


def record_quiz_miss(card_subject: str, question: str, answer: str) -> None:
    """Quiz me 'again' (galat) -> diary me apne aap (study.quiz_grade bulata hai)."""
    subj, _, chap = card_subject.partition(" - ")
    with memory._db() as db:
        _schema(db)
        db.execute("INSERT INTO mistakes (ts, subject, chapter, question, my_answer, correct, reason) VALUES (?, ?, ?, ?, '', ?, 'quiz')",
                   (memory.now(), _subject(subj), chap.replace("(galti)", "").strip().lower() or "general", question, answer))


def mistake_report(days: int) -> str:
    """Galtiyon ka hisaab: kaunse chapter me sabse zyada, aur galti ka type (concept/calculation/silly...). Weak chapters dikhao.

    Args:
        days: Pichhle kitne din (7 = hafta, 365 = sab).
    """
    since = (datetime.now() - timedelta(days=max(1, days))).strftime("%Y-%m-%d %H:%M")
    with memory._db() as db:
        _schema(db)
        rows = db.execute("SELECT subject, chapter, reason FROM mistakes WHERE ts >= ?", (since,)).fetchall()
    if not rows:
        return f"Pichhle {days} din me koi galti record nahi hui. 💪"
    chapters, reasons = {}, {}
    for s, c, r in rows:
        chapters[f"{s} - {c}"] = chapters.get(f"{s} - {c}", 0) + 1
        reasons[r] = reasons.get(r, 0) + 1
    weak = sorted(chapters.items(), key=lambda x: -x[1])[:5]
    return json.dumps({"days": days, "total_mistakes": len(rows), "weak_chapters": dict(weak), "by_reason": reasons},
                      ensure_ascii=False)


# ======================= Board-style practice (mixed / interleaved) =======================

def practice_set(subjects: str, count: int) -> str:
    """Mixed board-style practice set ke chapters chuno (alag-alag chapter mila ke - interleaving), weightage aur
    purani galtiyon ke hisaab se. Phir user se EK-EK sawaal poochho (CBSE pattern: 1, 2, 3, 5 marks), jawab check karo,
    galat ho to poochho galti kyun hui aur log_mistake karo. Kisi saal ka 'PYQ' tabhi bolo jab pakka pata ho.

    Args:
        subjects: Comma se alag subjects, jaise 'Physics, Chemistry' (khaali = Physics, Chemistry, Maths).
        count: Kitne sawaal (5-15).
    """
    import random

    wanted = [_subject(s) for s in subjects.split(",") if s.strip()] or ["physics", "chemistry", "maths"]
    with memory._db() as db:
        _schema(db)
        backlog = {(s, c) for s, c, r in db.execute("SELECT subject, chapter, remaining FROM backlog").fetchall() if r > 0}
        mistakes = dict(db.execute("SELECT chapter, COUNT(*) FROM mistakes GROUP BY chapter").fetchall())
    pool = []
    for s in wanted:
        for c, w in WEIGHTAGE.get(s, {}).items():
            if (s, c) not in backlog:  # jo chapter abhi padha hi nahi, us pe practice nahi
                pool.append((s, c, w + 3 * mistakes.get(c, 0)))
    if not pool:
        return "Practice ke liye koi padha hua chapter nahi mila (sab backlog me hain)."
    count = max(3, min(int(count), 20))
    picks, last = [], None
    for _ in range(count):
        options = [p for p in pool if p[0] != last] or pool
        s, c, _ = random.choices(options, weights=[p[2] for p in options])[0]
        picks.append((s, c))
        last = s
    marks = [1, 2, 3, 1, 5, 2, 3, 1, 2, 5]
    return json.dumps({"questions": [{"no": i + 1, "subject": s, "chapter": c, "marks": marks[i % len(marks)]}
                                     for i, (s, c) in enumerate(picks)],
                       "how": "Ek-ek sawaal poochho, jawab ka intezaar karo, check karke sahi tareeka batao, galat pe "
                              "log_mistake. End me score + mistake_report."}, ensure_ascii=False)


TOOLS = [set_backlog, lectures_done, backlog_status, study_plan, today_plan, log_mistake, mistake_report, practice_set]
