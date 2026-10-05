"""JARVIS ka dimaag. Teen options, sabka kaam same: ask(text, image) -> jawab.

- GeminiBrain: free (default). Busy ho to kai Gemini models baari-baari try karta hai.
- GroqBrain:   free backup (Gemini fail ho tab). Chhota prompt + zaroori tools (Groq ki limit 8000 tokens/minute).
- ClaudeBrain: paid, sabse smart (config.BRAIN = "claude").

Niyam: agar beech me koi KAAM wala tool chal chuka ho (message bheja, app khola...), to dobara retry nahi - warna
woh kaam do baar ho jata. Sirf padhne wale tools (mausam, battery...) ke baad retry safe hai.
"""

import functools
import json
import time
import urllib.error
import urllib.request


def image_mime(data: bytes) -> str:
    if data[1:4] == b"PNG":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


READ_ONLY_TOOLS = {  # ye sirf jaankari padhte hain - dobara chalane me koi nuksaan nahi
    "get_weather", "list_reminders", "system_status", "study_report", "flashcard_stats", "search_memory", "list_facts",
    "list_contacts", "screen_time_report", "quiz_next", "read_clipboard", "screen_controls", "look_at_screen",
    "browse_read", "find_files", "web_search", "news_headlines", "youtube_lecture", "read_whatsapp", "list_protocols",
    "run_protocol", "backlog_status", "study_plan", "today_plan", "mistake_report", "practice_set",
}


class BrainError(Exception):
    """User ko dikhane layak error (limit khatam, key galat, internet nahi...)."""


