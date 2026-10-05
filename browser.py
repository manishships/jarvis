"""JARVIS ka apna browser (Edge, Playwright se): WhatsApp Web aur websites pe asli kaam.

Page ke andar ke buttons/boxes seedha pehchanta hai, isliye 'bhej diya' tabhi bolta hai jab sach me gaya ho.
Login (WhatsApp QR waghera) is profile me ek baar karna padta hai, phir yaad rehta hai.
"""

import functools
import re
import time
from pathlib import Path
from urllib.parse import quote_plus

PROFILE_DIR = Path(__file__).with_name("browser_profile")
WHATSAPP_URL = "https://web.whatsapp.com"

_pw = None
_ctx = None


def _context():
    """JARVIS ki Edge window (band ho gayi ho to dobara kholo)."""
    global _pw, _ctx
    if _ctx is not None:
        try:
            _ctx.pages  # zinda hai?
            if _ctx.pages:
                return _ctx
        except Exception:
            pass
        close()
    from playwright.sync_api import sync_playwright

    _pw = sync_playwright().start()
    try:
        _ctx = _pw.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR), channel="msedge", headless=False,
            no_viewport=True, args=["--start-maximized"],
        )
        _ctx.set_default_timeout(10_000)  # kuch atke to 10 sec me error, 30 nahi
    except Exception as e:
        close()
        if "existing browser session" in str(e) or "already in use" in str(e):
            raise RuntimeError("JARVIS ka browser pehle se kisi aur JARVIS / WhatsApp Login window me khula hai. "
                               "Use band karke dobara try karo.") from None
        raise
    return _ctx


def close():
    global _pw, _ctx
    try:
        if _ctx:
            _ctx.close()
        if _pw:
            _pw.stop()
    except Exception:
        pass
    _pw = _ctx = None


def _page(url_part: str | None = None):
    """url_part wala tab dhoondho (na mile to naya/khaali tab)."""
    ctx = _context()
    if url_part:
        for p in ctx.pages:
            if url_part in p.url:
                p.bring_to_front()
                return p
    blank = next((p for p in ctx.pages if p.url in ("about:blank", "edge://newtab/", "chrome://newtab/")), None)
    page = blank or ctx.new_page()
    page.bring_to_front()
    return page


def _resilient(fn):
    """User ne JARVIS ki browser window band kar di ho to dobara khol ke ek baar phir try karo."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            if "closed" not in str(e).lower():
                raise
            close()
            return fn(*args, **kwargs)
    return wrapper


def _first_visible(page, selectors: list[str], timeout: float = 10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        for sel in selectors:
            loc = page.locator(sel)
            try:
                if loc.count() and loc.first.is_visible():
                    return loc.first
            except Exception:
                pass
        time.sleep(0.3)
    return None


# ======================= WhatsApp =======================

SEARCH_BOX = ['#side [contenteditable="true"]', 'input[aria-label*="Search" i]', '[role="textbox"][aria-label*="Search" i]']
COMPOSE_BOX = ['#main footer [contenteditable="true"]', '#main [role="textbox"][aria-label*="message" i]', 'footer [contenteditable="true"]']


SAFE_POPUP_BUTTONS = ("Continue", "OK", "Got it", "Not now", "Close", "Dismiss", "Skip")


def _dismiss_popups(page) -> None:
    """'What's new' jaise WhatsApp popups band karo - sirf safe buttons (kabhi Log out/Delete waghera nahi)."""
    for _ in range(3):
        dialog = page.locator('[role="dialog"]')
        if not dialog.count():
            return
        for label in SAFE_POPUP_BUTTONS:
            button = dialog.first.get_by_role("button", name=label, exact=True)
            if button.count():
                button.first.click(timeout=3000)
                break
        else:
            page.keyboard.press("Escape")
        time.sleep(0.8)


