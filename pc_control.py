"""JARVIS ke haath-pair: laptop control (apps, volume, brightness, screen dekhna, typing, files, power).

Khatarnaak kaam (shutdown, restart, app zabardasti band) se pehle JARVIS hamesha tumse 'haan' poochta hai.
"""

import io
import json
import os
import subprocess
import time
from datetime import datetime
from difflib import get_close_matches
from pathlib import Path

import psutil

# jarvis.py inhe set karta hai: CONFIRM(sawaal) -> True/False, VISION(jpeg_bytes, sawaal) -> jawab
CONFIRM = None
VISION = None
DEFAULT_CITY = ""  # jarvis.py HOME_CITY se set hota hai

HOME = Path.home()
WORK_DIR = HOME / "Documents" / "JARVIS"            # JARVIS ke banaye documents yahan
SCREENSHOT_DIR = HOME / "Pictures" / "JARVIS Screenshots"
SEARCH_DIRS = [HOME / d for d in ("Desktop", "Documents", "Downloads", "Pictures", "Videos", "Music", "OneDrive/Desktop", "OneDrive/Documents")]
SKIP_DIRS = {"node_modules", ".git", ".venv", "venv", "__pycache__", "AppData", "site-packages"}
NO_WINDOW = 0x08000000

_apps_cache = None


def _confirm(question: str) -> bool:
    return bool(CONFIRM and CONFIRM(question))


RISKY_EXTENSIONS = {".exe", ".bat", ".cmd", ".com", ".ps1", ".psm1", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh",
                    ".msi", ".msp", ".scr", ".pif", ".lnk", ".url", ".reg", ".jar", ".hta", ".cpl", ".appref-ms"}
RISKY_APP_WORDS = ("powershell", "command prompt", "terminal", "cmd", "registry", "regedit")


def _risky_ok(question: str) -> bool:
    """config.ASK_BEFORE_RISKY on ho to khatarnaak kaam se pehle user se 'haan' lo."""
    import config

    return (not getattr(config, "ASK_BEFORE_RISKY", True)) or _confirm(question)


def _start_apps() -> dict[str, str]:
    """Start menu ke saare apps (Store wale bhi): naam -> AppID."""
    global _apps_cache
    if _apps_cache is None:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-StartApps | ConvertTo-Json -Compress"],
            capture_output=True, text=True, encoding="utf-8", creationflags=NO_WINDOW,
        ).stdout
        apps = json.loads(out) if out.strip() else []
        apps = apps if isinstance(apps, list) else [apps]
        _apps_cache = {a["Name"].lower(): a["AppID"] for a in apps}
    return _apps_cache


ALIASES = {"chrome": "google chrome", "vs code": "visual studio code", "vscode": "visual studio code", "code": "visual studio code",
           "edge": "microsoft edge", "calculator": "calculator", "calc": "calculator", "setting": "settings",
           "explorer": "file explorer", "file manager": "file explorer", "files": "file explorer"}


# ---------------- Apps ----------------

def open_app(name: str) -> str:
    """Laptop pe koi app kholo (Chrome, VS Code, Notepad, Calculator, Settings, WhatsApp, Spotify, Discord, Camera...).

    Args:
        name: App ka naam, jaise 'chrome' ya 'notepad'.
    """
    apps = _start_apps()
    key = ALIASES.get(name.lower().strip(), name.lower().strip())
    match = key if key in apps else next((a for a in apps if key in a), None)
    if not match:
        close = get_close_matches(key, list(apps), n=1, cutoff=0.6)
        match = close[0] if close else None
    if not match:
        return f"'{name}' naam ka app nahi mila. Installed apps me ye kuch milte-julte hain: {get_close_matches(key, list(apps), n=5, cutoff=0.3)}"
    if any(w in match for w in RISKY_APP_WORDS) and not _risky_ok(f"'{match}' kholun? (isse laptop pe commands chal sakti hain)"):
        return f"User ne haan nahi bola, isliye '{match}' nahi khola."
    subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{apps[match]}"])
    time.sleep(2)  # app khulne do, taaki agla kaam (typing) sahi window me ho
    return f"'{match}' khol diya."