class _ToolTracker:
    """Ek turn me kaun se tools chale - taaki fail hone pe pata ho ki retry safe hai ya nahi."""

    def __init__(self):
        self.ran: list[tuple[str, str]] = []

    def wrap(self, fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            result = fn(*args, **kwargs)
            self.ran.append((fn.__name__, str(result)[:300]))
            return result
        return wrapper

    def side_effects_message(self) -> str | None:
        done = [(n, r) for n, r in self.ran if n not in READ_ONLY_TOOLS and not r.startswith("Error")]
        if not done:
            return None
        return "Server beech me busy ho gaya. Tab tak ka haal: " + "; ".join(
            f"{n.replace('_', ' ')} → {r[:100]}" for n, r in done)


# ======================= Gemini (free, default) =======================

class GeminiBrain:
    TIMEOUT_MS = 18_000
    BACKOFF = [0, 1.5, 3]        # 3 try (alag models), phir backup (Groq) - zyada intezaar nahi
    MAX_HISTORY = 60             # itni entries ke baad purani baatein hata do (tez + limit bachao)
    KEEP_HISTORY = 30

    def __init__(self, model: str, system: str, tools: list, backup_models: tuple = ()):
        from google import genai
        from google.genai import types

        self.models = list(dict.fromkeys([model, *backup_models]))
        self.model = model
        self.client = genai.Client(http_options=types.HttpOptions(timeout=self.TIMEOUT_MS))  # GEMINI_API_KEY env se
        self.tracker = _ToolTracker()
        # Google Search grounding free key pe allowed nahi (429 deta hai), isliye internet ke liye web_search tool hai
        self.config = types.GenerateContentConfig(system_instruction=system, tools=[self.tracker.wrap(t) for t in tools])
        self.chat = self.client.chats.create(model=model, config=self.config)

    def _use_model(self, model: str):
        if model != self.model:
            print(f"   (JARVIS: '{self.model}' busy hai, '{model}' try kar raha hoon)")
            self.chat = self.client.chats.create(model=model, config=self.config, history=self.chat.get_history())
            self.model = model

    def _trim_history(self):
        """Lambi baatcheet me sirf pichli ~30 entries rakho (user ke kisi saaf message se shuru karke)."""
        history = self.chat.get_history()
        if len(history) <= self.MAX_HISTORY:
            return
        for i in range(len(history) - self.KEEP_HISTORY, len(history)):
            content = history[i]
            if content.role == "user" and content.parts and getattr(content.parts[0], "text", None):
                self.chat = self.client.chats.create(model=self.model, config=self.config, history=history[i:])
                return

    def see(self, image: bytes, question: str) -> str:
        """Photo/screenshot dekh ke jawab (alag request, chat history me nahi judta)."""
        from google.genai import types

        part = types.Part.from_bytes(data=image, mime_type=image_mime(image))
        last_error = None
        for model in self.models:
            try:
                return self.client.models.generate_content(model=model, contents=[part, question]).text or ""
            except Exception as e:
                last_error = e
        return f"Dekh nahi paya: {last_error}"

    def transcribe(self, audio: bytes, mime: str) -> str | None:
        """Voice note -> text (Gemini audio samajhta hai)."""
        from google.genai import types

        part = types.Part.from_bytes(data=audio, mime_type=mime)
        prompt = ("Is voice note me jo bola gaya hai use exactly likh do. Hindi/Hinglish ho to Roman Hinglish me likho. "
                  "Sirf transcript do, aur kuch nahi.")
        for model in self.models:
            try:
                return (self.client.models.generate_content(model=model, contents=[part, prompt]).text or "").strip()
            except Exception:
                continue
        return None

    def ask(self, text: str, image: bytes | None = None) -> str:
        from google.genai import errors, types

        message = [types.Part.from_bytes(data=image, mime_type=image_mime(image)), text] if image else text
        order = [self.model] + [m for m in self.models if m != self.model]
        last_problem = "busy"
        for attempt, wait in enumerate(self.BACKOFF):
            time.sleep(wait)
            self._use_model(order[attempt % len(order)])
            self.tracker.ran = []
            try:
                reply = self.chat.send_message(message).text or ""
                self._trim_history()
                return reply
            except errors.ClientError as e:
                if e.code in (401, 403) or "API_KEY_INVALID" in str(e):
                    raise BrainError("Gemini API key galat hai ya set nahi hai. keys.env file check karo.")
                if e.code not in (429, 404):
                    raise BrainError(f"Gemini error: {e}")
                last_problem = "limit" if e.code == 429 else "busy"
            except Exception as e:  # 5xx busy, timeout, internet
                last_problem = "busy"
                if "timeout" in type(e).__name__.lower() or "timed out" in str(e).lower():
                    done = self.tracker.side_effects_message()
                    if done:
                        return done
                    raise BrainError("Gemini bahut slow hai (timeout).") from None  # aur intezaar nahi - seedha backup
            done = self.tracker.side_effects_message()
            if done:
                return done
        if last_problem == "limit":
            raise BrainError("Gemini ki free limit abhi khatam ho gayi.")
        raise BrainError("Google ke free servers abhi bahut busy hain.")


# ======================= Groq (free backup) =======================

GROQ_TOOL_NAMES = {  # Groq ki limit chhoti hai (8000 tokens/minute), isliye sirf zaroori tools
    "set_reminder", "set_timer", "list_reminders", "cancel_reminder", "remember", "list_facts", "get_weather",
    "system_status", "web_search", "news_headlines", "open_app", "open_website", "set_volume", "set_brightness",
    "media_control", "play_music", "start_study", "stop_study", "quiz_next", "quiz_grade", "add_flashcards",
    "run_protocol", "write_document", "set_voice", "set_silent_mode", "send_to_phone",
    "today_plan", "lectures_done", "log_mistake",
}
GROQ_FALLBACK_MODELS = ("openai/gpt-oss-20b", "qwen/qwen3.8-27b")  # har model ki limit alag - ek bhara to doosra


class GroqBrain:
    """Gemini busy ho to backup. Bina chat history ke chalta hai - har baar DB se pichli kuch baatein leta hai."""

    URL = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self, key: str, model: str, system: str, tools: list, facts=lambda: ""):
        from anthropic import beta_tool  # sirf tool ka JSON schema banane ke liye

        self.key, self.system, self.facts = key, system, facts
        self.models = list(dict.fromkeys([model, *GROQ_FALLBACK_MODELS]))
        self.model = model
        self.funcs = {t.__name__: t for t in tools if t.__name__ in GROQ_TOOL_NAMES}
        self.tools = []
        for fn in self.funcs.values():
            spec = beta_tool(fn).to_dict()
            self.tools.append({"type": "function", "function": {
                "name": spec["name"], "description": spec["description"][:220], "parameters": spec["input_schema"]}})
        self.tracker = _ToolTracker()

    def _post(self, body: dict) -> dict:
        """Ek model bhara (429) ya kharab ho to agla model try karo."""
        last = None
        for model in [self.model] + [m for m in self.models if m != self.model]:
            body["model"] = model
            if "gpt-oss" in model:
                body["reasoning_effort"] = "low"
            else:
                body.pop("reasoning_effort", None)
            req = urllib.request.Request(self.URL, data=json.dumps(body).encode(), headers={
                "Authorization": f"Bearer {self.key}", "Content-Type": "application/json", "User-Agent": "JARVIS"})
            try:
                with urllib.request.urlopen(req, timeout=40) as r:
                    return json.load(r)
            except urllib.error.HTTPError as e:
                last = f"Groq error {e.code}"
                if e.code in (401, 403):
                    raise BrainError("Groq key galat hai - keys.env check karo.") from None
                continue  # 429 limit / 413 bada / 5xx - agla model
            except Exception as e:
                last = f"Groq tak nahi pahunch paya: {e}"
                break
        raise BrainError(last or "Groq error")

    def ask(self, text: str, history: list[tuple[str, str]] = (), image: bytes | None = None) -> str:
        if image:
            return "Photo abhi nahi dekh pa raha (backup dimaag chal raha hai) - 1-2 minute baad dobara bhejo."
        system = self.system + ("\n\nUser ke baare me:\n" + self.facts()[:1200] if self.facts() else "")
        messages = [{"role": "system", "content": system}]
        messages += [{"role": "assistant" if role == "jarvis" else "user", "content": content[:500]} for role, content in history]
        messages.append({"role": "user", "content": text})
        self.tracker.ran = []
        for _ in range(6):  # tool -> jawab -> tool ... zyada se zyada 6 chakkar
            body = {"messages": messages, "tools": self.tools, "temperature": 0.6}
            try:
                msg = self._post(body)["choices"][0]["message"]
            except BrainError:
                done = self.tracker.side_effects_message()
                if done:
                    return done
                raise
            calls = msg.get("tool_calls") or []
            if not calls:
                return (msg.get("content") or "").strip()
            messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
            for call in calls:
                name = call["function"]["name"]
                try:
                    args = json.loads(call["function"].get("arguments") or "{}")
                    result = str(self.tracker.wrap(self.funcs[name])(**args)) if name in self.funcs else f"Error: '{name}' tool nahi hai"
                except Exception as e:
                    result = f"Error: {e}"
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": result[:1500]})
        return "Ye kaam thoda lamba ho gaya - ek baar phir se bolo."