def _whatsapp_ready():
    """WhatsApp Web khula aur logged-in ho. Nahi to (None, wajah)."""
    page = _page("web.whatsapp.com")
    if "web.whatsapp.com" not in page.url:
        page.goto(WHATSAPP_URL, wait_until="domcontentloaded")
    deadline = time.time() + 60
    while time.time() < deadline:
        if page.locator("#pane-side").count():
            time.sleep(1)
            _dismiss_popups(page)
            return page, None
        if page.locator('canvas[aria-label*="QR" i]').count():
            return None, ("WhatsApp login nahi hai. JARVIS ki Edge window me QR code khula hai - user apne phone me "
                          "WhatsApp > Linked devices > Link a device se scan kare (sirf ek baar). Phir dobara try karna.")
        time.sleep(0.5)
    return None, "WhatsApp Web 60 second me load nahi hua (internet slow?)."


def _open_chat_by_name(page, name: str):
    """Search box me naam likh ke sabse milta-julta chat kholo. Lautao: (chat ka naam, error)."""
    box = _first_visible(page, SEARCH_BOX, timeout=10)
    if not box:
        return None, "WhatsApp ka search box nahi mila."
    box.click()
    page.keyboard.press("Control+A")
    page.keyboard.press("Backspace")
    page.keyboard.type(name, delay=40)
    time.sleep(2)
    titles = page.locator("#pane-side span[title]")
    names = []
    for i in range(min(titles.count(), 40)):
        t = (titles.nth(i).get_attribute("title") or "").strip("\u202a\u202c ")
        # chat ke naam chhote hote hain; lambe/multi-line title = message ka preview, time/date wale bhi chhodo
        if t and t not in names and len(t) <= 60 and "\n" not in t and "is also in" not in t \
                and not re.match(r"^[\d:/\s.,APMapm]+$", t):
            names.append(t)
    if not names:
        page.keyboard.press("Escape")
        return None, f"'{name}' naam ka koi chat nahi mila."
    key = name.lower().strip()
    best = (next((n for n in names if n.lower() == key), None)
            or next((n for n in names if n.lower().startswith(key)), None)
            or next((n for n in names if key in n.lower()), None))
    if not best:
        page.keyboard.press("Escape")
        return None, f"'{name}' se exact chat nahi mila. Milte-julte: {names[:5]}"
    page.locator("#pane-side span[title]").filter(has_text=best).first.click()
    if not _first_visible(page, COMPOSE_BOX, timeout=10):
        return None, f"'{best}' ka chat khula nahi."
    return best, None


def _open_chat_by_number(page, number: str):
    page.goto(f"{WHATSAPP_URL}/send?phone={number}", wait_until="domcontentloaded")
    deadline = time.time() + 45
    while time.time() < deadline:
        if _first_visible(page, COMPOSE_BOX, timeout=0.5):
            return f"+{number}", None
        dialog = page.locator('[role="dialog"]')
        if dialog.count() and "invalid" in (dialog.first.inner_text() or "").lower():
            return None, f"+{number} WhatsApp pe nahi hai (invalid number)."
        time.sleep(0.5)
    return None, "Chat 45 second me nahi khula."


# Har text message pe WhatsApp likhta hai: data-pre-plain-text="[2:08 PM, 10/3/2026] Naam: "
MESSAGE = "#main [data-pre-plain-text]"


def _bubbles_containing(page, snippet: str) -> int:
    return page.evaluate(
        "(s) => [...document.querySelectorAll('#main [data-pre-plain-text]')].filter(e => e.innerText.includes(s)).length",
        snippet,
    )


def _plain_snippet(message: str) -> str:
    """Message ka shuru wala saada hissa (emoji WhatsApp me image ban jaate hain, text me match nahi hote)."""
    match = re.match(r"[\w\s,.'!?-]{3,}", message.strip())
    return (match.group(0) if match else message.strip())[:20].strip()