def close_app(name: str) -> str:
    """Koi chalta hua app band karo (unsaved kaam ud sakta hai, isliye user se confirm hota hai).

    Args:
        name: App/process ka naam, jaise 'chrome', 'notepad', 'discord'.
    """
    key = name.lower().replace(" ", "")
    procs = [p for p in psutil.process_iter(["name"]) if p.info["name"] and key in p.info["name"].lower().replace(" ", "")]
    if not procs:
        return f"'{name}' abhi chal hi nahi raha."
    if not _confirm(f"{name} band kar doon? Unsaved kaam ud sakta hai."):
        return "User ne mana kar diya, band nahi kiya."
    for p in procs:
        try:
            p.terminate()
        except psutil.Error:
            pass
    return f"'{name}' band kar diya ({len(procs)} process)."


# ---------------- Sound, screen, media ----------------

def set_volume(level: int) -> str:
    """Laptop ka volume set karo.

    Args:
        level: 0 se 100 tak.
    """
    from pycaw.pycaw import AudioUtilities

    vol = AudioUtilities.GetSpeakers().EndpointVolume
    vol.SetMute(0, None)
    vol.SetMasterVolumeLevelScalar(max(0, min(level, 100)) / 100, None)
    return f"Volume {level}% kar diya."


def change_volume(delta: int) -> int:
    """Volume ko delta se badhao/ghatao (gestures ke liye). Naya volume lautata hai."""
    import comtypes
    from pycaw.pycaw import AudioUtilities

    try:
        comtypes.CoInitialize()  # doosre thread se bhi chale
    except OSError:
        pass
    vol = AudioUtilities.GetSpeakers().EndpointVolume
    level = max(0, min(100, round(vol.GetMasterVolumeLevelScalar() * 100) + delta))
    vol.SetMute(0, None)
    vol.SetMasterVolumeLevelScalar(level / 100, None)
    return level


def mute(on: bool) -> str:
    """Laptop ki aawaz mute ya unmute karo.

    Args:
        on: true = mute, false = unmute.
    """
    from pycaw.pycaw import AudioUtilities

    AudioUtilities.GetSpeakers().EndpointVolume.SetMute(1 if on else 0, None)
    return "Mute kar diya." if on else "Unmute kar diya."


def set_brightness(level: int) -> str:
    """Screen ki brightness set karo.

    Args:
        level: 0 se 100 tak.
    """
    import screen_brightness_control as sbc

    sbc.set_brightness(max(5, min(level, 100)))
    return f"Brightness {level}% kar di."


def media_control(action: str) -> str:
    """Chal rahe gaane/video ko control karo (YouTube, Spotify, kuch bhi).

    Args:
        action: 'play_pause', 'next' ya 'previous'.
    """
    import pyautogui

    keys = {"play_pause": "playpause", "next": "nexttrack", "previous": "prevtrack"}
    if action not in keys:
        return "action 'play_pause', 'next' ya 'previous' hona chahiye."
    pyautogui.press(keys[action])
    return f"Done: {action}."


def take_screenshot() -> str:
    """Screen ka screenshot le ke Pictures/JARVIS Screenshots me save karo."""
    from PIL import ImageGrab

    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SCREENSHOT_DIR / f"screenshot_{datetime.now():%Y-%m-%d_%H-%M-%S}.png"
    ImageGrab.grab().save(path)
    return f"Screenshot save ho gaya: {path}"


def look_at_screen(question: str) -> str:
    """Abhi laptop ki screen pe kya hai, use dekh ke sawaal ka jawab do (error samjhana, question solve karna, kya khula hai...).

    Args:
        question: Screen ke baare me kya jaanna hai, e.g. 'ye error kya hai?' ya 'is question ka answer kya hai?'.
    """
    from PIL import ImageGrab

    if VISION is None:
        return "Screen dekhne ki suvidha abhi set nahi hai."
    buf = io.BytesIO()
    ImageGrab.grab().convert("RGB").save(buf, format="JPEG", quality=80)
    return VISION(buf.getvalue(), question)


