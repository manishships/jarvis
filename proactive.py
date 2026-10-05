"""JARVIS khud se bole - par kam aur sahi waqt pe (research: bina pooche baar-baar bolna irritate karta hai).
Start pe briefing, battery warning, raat ka review offer, lambe screen time pe aankhon ka break.
Silent mode me ye sab sirf screen/phone pe likhe jaate hain (jarvis.py/hud_app.py sambhalta hai)."""

import time
from datetime import datetime

import psutil

import lang


def greeting() -> str:
    h = datetime.now().hour
    return ("Good morning" if 4 <= h < 12 else "Good afternoon" if 12 <= h < 17 else "Good evening"
            if 17 <= h < 22 or lang.is_english() else "Itni raat ko jaage ho")


def briefing_prompt(user_name: str) -> str:
    if lang.is_english():
        return (
            f"[{datetime.now():%Y-%m-%d %H:%M}] [SYSTEM: JARVIS has just come online - the user hasn't asked anything yet. "
            f"Give {user_name} a short spoken briefing exactly like the AI butler JARVIS from Iron Man (2-4 sentences, "
            f"British English, no markdown/emoji): open with '{greeting()}, sir. Welcome home.' or similar, then the weather "
            f"via get_weather(''), today's pending reminders via list_reminders (if any), flashcards due via flashcard_stats "
            f"(one line, if any), today's study plan via today_plan (one line, if there is one), and battery via system_status "
            f"only if below 30%. End with a crisp, witty one-liner.]"
        )
    return (
        f"[{datetime.now():%Y-%m-%d %H:%M}] [SYSTEM: JARVIS abhi start hua hai - user ne kuch nahi poocha. "
        f"Tony Stark ke JARVIS ki tarah {user_name} ko chhoti si briefing do (bolke sunayi jayegi, 3-4 line, bina markdown/emoji): "
        f"'{greeting()}, sir. Welcome home.' jaisa shuru karo, get_weather('') se mausam, list_reminders se aaj ke pending "
        f"reminders (ho to), flashcard_stats se kitne cards due hain (ho to ek line), today_plan se aaj ka padhai plan (ho to ek line), "
        f"system_status se battery (sirf tab batao "
        f"jab 30% se kam ho). Padhai ka lecture nahi - bas ek chhoti, mazedaar line.]"
    )


def battery_watcher(notify):
    """Har minute battery dekho: kam ho aur charger na laga ho -> warning; full ho jaye -> bata do. Ek baar hi."""
    warned_low = warned_critical = warned_full = False
    while True:
        try:
            b = psutil.sensors_battery()
            if b:
                if b.power_plugged:
                    warned_low = warned_critical = False
                    if b.percent >= 100 and not warned_full:
                        notify(lang.t("battery_full"))
                        warned_full = True
                else:
                    warned_full = False
                    if b.percent <= 10 and not warned_critical:
                        notify(lang.t("battery_critical", p=f"{b.percent:.0f}"))
                        warned_critical = True
                    elif b.percent <= 20 and not warned_low:
                        notify(lang.t("battery_low", p=f"{b.percent:.0f}"))
                        warned_low = True
        except Exception:
            pass
        time.sleep(60)


def daily_review_watcher(review_time: str, notify):
    """Roz ek baar (jaise 21:30) din ka 2 minute review offer karo. Sirf offer - user 'review' bole tabhi hota hai."""
    last_day = None
    while True:
        current = datetime.now()
        if current.strftime("%H:%M") == review_time and last_day != current.date():
            last_day = current.date()
            notify(lang.t("review"))
        time.sleep(30)


def screen_break_watcher(minutes: int, notify):
    """Lagatar itne minute laptop pe ho (5 min ka bhi break nahi) to ek baar aankhon ka break yaad dilao (20-20-20).
    Padhai session ke beech nahi - wahan Pomodoro khud break deta hai."""
    import study

    active_since = time.time()
    reminded = False
    while True:
        time.sleep(30)
        try:
            if study.idle_seconds() > 300:  # 5 min ka break ho gaya - phir se shuru
                active_since, reminded = time.time(), False
                continue
            if not reminded and time.time() - active_since >= minutes * 60 and not study.session_status():
                notify(lang.t("screen_break", m=minutes))
                reminded = True
        except Exception:
            pass