@_resilient
def whatsapp_message(to: str, message: str, send: bool, number: str | None = None) -> str:
    """Chat kholo, message likho, aur send=True ho to bhejo + check karo ki sach me gaya."""
    page, err = _whatsapp_ready()
    if err:
        return err
    chat, err = _open_chat_by_number(page, number) if number else _open_chat_by_name(page, to)
    if err:
        return err

    box = _first_visible(page, COMPOSE_BOX, timeout=10)
    if box is None:
        return "Chat khula par message box nahi mila. Kuch nahi bheja."
    box.click()
    page.keyboard.press("Control+A")
    page.keyboard.press("Backspace")
    lines = message.split("\n")
    for i, line in enumerate(lines):  # Enter = send hota hai, isliye nayi line ke liye Shift+Enter
        page.keyboard.insert_text(line)
        if i < len(lines) - 1:
            page.keyboard.press("Shift+Enter")
    time.sleep(0.5)
    if message.strip()[:15] not in (box.inner_text() or ""):
        return "Message box me text nahi likha gaya, kuch gadbad hui. Kuch nahi bheja."
    if not send:
        return f"'{chat}' ke chat me message likh diya hai (bheja NAHI). User khud dekh ke Enter daba sakta hai."

    snippet = _plain_snippet(message)
    before = _bubbles_containing(page, snippet)
    page.keyboard.press("Enter")
    deadline = time.time() + 15
    while time.time() < deadline:
        if _bubbles_containing(page, snippet) > before and not (box.inner_text() or "").strip():
            return f"'{chat}' ko message chala gaya ✓ (WhatsApp chat me dikh raha hai)."
        time.sleep(0.5)
    return f"Enter dabaya par confirm nahi ho paya ki '{chat}' ko message gaya. User screen pe check kare."


@_resilient
def whatsapp_read(name: str, count: int) -> str:
    """Kisi chat ke last messages padho."""
    page, err = _whatsapp_ready()
    if err:
        return err
    chat, err = _open_chat_by_name(page, name)
    if err:
        return err
    time.sleep(2)
    msgs = page.locator(MESSAGE)
    total = msgs.count()
    out = []
    for i in range(max(0, total - count), total):
        m = msgs.nth(i)
        header = m.get_attribute("data-pre-plain-text") or ""  # "[2:08 PM, 10/3/2026] Naam: "
        when, _, who = header.partition("] ")
        out.append(f"{when.strip('[ ')} | {who.strip().rstrip(':')}: {m.inner_text().strip()}")
    if not out:
        return f"'{chat}' me koi text message nahi dikha."
    return f"'{chat}' ke last {len(out)} messages (time | kisne bheja: kya):\n" + "\n".join(out)


# ======================= Websites =======================

def _page_text(page, limit: int = 6000) -> str:
    try:
        text = page.locator("body").inner_text(timeout=5000)
    except Exception:
        text = ""
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    return f"[{page.title()}] {page.url}\n{text[:limit]}"


KEEP_TABS = ("web.whatsapp.com", "music.youtube.com")  # in tabs ko browsing ke liye mat chhedo (WhatsApp, gaana)


def _current_page():
    ctx = _context()
    pages = [p for p in ctx.pages if not any(k in p.url for k in KEEP_TABS)] or [ctx.new_page()]
    page = pages[-1]
    page.bring_to_front()
    return page


@_resilient
def browse_open(url: str) -> str:
    """JARVIS ke browser me website kholo aur uska text padho (padhne, dhoondhne, form bharne jaise kaam ke liye).

    Args:
        url: Poora URL, e.g. 'https://www.pw.live'.
    """
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    page = _current_page()
    page.goto(url, wait_until="domcontentloaded", timeout=45000)
    time.sleep(2)
    return _page_text(page, 4000)


@_resilient
def browse_read() -> str:
    """JARVIS ke browser me abhi jo page khula hai uska text dobara padho (click/scroll ke baad)."""
    return _page_text(_current_page(), 4000)