# ---------------- Typing ----------------

def type_text(text: str) -> str:
    """Jo window abhi khuli/active hai usme text type karo (Hindi/emoji bhi). Pehle sahi app khol lo.

    Args:
        text: Kya type karna hai.
    """
    import pyautogui
    import pyperclip

    old = pyperclip.paste()
    pyperclip.copy(text)
    time.sleep(0.2)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.3)
    pyperclip.copy(old)  # user ka clipboard wapas
    return "Type kar diya."


def press_keys(keys: str) -> str:
    """Keyboard shortcut dabao, jaise 'ctrl+s' (save), 'alt+tab' (window badlo), 'win+d' (desktop), 'ctrl+t' (nayi tab), 'enter'.

    Args:
        keys: '+' se jude keys, e.g. 'ctrl+shift+esc'.
    """
    import pyautogui

    parts = [k.strip().lower() for k in keys.split("+") if k.strip()]
    parts = ["win" if k in ("windows", "window") else k for k in parts]
    bad = [k for k in parts if k not in pyautogui.KEYBOARD_KEYS]
    if bad:
        return f"Ye keys samajh nahi aayi: {bad}"
    pyautogui.hotkey(*parts)
    return f"Dabaya: {keys}"


def read_clipboard() -> str:
    """User ne jo copy kiya hai (Ctrl+C) woh text padho - summarize, translate ya explain karne ke liye."""
    import pyperclip

    text = pyperclip.paste()
    return text[:8000] if text else "Clipboard khaali hai."


# ---------------- WhatsApp (JARVIS ke browser se, browser.py) ----------------

def send_whatsapp(to: str, message: str, send: bool) -> str:
    """WhatsApp pe kisi ko message likho ya bhejo. Naam se chat dhoondhta hai (WhatsApp me jo naam save hai), ya saved contact/number se.
    send=True pe bhejne se pehle user se confirm hota hai, aur bhejne ke baad check hota hai ki sach me gaya.

    Args:
        to: WhatsApp me chat ka naam (jaise 'Rahul Sharma'), saved contact ka naam, ya mobile number.
        message: Kya bhejna hai - user ke shabdon me, apni taraf se kuch mat jodo.
        send: true = bhej do, false = sirf chat me likh ke chhod do (draft).
    """
    import browser
    import memory

    number = memory.find_contact(to) or (memory.normalize_phone(to) if any(c.isdigit() for c in to) else None)
    if send and not _confirm(f"{to} ko WhatsApp pe ye message bhejun: '{message}'?"):
        return "User ne haan nahi bola, isliye message nahi bheja."
    return browser.whatsapp_message(to, message, send, number)


def read_whatsapp(chat: str, count: int) -> str:
    """WhatsApp ke kisi chat ke last messages padho (jaise 'Rahul ne kya bola?').

    Args:
        chat: Chat ka naam jaisa WhatsApp me hai.
        count: Kitne last messages (1-30).
    """
    import browser

    return browser.whatsapp_read(chat, max(1, min(count, 30)))


# ---------------- Kisi bhi app ke buttons (Windows UI Automation) ----------------

def _foreground_controls(limit: int = 80):
    import uiautomation as auto

    win = auto.GetForegroundControl().GetTopLevelControl()
    found = []

    def walk(c, depth=0):
        if depth > 25 or len(found) >= limit:
            return
        for ch in c.GetChildren():
            if ch.ControlTypeName in ("ButtonControl", "MenuItemControl", "HyperlinkControl", "TabItemControl",
                                      "ListItemControl", "CheckBoxControl", "EditControl", "ComboBoxControl",
                                      "RadioButtonControl", "TreeItemControl", "TextControl") and (ch.Name or "").strip() \
                    and not (ch.ControlTypeName == "TextControl" and len(ch.Name) > 120):
                found.append(ch)
            walk(ch, depth + 1)

    walk(win)
    return win, found


