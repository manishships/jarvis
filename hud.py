"""Iron Man style HUD: ghoomta arc reactor + JARVIS ki halat (so raha / sun raha / soch raha / bol raha) + baatcheet + system stats.

Tkinter sirf main thread me chalta hai, isliye baaki threads `hud.post(...)` se queue me message daalte hain.
"""

import math
import queue
import time
import tkinter as tk
from datetime import datetime

import psutil

BG = "#05080d"
CYAN = "#33d6ff"
DIM = "#0e3a4a"
TEXT = "#bfefff"
STATES = {
    "sleeping": ("STANDBY", "#1f6f8b", 0.4),
    "listening": ("LISTENING", "#33ff99", 2.2),
    "thinking": ("PROCESSING", "#ffcc33", 3.5),
    "speaking": ("SPEAKING", "#33d6ff", 1.6),
    "working": ("EXECUTING", "#ff7a33", 3.0),
}


class HUD:
    def __init__(self, title: str, on_text, level=None, status=None, hint="'Hey Jarvis' bolo  •  Ctrl+Alt+J  •  ya yahan likho",
                 on_hand=None):
        self.on_text = on_text  # user ne box me kuch likha -> callback(text)
        self.level = level or (lambda: 0.0)  # JARVIS ki aawaz ka loudness (reactor isse dhadakta hai)
        self.status = status or (lambda: "")  # "📚 Physics 32m · 🃏 5 due · 🔕" jaisi chhoti line
        self.voice_glow = 0.0
        self.events = queue.Queue()
        self.state = "sleeping"
        self.angle = 0.0
        self.pulse = 0.0
        self.stats = ""
        self.last_stats = 0.0

        self.root = tk.Tk()
        self.root.title(title)
        self.root.configure(bg=BG)
        screen_h = self.root.winfo_screenheight()
        height = min(720, screen_h - 110)  # taskbar ke peeche na chhupe
        self.size = 300 if height >= 680 else 220  # chhoti screen pe chhota reactor
        self.k = self.size / 300
        self.root.geometry(f"440x{height}+30+20")
        self.root.minsize(360, 480)
        self.root.attributes("-topmost", True)

        top = tk.Frame(self.root, bg=BG)
        top.pack(fill="x", padx=14, pady=(10, 0))
        tk.Label(top, text="J.A.R.V.I.S.", fg=CYAN, bg=BG, font=("Consolas", 18, "bold")).pack(side="left")
        self.pin = tk.Button(top, text="📌", command=self._toggle_top, bg=BG, fg=TEXT, bd=0, activebackground=DIM)
        self.pin.pack(side="right")
        if on_hand:  # 🖐 = haath ke ishaare (webcam) on/off
            tk.Button(top, text="🖐", command=on_hand, bg=BG, fg=TEXT, bd=0, activebackground=DIM).pack(side="right", padx=(0, 4))
        self.clock = tk.Label(top, fg=TEXT, bg=BG, font=("Consolas", 11))
        self.clock.pack(side="right", padx=8)

        self.canvas = tk.Canvas(self.root, width=self.size, height=self.size, bg=BG, highlightthickness=0)
        self.canvas.pack(pady=(6, 0))
        self.state_label = tk.Label(self.root, fg=CYAN, bg=BG, font=("Consolas", 13, "bold"))
        self.state_label.pack()
        self.stats_label = tk.Label(self.root, fg="#5fa8bf", bg=BG, font=("Consolas", 9))
        self.stats_label.pack(pady=(2, 0))
        self.status_label = tk.Label(self.root, fg="#ffcc33", bg=BG, font=("Segoe UI", 9))
        self.status_label.pack(pady=(0, 6))

        # Neeche wale hisse pehle pack karo, taaki chhoti screen pe type box kabhi na chhupe
        tk.Label(self.root, text=hint, fg="#3f6f7f", bg=BG,
                 font=("Consolas", 8)).pack(side="bottom", pady=(0, 6))
        bottom = tk.Frame(self.root, bg=BG)
        bottom.pack(side="bottom", fill="x", padx=14, pady=(8, 4))
        self.entry = tk.Entry(bottom, bg="#071119", fg=TEXT, insertbackground=CYAN, bd=0, font=("Segoe UI", 11),
                              highlightthickness=1, highlightbackground=DIM, highlightcolor=CYAN)
        self.entry.pack(side="left", fill="x", expand=True, ipady=6)
        self.entry.bind("<Return>", self._submit)
        tk.Button(bottom, text="➤", command=self._submit, bg=DIM, fg=CYAN, bd=0, width=4,
                  activebackground=CYAN).pack(side="left", padx=(6, 0), ipady=4)

        self.log = tk.Text(self.root, bg="#071119", fg=TEXT, bd=0, wrap="word", font=("Segoe UI", 10), height=6,
                           highlightthickness=1, highlightbackground=DIM, padx=8, pady=6)
        self.log.pack(fill="both", expand=True, padx=14)
        self.log.tag_configure("you", foreground="#33ff99", font=("Segoe UI", 10, "bold"))
        self.log.tag_configure("jarvis", foreground=CYAN, font=("Segoe UI", 10, "bold"))
        self.log.tag_configure("info", foreground="#5f7f8f", font=("Segoe UI", 9, "italic"))
        self.log.configure(state="disabled")

        self.root.after(30, self._tick)

    # ---- dusre threads se (thread-safe) ----
    def post(self, kind: str, *args):
        self.events.put((kind, args))

    def set_state(self, state: str):
        self.post("state", state)

    def say(self, who: str, text: str):
        self.post("line", who, text)

    def close(self):
        self.post("quit")

    # ---- main thread ----
    def run(self):
        self.root.mainloop()

    def _toggle_top(self):
        on = not self.root.attributes("-topmost")
        self.root.attributes("-topmost", on)
        self.pin.configure(fg=TEXT if on else "#3f6f7f")

    def _submit(self, _event=None):
        text = self.entry.get().strip()
        if text:
            self.entry.delete(0, "end")
            self.on_text(text)

    def _append(self, who: str, text: str):
        self.log.configure(state="normal")
        tag = "you" if who.startswith(("Tum", "You")) else "jarvis" if who == "JARVIS" else "info"
        if tag == "info":
            self.log.insert("end", f"{text}\n", "info")
        else:
            self.log.insert("end", f"{who}: ", tag)
            self.log.insert("end", f"{text}\n\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _tick(self):
        while not self.events.empty():
            kind, args = self.events.get_nowait()
            if kind == "state":
                self.state = args[0]
            elif kind == "line":
                self._append(*args)
            elif kind == "quit":
                self.root.destroy()
                return
        now = time.time()
        if now - self.last_stats > 3:
            b = psutil.sensors_battery()
            bat = f"BAT {b.percent:.0f}%{' ⚡' if b.power_plugged else ''}" if b else "BAT --"
            self.stats = f"{bat}   CPU {psutil.cpu_percent():.0f}%   RAM {psutil.virtual_memory().percent:.0f}%"
            self.stats_label.configure(text=self.stats)
            try:
                self.status_label.configure(text=self.status())
            except Exception:
                pass
            self.clock.configure(text=datetime.now().strftime("%a %d %b  %H:%M"))
            self.last_stats = now
        self._draw()
        self.root.after(33, self._tick)

    def _draw(self):
        label, color, speed = STATES.get(self.state, STATES["sleeping"])
        self.state_label.configure(text=f"◉ {label}", fg=color)
        self.angle = (self.angle + speed * 2) % 360
        self.pulse += 0.12 * speed
        glow = (math.sin(self.pulse) + 1) / 2  # 0..1
        if self.state == "speaking":  # bolte waqt asli aawaz ke saath dhadko
            self.voice_glow = max(self.level(), self.voice_glow * 0.75)
            glow = 0.2 + self.voice_glow * 1.6

        c, k = self.canvas, self.k
        cx = cy = self.size / 2
        c.delete("all")
        # bahar ke ghoomte arcs
        for r, width, start, extent, direction in ((135, 3, 0, 70, 1), (135, 3, 180, 70, 1), (118, 2, 90, 50, -1),
                                                    (118, 2, 270, 50, -1), (102, 6, 30, 120, 1), (102, 6, 210, 120, 1)):
            a = (start + direction * self.angle) % 360
            r *= k
            c.create_arc(cx - r, cy - r, cx + r, cy + r, start=a, extent=extent, style="arc", outline=color, width=width)
        # ticks ka ghera
        for i in range(36):
            t = math.radians(i * 10 - self.angle / 3)
            r1, r2 = 84 * k, (90 if i % 3 else 95) * k
            c.create_line(cx + r1 * math.cos(t), cy + r1 * math.sin(t), cx + r2 * math.cos(t), cy + r2 * math.sin(t),
                          fill=DIM if i % 3 else color, width=2)
        # arc reactor ke 10 segment
        for i in range(10):
            a = i * 36 + self.angle / 4
            c.create_arc(cx - 70 * k, cy - 70 * k, cx + 70 * k, cy + 70 * k, start=a, extent=24, style="arc", outline=color, width=10 * k)
        # beech ka glow
        rr = (34 + glow * 8) * k
        c.create_oval(cx - rr - 10 * k, cy - rr - 10 * k, cx + rr + 10 * k, cy + rr + 10 * k, outline=DIM, width=2)
        c.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, fill=color, outline="")
        c.create_oval(cx - 16 * k, cy - 16 * k, cx + 16 * k, cy + 16 * k, fill="#e6fbff", outline="")