@_resilient
def browse_click(text: str) -> str:
    """JARVIS ke browser me us link/button pe click karo jispe ye text likha hai.

    Args:
        text: Button/link pe likha text, e.g. 'Login' ya 'Next'.
    """
    page = _current_page()
    for loc in (page.get_by_role("button", name=text), page.get_by_role("link", name=text), page.get_by_text(text)):
        try:
            if loc.count():
                loc.first.click(timeout=5000)
                time.sleep(2)
                return "Click kiya.\n" + _page_text(page, 3000)
        except Exception:
            continue
    return f"'{text}' wala button/link nahi mila."


@_resilient
def browse_type(field: str, text: str, press_enter: bool) -> str:
    """JARVIS ke browser me kisi box me likho (search box, form field).

    Args:
        field: Box ka label/placeholder, e.g. 'Search' ya 'Email'.
        text: Kya likhna hai.
        press_enter: Likhne ke baad Enter dabana hai ya nahi.
    """
    page = _current_page()
    for loc in (page.get_by_label(field), page.get_by_placeholder(field), page.get_by_role("searchbox"), page.get_by_role("textbox", name=field)):
        try:
            if loc.count() and loc.first.is_visible():
                loc.first.fill(text, timeout=5000)
                if press_enter:
                    loc.first.press("Enter")
                    time.sleep(3)
                return "Likh diya.\n" + _page_text(page, 3000)
        except Exception:
            continue
    return f"'{field}' naam ka box nahi mila."


# ======================= Music =======================

@_resilient
def play_music(query: str) -> str:
    """YouTube Music pe gaana chalao (JARVIS ke browser me) aur check karo ki sach me baj raha hai.
    Rokna/agla gaana: media_control. Volume: set_volume.

    Args:
        query: Gaane/artist/mood ka naam, jaise 'Arijit Singh sad songs', 'lofi study music'.
    """
    page = _page("music.youtube.com")
    page.goto("https://music.youtube.com/search?q=" + quote_plus(query), wait_until="domcontentloaded", timeout=45000)
    target, deadline = None, time.time() + 15
    while target is None and time.time() < deadline:
        top = page.locator("ytmusic-card-shelf-renderer ytmusic-play-button-renderer")  # "Top result" ka play button
        if top.count() and top.first.is_visible():
            target = top.first
            break
        links = page.locator("ytmusic-responsive-list-item-renderer .title-column a")
        for i in range(min(links.count(), 12)):
            if links.nth(i).is_visible() and links.nth(i).inner_text().strip():
                target = links.nth(i)
                break
        time.sleep(0.5)
    if target is None:
        return f"YouTube Music pe '{query}' ka koi gaana nahi mila."
    target.click()
    for _ in range(30):  # 15 sec tak dekho ki sach me baj raha hai
        state = page.evaluate("""() => { const v = document.querySelector('video');
            const m = navigator.mediaSession && navigator.mediaSession.metadata;
            return {playing: !!v && !v.paused && v.currentTime > 0.3, title: m ? m.title : '', artist: m ? m.artist : ''}; }""")
        if state["playing"]:
            return f"Baj raha hai ✓: {state['title']} - {state['artist']}".strip(" -")
        time.sleep(0.5)
    return "Gaana click kiya par bajna confirm nahi hua (shayad ad ya page slow hai) - user ek baar dekh le."


TOOLS = [browse_open, browse_read, browse_click, browse_type, play_music]


if __name__ == "__main__":
    # WhatsApp Login.bat: JARVIS ke browser me WhatsApp kholo aur QR scan hone tak ruko (sirf ek baar)
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    page = _page("web.whatsapp.com")
    page.goto(WHATSAPP_URL, wait_until="domcontentloaded")
    print("JARVIS ki Edge window me WhatsApp khula hai.")
    print("Phone me: WhatsApp > Settings > Linked devices > Link a device > QR scan karo.")
    deadline = time.time() + 600
    while time.time() < deadline:
        if page.locator("#pane-side").count():
            print("\nWhatsApp login ho gaya ✓  Ab JARVIS WhatsApp chala sakta hai. (ye window band kar sakte ho)")
            break
        time.sleep(1)
    else:
        print("\n10 minute me login nahi hua. Dobara chalao.")
    time.sleep(3)
    close()
