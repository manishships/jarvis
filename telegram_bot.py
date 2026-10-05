"""Phone se JARVIS: Telegram bot (laptop pe JARVIS chal raha ho tab).

- Sirf owner (tumhara Telegram) se baat karta hai. Pehli baar laptop ki HUD pe 6 digit ka code dikhta hai - woh bot ko bhejo.
- Text = JARVIS se baat / laptop pe kaam. Photo = question solve / samjhao. Reminders aur alerts phone pe bhi aate hain.
"""

import json
import logging
import queue
import secrets
import time
import urllib.error
import urllib.request

log = logging.getLogger("jarvis")


class TelegramBot:
    def __init__(self, token: str, owner_id: int | None, on_text, on_photo, on_paired, on_voice=None):
        self.token = token
        self.owner_id = owner_id
        self.on_text, self.on_photo, self.on_paired, self.on_voice = on_text, on_photo, on_paired, on_voice
        self.pair_code = None if owner_id else f"{secrets.randbelow(900000) + 100000}"
        self.bad_codes = 0  # galat pairing code ki ginti (5 ke baad pairing band, JARVIS restart pe naya code)
        self.offset = 0
        self._waiter = None  # confirm ke time pe jawab yahan aata hai
        self.alive = True

    # ---------- Telegram API ----------
    def _call(self, method: str, http_timeout: float = 20, **params):
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{self.token}/{method}",
            data=json.dumps(params).encode(), headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=http_timeout) as r:
            data = json.load(r)
        if not data.get("ok"):
            raise RuntimeError(data)
        return data["result"]

    def _download(self, file_id: str) -> bytes:
        path = self._call("getFile", file_id=file_id)["file_path"]
        with urllib.request.urlopen(f"https://api.telegram.org/file/bot{self.token}/{path}", timeout=30) as r:
            return r.read()

    def send(self, text: str) -> None:
        if not self.owner_id or not text:
            return
        for i in range(0, len(text), 4000):  # Telegram ki 4096 char limit
            try:
                self._call("sendMessage", chat_id=self.owner_id, text=text[i:i + 4000])
            except Exception:
                log.exception("Telegram send failed")

    def _upload(self, method: str, field: str, filename: str, data: bytes, mime: str, caption: str = "") -> None:
        """Photo/file bhejo (multipart upload)."""
        import uuid

        boundary = uuid.uuid4().hex
        parts = []
        for name, value in (("chat_id", str(self.owner_id)), ("caption", caption[:1000])):
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'
                     f"Content-Type: {mime}\r\n\r\n".encode() + data + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        req = urllib.request.Request(f"https://api.telegram.org/bot{self.token}/{method}", data=b"".join(parts),
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        with urllib.request.urlopen(req, timeout=60) as r:
            if not json.load(r).get("ok"):
                raise RuntimeError(f"Telegram {method} failed")

    def send_photo(self, data: bytes, caption: str = "") -> None:
        if self.owner_id:
            self._upload("sendPhoto", "photo", "screen.jpg", data, "image/jpeg", caption)

    def send_document(self, path: str, caption: str = "") -> None:
        import mimetypes
        from pathlib import Path

        if self.owner_id:
            p = Path(path)
            self._upload("sendDocument", "document", p.name, p.read_bytes(),
                         mimetypes.guess_type(p.name)[0] or "application/octet-stream", caption)

    def typing(self) -> None:
        try:
            self._call("sendChatAction", chat_id=self.owner_id, action="typing")
        except Exception:
            pass

    def ask(self, question: str, timeout: float = 120) -> str | None:
        """Phone pe sawaal bhejo aur jawab ka intezaar karo (confirm ke liye)."""
        self._waiter = queue.Queue()
        self.send(question)
        try:
            return self._waiter.get(timeout=timeout)
        except queue.Empty:
            self.send("2 minute me jawab nahi aaya, isliye cancel kar diya.")
            return None
        finally:
            self._waiter = None

    # ---------- Main loop (apne thread me) ----------
    def check_token(self) -> str:
        return self._call("getMe")["username"]

    def run(self) -> None:
        while self.alive:
            try:
                updates = self._call("getUpdates", http_timeout=40, offset=self.offset, timeout=30)
            except urllib.error.HTTPError as e:
                if e.code in (401, 404):
                    log.error("Telegram token galat hai - bot band")
                    return
                time.sleep(5)
                continue
            except Exception:
                time.sleep(5)  # internet gaya - thodi der baad phir
                continue
            for update in updates:
                self.offset = update["update_id"] + 1
                try:
                    self._handle(update.get("message") or {})
                except Exception:
                    log.exception("Telegram update handle failed")

    def _handle(self, msg: dict) -> None:
        chat_id = (msg.get("chat") or {}).get("id")
        text = (msg.get("text") or msg.get("caption") or "").strip()
        if not chat_id:
            return

        if self.owner_id is None:  # pairing
            code = text.replace("/start", "").strip()
            if self.pair_code and code == self.pair_code:
                self.owner_id, self.pair_code = chat_id, None
                self.on_paired(chat_id)
                self.send("✅ Pairing ho gayi! Main JARVIS hoon - ab yahan se mujhse baat karo, kaam bolo, "
                          "ya kisi question ki photo bhejo. (Laptop pe JARVIS chalu hona chahiye.)")
            else:
                if self.pair_code and code:
                    self.bad_codes += 1
                    if self.bad_codes >= 5:
                        self.pair_code = None
                        log.warning("Telegram: 5 galat pairing code - pairing band (JARVIS restart karo)")
                self._reply(chat_id, "🔒 Ye JARVIS private hai. Laptop pe HUD me jo 6 digit ka pairing code dikh raha hai, woh bhejo.")
            return

        if chat_id != self.owner_id:
            self._reply(chat_id, "🔒 Ye JARVIS private hai.")
            log.warning("Telegram: anjaan chat %s ne message bheja", chat_id)
            return

        if self._waiter is not None and text:
            self._waiter.put(text)
            return
        if text == "/start":
            self.send("JARVIS online hai, Boss. Bolo kya karna hai?")
            return
        document = msg.get("document") or {}
        voice = msg.get("voice") or msg.get("audio")
        if msg.get("photo"):
            self.typing()
            self.on_photo(self._download(msg["photo"][-1]["file_id"]), text)
        elif (document.get("mime_type") or "").startswith("image/"):  # photo "file" bana ke bheji
            self.typing()
            self.on_photo(self._download(document["file_id"]), text)
        elif voice and self.on_voice:
            self.typing()
            self.on_voice(self._download(voice["file_id"]), voice.get("mime_type") or "audio/ogg")
        elif text:
            self.typing()
            self.on_text(text)
        else:
            self.send("Ye wali cheez main abhi nahi samajhta. Text, photo ya voice note bhejo.")

    def _reply(self, chat_id: int, text: str) -> None:
        try:
            self._call("sendMessage", chat_id=chat_id, text=text)
        except Exception:
            pass