def screen_controls() -> str:
    """Abhi saamne wali app/window me kaun-kaun se buttons, menu, tabs, boxes hain - unke naam (click_control se pehle dekhne ke liye)."""
    win, found = _foreground_controls()
    items = [f"{c.ControlTypeName.replace('Control', '')}: {c.Name[:60]}" for c in found]
    if not items:
        return f"Window '{win.Name}' me naam wale controls nahi mile (look_at_screen try karo)."
    return f"Window: {win.Name}\n" + "\n".join(items)


def click_control(name: str) -> str:
    """Saamne wali app me naam se button/menu/tab/item pe click karo (screen_controls se naam dekho).

    Args:
        name: Control ka naam, jaise 'Bluetooth & devices' ya 'Save'.
    """
    _, found = _foreground_controls(limit=300)
    key = name.lower().strip()
    match = next((c for c in found if c.Name.lower().strip() == key), None) or next((c for c in found if key in c.Name.lower()), None)
    if not match:
        return f"'{name}' naam ka control nahi mila."
    match.Click(simulateMove=False)
    time.sleep(1)
    return f"'{match.Name}' pe click kiya."


# ---------------- Files & documents ----------------

NOTE_PAGE = """<!doctype html>
<html lang="hi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<script>window.MathJax = {{tex: {{inlineMath: [['$', '$'], ['\\\\(', '\\\\)']], displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']]}}}};</script>
<script defer src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js"></script>
<style>
  :root {{ --bg: #f7fafc; --card: #ffffff; --ink: #14202b; --muted: #5b6b78; --accent: #0a84b8; --line: #dbe5ec; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --bg: #071019; --card: #0c1a26; --ink: #dcefff; --muted: #86a3b8; --accent: #33d6ff; --line: #17324a; }} }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: var(--bg); color: var(--ink); font: 17px/1.65 "Segoe UI", system-ui, sans-serif; }}
  header {{ padding: 28px 16px 18px; border-bottom: 2px solid var(--accent); background: var(--card); }}
  header, main {{ max-width: 860px; margin: 0 auto; }}
  .badge {{ color: var(--accent); font: 600 12px/1 Consolas, monospace; letter-spacing: .2em; }}
  h1 {{ margin: 8px 0 4px; font-size: 30px; }}
  .meta {{ color: var(--muted); font-size: 14px; }}
  button {{ float: right; margin-top: -40px; border: 1px solid var(--accent); background: transparent; color: var(--accent);
           border-radius: 8px; padding: 6px 12px; cursor: pointer; font: inherit; font-size: 14px; }}
  main {{ padding: 8px 16px 48px; }}
  h2 {{ margin-top: 30px; padding-bottom: 4px; border-bottom: 1px solid var(--line); color: var(--accent); }}
  h3 {{ margin-top: 22px; }}
  code, pre {{ background: var(--card); border: 1px solid var(--line); border-radius: 6px; }}
  code {{ padding: 1px 5px; }} pre {{ padding: 12px; overflow-x: auto; }}
  table {{ border-collapse: collapse; width: 100%; margin: 14px 0; background: var(--card); }}
  th, td {{ border: 1px solid var(--line); padding: 8px 10px; text-align: left; }}
  blockquote {{ margin: 14px 0; padding: 8px 14px; border-left: 4px solid var(--accent); background: var(--card); }}
  mjx-container {{ overflow-x: auto; overflow-y: hidden; }}
  @media print {{ button {{ display: none; }} body {{ background: #fff; color: #000; }} }}
</style></head>
<body><header><div class="badge">J.A.R.V.I.S. NOTES</div><h1>{title}</h1><div class="meta">{date}</div>
<button onclick="window.print()">🖨 Print / PDF</button></header>
<main>{body}</main></body></html>"""