# ======================= Claude (paid, sabse smart) =======================

class ClaudeBrain:
    def __init__(self, model: str, system: str, tools: list):
        import anthropic
        from anthropic import beta_tool

        self._anthropic = anthropic
        self.client = anthropic.Anthropic()  # ANTHROPIC_API_KEY env variable se key leta hai
        self.model = model
        self.system = system
        # Claude ka apna (behtar) web search hai, isliye free wala web_search tool hata do
        self.tools = [beta_tool(t) for t in tools if t.__name__ != "web_search"]
        self.tools.append({"type": "web_search_20260209", "name": "web_search", "max_uses": 3})
        self.messages = []  # sirf append hota hai, kabhi edit nahi

    def see(self, image: bytes, question: str) -> str:
        import base64

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4000,
                output_config={"effort": "low"},
                messages=[{"role": "user", "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": image_mime(image),
                                                 "data": base64.standard_b64encode(image).decode()}},
                    {"type": "text", "text": question},
                ]}],
            )
        except self._anthropic.APIError as e:
            return f"Dekh nahi paya: {e}"
        return "".join(b.text for b in response.content if b.type == "text")

    def transcribe(self, audio: bytes, mime: str) -> str | None:
        return None  # Claude audio nahi sunta - voice note ke liye Gemini/Groq chahiye

    def ask(self, text: str, image: bytes | None = None) -> str:
        import base64

        anthropic = self._anthropic
        turn_start = len(self.messages)
        content = text
        if image:
            content = [{"type": "image", "source": {"type": "base64", "media_type": image_mime(image),
                                                    "data": base64.standard_b64encode(image).decode()}},
                       {"type": "text", "text": text}]
        self.messages.append({"role": "user", "content": content})
        try:
            for _ in range(5):  # pause_turn aaye (lamba web search) to aage continue karo
                runner = self.client.beta.messages.tool_runner(
                    model=self.model,
                    max_tokens=16000,
                    system=self.system,
                    tools=self.tools,
                    messages=self.messages,
                    output_config={"effort": "medium"},
                    cache_control={"type": "ephemeral"},
                    betas=["server-side-fallback-2026-07-01"],
                    fallbacks="default",
                )
                last = None
                for message in runner:
                    last = message
                    self.messages.append({"role": "assistant", "content": message.content})
                    tool_response = runner.generate_tool_call_response()
                    if tool_response is not None:
                        self.messages.append(tool_response)
                if last is None or last.stop_reason != "pause_turn":
                    break
        except anthropic.AuthenticationError:
            del self.messages[turn_start:]
            raise BrainError("Claude API key galat hai ya set nahi hai. keys.env file check karo.")
        except anthropic.RateLimitError:
            del self.messages[turn_start:]
            raise BrainError("Thoda rush hai, ek minute baad try karo.")
        except anthropic.APIConnectionError:
            del self.messages[turn_start:]
            raise BrainError("Internet check karo, connect nahi ho pa raha.")
        except anthropic.APIStatusError as e:
            del self.messages[turn_start:]
            raise BrainError(f"Claude error ({e.status_code}): {e.message}")

        if last is None:
            return ""
        if last.stop_reason == "refusal":
            return "Is baare me main help nahi kar paunga. Kuch aur poochho?"
        return "".join(b.text for b in last.content if b.type == "text")