def _render_markdown(content: str) -> str:
    """Markdown -> HTML, par formulas ($...$, $$...$$) ko chhede bina (MathJax unhe sundar dikhata hai)."""
    import html
    import re

    import markdown

    maths = []

    def keep(m):
        maths.append(html.escape(m.group(0)))
        return f"@@MATH{len(maths) - 1}@@"

    protected = re.sub(r"\$\$.+?\$\$|\\\[.+?\\\]|\$[^$\n]+?\$|\\\(.+?\\\)", keep, content, flags=re.S)
    body = markdown.markdown(protected, extensions=["tables", "fenced_code", "sane_lists", "nl2br"])
    return re.sub(r"@@MATH(\d+)@@", lambda m: maths[int(m.group(1))], body)


def write_document(title: str, content: str) -> str:
    """Notes, essay, application, study plan, to-do list jaisa document banao. Sundar page (formulas ke saath) ban ke
    Documents/JARVIS me save hota hai aur browser me khulta hai (Print/PDF button ke saath).

    Args:
        title: Document ka naam, e.g. 'Physics notes - Alternating Current'.
        content: Poora content Markdown me (## headings, - bullets, **bold**, tables). Formula $...$ ya $$...$$ me likho.
    """
    import html

    WORK_DIR.mkdir(parents=True, exist_ok=True)
    safe = "".join(c for c in title if c not in '<>:"/\\|?*').strip() or "note"
    path = WORK_DIR / f"{safe}.html"
    if path.exists():
        path = WORK_DIR / f"{safe} ({datetime.now():%Y-%m-%d %H-%M}).html"
    page = NOTE_PAGE.format(title=html.escape(title), date=datetime.now().strftime("%d %b %Y, %I:%M %p"),
                            body=_render_markdown(content))
    path.write_text(page, encoding="utf-8")
    os.startfile(path)
    return f"Document bana ke browser me khol diya. Path: {path}"


PHONE = None  # jarvis set karta hai (Telegram bot): send(text), send_photo(bytes, caption), send_document(path, caption)


def send_to_phone(text: str, screenshot: bool, file_path: str) -> str:
    """User ke phone pe (Telegram) bhejo: message, laptop ka screenshot, aur/ya koi file (jaise banaye hue notes).

    Args:
        text: Message (khaali = koi message nahi).
        screenshot: true = abhi ki screen ki photo bhi bhejo.
        file_path: Bhejni wali file ka poora path (khaali = koi file nahi), jaise write_document ka diya path.
    """
    if PHONE is None:
        return "Phone link (Telegram bot) abhi chalu nahi hai - JARVIS.bat se chalao aur keys.env me TELEGRAM_BOT_TOKEN ho."
    sent = []
    if text.strip():
        PHONE.send(text.strip())
        sent.append("message")
    if screenshot:
        from PIL import ImageGrab

        buf = io.BytesIO()
        ImageGrab.grab().convert("RGB").save(buf, format="JPEG", quality=85)
        PHONE.send_photo(buf.getvalue(), "💻 Laptop ki screen")
        sent.append("screenshot")
    if file_path.strip():
        if not os.path.isfile(file_path.strip()):
            return f"Ye file nahi mili: {file_path}" + (f" (baaki bhej diya: {', '.join(sent)})" if sent else "")
        inside_work_dir = Path(file_path.strip()).resolve().is_relative_to(WORK_DIR.resolve())
        if not inside_work_dir and not _risky_ok(f"Ye file phone pe bhejun: {Path(file_path.strip()).name}?"):
            return "User ne haan nahi bola, isliye file nahi bheji." + (f" (baaki bhej diya: {', '.join(sent)})" if sent else "")
        PHONE.send_document(file_path.strip(), "📄 " + Path(file_path.strip()).name)
        sent.append(Path(file_path.strip()).name)
    return "Phone pe bhej diya: " + ", ".join(sent) if sent else "Kuch bhejne ko nahi tha."


def find_files(name: str) -> str:
    """Laptop pe (Desktop, Documents, Downloads, Pictures, Videos, Music) file ya folder naam se dhoondo.

    Args:
        name: Naam ka hissa, e.g. 'resume' ya 'physics'.
    """
    key, found, deadline = name.lower(), [], time.time() + 8
    for base in SEARCH_DIRS:
        if len(found) >= 15 or time.time() > deadline:
            break
        if not base.exists():
            continue
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
            found += [os.path.join(root, f) for f in dirs + files if key in f.lower()]
            if len(found) >= 15 or time.time() > deadline:
                break
    return json.dumps(found[:15], ensure_ascii=False) if found else f"'{name}' naam ki koi file nahi mili."


def open_path(path: str) -> str:
    """Koi file ya folder kholo (find_files se mila hua poora path).

    Args:
        path: Poora path.
    """
    if not os.path.exists(path):
        return "Ye path exist nahi karta."
    if Path(path).suffix.lower() in RISKY_EXTENSIONS and not _risky_ok(f"Ye program/script chalaun: {Path(path).name}?"):
        return f"User ne haan nahi bola, isliye {Path(path).name} nahi chalaya."
    os.startfile(path)
    return f"Khol diya: {path}"


# ---------------- System ----------------

def system_status() -> str:
    """Laptop ki abhi ki halat batao: battery, charging, volume, brightness, CPU, RAM, disk. Har baar naya data lo."""
    import screen_brightness_control as sbc
    from pycaw.pycaw import AudioUtilities

    b = psutil.sensors_battery()
    disk = psutil.disk_usage("C:\\")
    vol = AudioUtilities.GetSpeakers().EndpointVolume
    try:
        brightness = sbc.get_brightness()[0]
    except Exception:
        brightness = None
    return json.dumps({
        "volume_percent": round(vol.GetMasterVolumeLevelScalar() * 100),
        "muted": bool(vol.GetMute()),
        "brightness_percent": brightness,
        "battery_percent": b.percent if b else None,
        "charging": b.power_plugged if b else None,
        "cpu_percent": psutil.cpu_percent(interval=0.5),
        "ram_used_percent": psutil.virtual_memory().percent,
        "c_drive_free_gb": round(disk.free / 1e9, 1),
    })


def power_action(action: str) -> str:
    """Laptop lock, sleep, shutdown ya restart karo. Lock ke alawa sab pe user se confirm hota hai.

    Args:
        action: 'lock', 'sleep', 'shutdown' ya 'restart'.
    """
    if action == "lock":
        subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"])
        return "Laptop lock kar diya."
    commands = {
        "shutdown": ["shutdown", "/s", "/t", "15"],
        "restart": ["shutdown", "/r", "/t", "15"],
        "sleep": ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
    }
    if action not in commands:
        return "action 'lock', 'sleep', 'shutdown' ya 'restart' hona chahiye."
    if not _confirm(f"Pakka laptop {action} kar doon?"):
        return "User ne mana kar diya."
    subprocess.run(commands[action])
    return f"{action} ho raha hai (shutdown/restart 15 second me; rokna ho to 'shutdown /a')."


def get_weather(city: str) -> str:
    """Abhi ka mausam aur aaj ka forecast. City khaali do to user ke ghar (default city) ka.

    Args:
        city: Shehar ka naam (e.g. 'Delhi'), ya khaali string = user ka ghar wala shehar.
    """
    import urllib.request
    from urllib.parse import quote

    try:
        with urllib.request.urlopen(f"https://wttr.in/{quote(city.strip() or DEFAULT_CITY)}?format=j1", timeout=15) as r:
            d = json.load(r)
    except Exception as e:
        return f"Mausam nahi mil paya: {e}"
    now, today, area = d["current_condition"][0], d["weather"][0], d["nearest_area"][0]
    return json.dumps({
        "place": area["areaName"][0]["value"], "temp_c": now["temp_C"], "feels_like_c": now["FeelsLikeC"],
        "condition": now["weatherDesc"][0]["value"], "humidity": now["humidity"],
        "today_min_c": today["mintempC"], "today_max_c": today["maxtempC"],
    })


TOOLS = [send_whatsapp, read_whatsapp, screen_controls, click_control, open_app, close_app, set_volume, mute, set_brightness, media_control, take_screenshot, look_at_screen,
         type_text, press_keys, read_clipboard, write_document, send_to_phone, find_files, open_path, system_status, power_action, get_weather]
