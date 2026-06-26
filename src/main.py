"""
Pixel Assistant — PixelAssistant class.
Handles LLM routing, conversation history, shortcuts, and commands.

Performance:
- run_text():  blocks on input() — 0% CPU while waiting
- run_voice(): blocks on audio device I/O — 0% CPU while silent
- No polling loops anywhere
"""
import json
import math
import os
import re
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
from datetime import datetime
from pathlib import Path

import requests
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from core_files.config import Config
from core_files.logger import log_conversation, setup_logger
from core_files.ui import (
    console,
    C_PRIMARY, C_DIM, C_SUCCESS, C_WARN, C_ERROR, C_ACCENT,
    show_header, show_farewell,
    show_user_message, show_response,
    show_streaming_start, show_streaming_end,
    show_info, show_error, show_success, show_warning,
    divider, input_styled, show_panel, show_markdown, show_help_panel, show_table,
)
from search import Search
logger = setup_logger()

BASE           = Path(__file__).parent
HISTORY_FILE   = BASE / "functionalities" / "chat-history.json"
PERSONA_FILE   = BASE / "functionalities" / "context.md"
FUNCTIONS_FILE = BASE / "functionalities" / "functions.json"
NOTES_FILE     = BASE / "functionalities" / "notes.txt"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_persona() -> str:
    if PERSONA_FILE.exists():
        return PERSONA_FILE.read_text(encoding="utf-8").strip()
    return "You are Pixel, a helpful AI assistant."

def _load_history() -> list:
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def _save_history(history: list):
    HISTORY_FILE.parent.mkdir(exist_ok=True)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

def _load_shortcuts() -> dict:
    if FUNCTIONS_FILE.exists():
        with open(FUNCTIONS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}

def _parse_duration(s: str) -> int:
    """Parse '5min', '30s', '2h' → seconds."""
    s = s.strip().lower()
    m = re.match(r"(\d+(?:\.\d+)?)\s*(s|sec|seconds?|m|min|minutes?|h|hr|hours?)?$", s)
    if not m:
        raise ValueError(f"Can't parse duration: {s!r}")
    n = float(m.group(1))
    unit = (m.group(2) or "s")[0]
    return int(n * {"s": 1, "m": 60, "h": 3600}[unit])

def _safe_eval(expr: str) -> str:
    """Evaluate a math expression safely (no builtins, math module only)."""
    allowed = {k: getattr(math, k) for k in dir(math) if not k.startswith("_")}
    allowed.update({"abs": abs, "round": round, "int": int, "float": float,
                    "min": min, "max": max, "sum": sum, "pow": pow})
    result = eval(compile(expr, "<calc>", "eval"), {"__builtins__": {}}, allowed)
    return str(result)


# ── Main class ────────────────────────────────────────────────────────────────

class PixelAssistant:
    def __init__(
        self,
        provider: str = "groq",
        debug: bool = False,
        voice=None,
        token_callback=None,   # callable(token: str) for API streaming
    ):
        self.config         = Config()
        self.provider       = provider or self.config.provider
        self.debug          = debug
        self.voice          = voice
        self.token_callback = token_callback   # set by FastAPI WebSocket handler
        self.history        = _load_history()
        self.persona        = _load_persona()
        self.shortcuts      = _load_shortcuts()
        self._printed       = False
        self.ollama_url     = os.getenv("OLLAMA_URL", self.config.OLLAMA_URL or "http://localhost:11434")
        self.ollama_model   = os.getenv("OLLAMA_MODEL", self.config.OLLAMA_MODEL or "llama3.2")
        self.openai_base    = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.openai_key     = os.getenv("OPENAI_KEY", "")
        self.openai_model   = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self._init_clients()

    # ── Client init ───────────────────────────────────────────────────────

    def _init_clients(self):
        self.groq_client = None
        if self.config.GROQ_KEY:
            try:
                from groq import Groq
                self.groq_client = Groq(api_key=self.config.GROQ_KEY)
            except ImportError:
                self.groq_client = None
                import logging as _lg
                _lg.getLogger(__name__).warning("groq package not installed")
        self.gemini = None
        if self.config.GEMINI_KEY:
            try:
                from google import genai
                self.gemini = genai.Client(api_key=self.config.GEMINI_KEY)
            except Exception:
                pass
        self.mistral = None
        if self.config.MISTRAL_KEY:
            try:
                from mistralai import Mistral
                self.mistral = Mistral(api_key=self.config.MISTRAL_KEY)
            except Exception:
                pass

    # ── Shortcut commands ─────────────────────────────────────────────────

    def _check_shortcut(self, text: str) -> str | None:
        lower = text.lower().strip()
        for action, triggers in self.shortcuts.items():
            if any(t in lower for t in triggers):
                return self._run_shortcut(action, text)
        return None

    _IMAGE_PREFIX = re.compile(
        r"^(?:generate|create|make|draw|paint|show me)\s+(?:an?\s+)?"
        r"(?:image|picture|photo|artwork|illustration|painting)\s+(?:of\s+)?", re.I)
    _VIDEO_PREFIX = re.compile(
        r"^(?:generate|create|make|show me)\s+(?:an?\s+)?"
        r"(?:video|animation|clip|movie)\s+(?:of\s+)?", re.I)

    def _run_shortcut(self, action: str, original: str) -> str:
        if action == "time":
            return f"It's {datetime.now().strftime('%I:%M %p')}."
        if action == "date":
            return f"Today is {datetime.now().strftime('%A, %B %d, %Y')}."
        if action == "browser":
            webbrowser.open("https://www.google.com")
            return "Opened browser."
        if action == "screenshot":
            try:
                import pyautogui
                p = Path.home() / f"pixel_screenshot_{int(time.time())}.png"
                pyautogui.screenshot(str(p))
                from core_files.platform import open_file
                open_file(str(p))
                return f"Screenshot saved: {p.name}"
            except Exception as e:
                return f"Screenshot failed: {e}"
        if action == "search":
            query = re.sub(r"^(search for|look up|find information about|google)\s*",
                           "", original, flags=re.I).strip()
            return Search(query).search()
        if action == "image":
            return self._generate_image(original)
        if action == "video":
            return self._generate_video(original)
        if action.startswith("provider_"):
            provider = action[9:]   # "groq", "gemini", or "mistral"
            self.provider = provider
            self.config.set("provider", provider)
            self._init_clients()
            return f"Switched to {provider.title()}."

        if action == "calendar":
            lower = original.lower()
            if any(t in lower for t in ["today", "schedule today", "on today"]):
                return self._cmd_cal_today()
            if any(t in lower for t in ["add", "schedule", "create", "put on", "meeting"]):
                # strip the trigger phrase and treat the rest as the event description
                cleaned = re.sub(
                    r"^(add event|add a meeting|schedule a meeting|add to my calendar"
                    r"|create an event|put on my calendar|add a?)\s*", "",
                    original, flags=re.I,
                ).strip()
                return self._cmd_cal_add(cleaned or original)
            return self._cmd_cal_list(7)
        return ""

    # ── Media generation ──────────────────────────────────────────────────

    def _generate_image(self, original: str) -> str:
        prompt = self._IMAGE_PREFIX.sub("", original).strip() or original
        from skills.image_gen import generate_image
        try:
            with Progress(SpinnerColumn(),
                          TextColumn("[cyan]Generating image (~30s)...[/cyan]"),
                          transient=True, console=console) as p:
                p.add_task("", total=None)
                out = generate_image(prompt)
            from core_files.platform import open_file
            open_file(str(out))
            return f"Image saved and opened: {out.name}"
        except Exception as e:
            return f"Image generation failed: {e}"

    def _generate_video(self, original: str) -> str:
        prompt = self._VIDEO_PREFIX.sub("", original).strip() or original
        from skills.video_gen import generate_video
        try:
            with Progress(SpinnerColumn(),
                          TextColumn("[cyan]Generating video (1-2 min)...[/cyan]"),
                          transient=True, console=console) as p:
                p.add_task("", total=None)
                out = generate_video(prompt)
            from core_files.platform import open_file
            open_file(str(out))
            return f"Video saved and opened: {out.name}"
        except Exception as e:
            return f"Video generation failed: {e}"

    # ── Commands (/cmd) ───────────────────────────────────────────────────

    def _check_meta(self, text: str) -> str | None:
        s = text.strip()

        # ── /prompt — send raw text straight to the LLM ──────────────────
        if s == "/prompt":
            return (
                "Usage: /prompt <text>              send text directly to the LLM\n"
                "       /prompt --system <text>     use a one-shot system prompt\n"
                "       /prompt --bare <text>       no persona, no history\n"
                "Shortcuts and command parsing are skipped entirely."
            )

        if s.startswith("/prompt "):
            return self._cmd_prompt(s[8:])

        # ── /web ──────────────────────────────────────────────────────────
        if s == "/web":
            url = "http://localhost:8000"
            webbrowser.open(url)
            return f"Opening web UI: {url}"

        # ── /help ─────────────────────────────────────────────────────────
        if s in ("/help", "help", "/?"):
            return self._help_text()

        # ── /status ───────────────────────────────────────────────────────
        if s == "/status":
            return self._cmd_status()

        # ── /models ───────────────────────────────────────────────────────
        if s == "/models":
            return (
                "Available models:\n\n"
                "  GROQ (default provider — fastest responses, best for conversation):\n"
                "    llama-3.3-70b-versatile        Best overall — smart, fast, great reasoning\n"
                "    llama-3.1-8b-instant           Fastest — use for quick tasks and short answers\n"
                "    deepseek-r1-distill-llama-70b  Chain-of-thought — shows step-by-step reasoning\n"
                "    gemma2-9b-it                   Compact Google model — good for light tasks\n\n"
                "  GEMINI (best for long context and multimodal — images, documents):\n"
                "    gemini-2.0-flash-exp           Massive context window, handles PDFs and images\n\n"
                "  MISTRAL (balanced — good general assistant, European privacy):\n"
                "    mistral-large-latest           Strong reasoning, multilingual, privacy-focused\n\n"
                "  RECOMMENDATION:\n"
                "    Everyday chat        → llama-3.3-70b-versatile (default)\n"
                "    Need to think hard   → deepseek-r1-distill-llama-70b\n"
                "    Long document/image  → gemini-2.0-flash-exp\n"
                "    Speed over quality   → llama-3.1-8b-instant\n\n"
                "Switch with: /set model <name>  or  /set provider groq|gemini|mistral"
            )

        # ── /smart ────────────────────────────────────────────────────────
        if s == "/smart":
            current = self.config.get("smart_mode", False)
            self.config.set("smart_mode", not current)
            new = not current
            model = self.config.smart_model if new else self.config.model
            return f"Smart mode {'ON' if new else 'OFF'} — using {model}."

        # ── /history ──────────────────────────────────────────────────────
        if s == "/history":
            if not self.history:
                return "No conversation history yet."
            lines = [f"[{m['role'].upper()}] {m['content'][:120]}" for m in self.history[-20:]]
            return "\n".join(lines)

        # ── /clear ────────────────────────────────────────────────────────
        if s == "/clear":
            self.history.clear()
            _save_history(self.history)
            return "Conversation history cleared."

        # ── Notes ─────────────────────────────────────────────────────────
        if s == "/notes":
            return self._cmd_notes_list()

        if s.startswith("/note delete "):
            return self._cmd_note_delete(s[13:].strip())

        if s == "/note clear":
            return self._cmd_note_clear()

        if s.startswith("/note search "):
            return self._cmd_note_search(s[13:].strip())

        if s.startswith("/note "):
            return self._cmd_note_add(s[6:].strip())

        # ── /email ────────────────────────────────────────────────────────
        if s == "/email":
            return (
                "Usage: /email <description>\n"
                "Example: /email to my professor asking for an extension on the assignment\n"
                "         /email reply declining a job offer politely"
            )

        if s.startswith("/email "):
            return self._cmd_email(s[7:].strip())

        # ── /speak ────────────────────────────────────────────────────────
        if s == "/speak":
            return "Usage: /speak <text>  — reads text aloud using TTS"

        if s.startswith("/speak "):
            return self._cmd_speak(s[7:].strip())

        # ── /conversation ─────────────────────────────────────────────────
        if s in ("/conversation", "/converse"):
            return self._cmd_conversation()

        # ── /translate ────────────────────────────────────────────────────
        if s == "/translate":
            return (
                "Usage:\n"
                "  /translate <language> <text>             quick translation\n"
                "  /translate --explain <language> <text>   detailed: pronunciation, breakdown, alternatives\n"
                "  /translate file <language> <path>        translate a text file\n"
                "Example: /translate Spanish Hello, how are you?\n"
                "         /translate --explain French The weather is beautiful today."
            )

        if s.startswith("/translate "):
            rest = s[11:]
            if rest.startswith("--explain "):
                parts = rest[10:].split(None, 1)
                if len(parts) < 2:
                    return "Usage: /translate --explain <language> <text>"
                return self._cmd_translate(parts[0], parts[1], explain=True)
            if rest.startswith("file "):
                parts = rest[5:].split(None, 1)
                if len(parts) < 2:
                    return "Usage: /translate file <language> <path>"
                return self._cmd_translate_file(parts[0], parts[1])
            parts = rest.split(None, 1)
            if len(parts) < 2:
                return "Usage: /translate <language> <text>"
            return self._cmd_translate(parts[0], parts[1])

        # ── /define ───────────────────────────────────────────────────────
        if s.startswith("/define "):
            return self._cmd_define(s[8:].strip())

        # ── /summarize ────────────────────────────────────────────────────
        if s == "/summarize":
            return self._cmd_summarize(None)

        if s.startswith("/summarize "):
            return self._cmd_summarize(s[11:].strip())

        # ── /todo ─────────────────────────────────────────────────────────
        if s == "/todo":
            return self._cmd_todo_list()

        if s.startswith("/todo add "):
            return self._cmd_todo_add(s[10:].strip())

        if s.startswith("/todo done "):
            return self._cmd_todo_done(s[11:].strip())

        if s.startswith("/todo delete "):
            return self._cmd_todo_delete(s[13:].strip())

        if s == "/todo clear":
            return self._cmd_todo_clear()

        # ── /timer ────────────────────────────────────────────────────────
        if s.startswith("/timer "):
            return self._cmd_timer(s[7:].strip())

        # ── /calc <expr> ──────────────────────────────────────────────────
        if s.startswith("/calc "):
            expr = s[6:].strip()
            try:
                return f"{expr} = {_safe_eval(expr)}"
            except Exception as e:
                return f"Calc error: {e}"

        # ── /weather [city] ───────────────────────────────────────────────
        if s.startswith("/weather"):
            from skills.weather import get_weather
            return get_weather(s[8:].strip() or "auto")

        # ── /remind <duration> <message> ──────────────────────────────────
        if s.startswith("/remind "):
            parts = s[8:].split(None, 1)
            if len(parts) < 2:
                return "Usage: /remind <duration> <message>  e.g. /remind 5min take a break"
            try:
                secs = _parse_duration(parts[0])
            except ValueError as e:
                return str(e)
            msg = parts[1]

            def _fire():
                time.sleep(secs)
                console.print(f"\n[bold yellow]REMINDER:[/bold yellow] {msg}\n")
                from core_files.platform import play_beep
                play_beep()

            threading.Thread(target=_fire, daemon=True).start()
            return f"Reminder set: '{msg}' in {parts[0]}."

        # ── /run <python code> ────────────────────────────────────────────
        if s.startswith("/run "):
            code = s[5:].strip()
            try:
                result = subprocess.run(
                    [sys.executable, "-c", code],
                    capture_output=True, text=True, timeout=15,
                )
                out = result.stdout.strip() or result.stderr.strip()
                return out or "(no output)"
            except subprocess.TimeoutExpired:
                return "Timed out after 15 seconds."
            except Exception as e:
                return f"Run error: {e}"

        # ── /open <path or url> ───────────────────────────────────────────
        if s.startswith("/open "):
            target = s[6:].strip()
            try:
                from core_files.platform import open_file
                ok = open_file(target)
                return f"Opened: {target}" if ok else f"Could not open: {target}"
            except Exception as e:
                return f"Could not open: {e}"

        # ── /sys ──────────────────────────────────────────────────────────
        if s == "/sys":
            try:
                import psutil
                cpu  = psutil.cpu_percent(interval=0.5)
                ram  = psutil.virtual_memory()
                disk = psutil.disk_usage(psutil.disk_partitions()[0].mountpoint)
                return (
                    f"CPU:  {cpu}%\n"
                    f"RAM:  {ram.used/1e9:.1f} / {ram.total/1e9:.1f} GB  ({ram.percent}%)\n"
                    f"Disk: {disk.used/1e9:.0f} / {disk.total/1e9:.0f} GB  ({disk.percent}%)"
                )
            except ImportError:
                return "psutil not installed. Run: pip install psutil"

        # ── /morning ──────────────────────────────────────────────────────────
        if s in ("/morning", "/briefing"):
            return self._cmd_morning()

        # ── /lang ────────────────────────────────────────────────────────────
        if s == "/lang":
            state = "ON" if self.config.get("auto_lang") else "OFF"
            return (
                f"Auto-language is {state}.\n\n"
                "Language learning commands:\n"
                "  /lang learn <language>                start interactive learning session\n"
                "  /lang vocab <language> [topic]        flashcard vocabulary drill\n"
                "  /lang lesson <language> <topic>       structured lesson with AI tutor\n"
                "  /lang conversation <language> [scene] practice conversation (AI roleplay)\n"
                "  /lang progress                        view your progress across all languages\n"
                "  /lang download <language>             download offline translation pack\n"
                "  /lang offline                         show which offline packs are installed\n"
                "  /lang auto                            auto-detect language, respond in kind\n"
                "  /lang off                             always respond in English\n"
                "\nTopics: greetings · numbers · phrases · days · colors\n"
                "Languages: Spanish, French, German, Japanese, Korean, Italian, Portuguese, Russian, Chinese, Arabic, Hindi, Dutch, ..."
            )
        if s.startswith("/lang "):
            arg = s[6:].strip()
            # New sub-commands first
            if arg == "progress":
                return self._cmd_lang_progress()
            if arg == "offline":
                return self._cmd_lang_offline()
            if arg.startswith("download "):
                return self._cmd_lang_download(arg[9:].strip())
            if arg.startswith("learn "):
                return self._cmd_lang_learn(arg[6:].strip())
            if arg.startswith("vocab "):
                parts = arg[6:].strip().split(None, 1)
                lang = parts[0]
                topic = parts[1] if len(parts) > 1 else "all"
                return self._cmd_lang_vocab(lang, topic)
            if arg.startswith("lesson "):
                parts = arg[7:].strip().split(None, 1)
                if len(parts) < 2:
                    return "Usage: /lang lesson <language> <topic>  e.g. /lang lesson Spanish present tense"
                return self._cmd_lang_lesson(parts[0], parts[1])
            if arg.startswith("conversation "):
                parts = arg[13:].strip().split(None, 1)
                lang = parts[0]
                scene = parts[1] if len(parts) > 1 else "at a café"
                return self._cmd_lang_conversation(lang, scene)
            return self._cmd_lang(arg)

        # ── /check ────────────────────────────────────────────────────────────
        if s == "/check":
            return self._cmd_check()

        # ── /wiki <topic> ────────────────────────────────────────────────────
        if s.startswith("/wiki "):
            return self._cmd_wiki(s[6:].strip())

        # ── /code <task> ─────────────────────────────────────────────────────
        if s == "/code":
            return "Usage: /code <task>  e.g. /code binary search in Python"
        if s.startswith("/code "):
            return self._cmd_code(s[6:].strip())

        # ── /pomodoro ─────────────────────────────────────────────────────────
        if s == "/pomodoro" or s.startswith("/pomodoro "):
            return self._cmd_pomodoro(s[10:].strip() if s.startswith("/pomodoro ") else "")

        # ── /clip ─────────────────────────────────────────────────────────────
        if s == "/clip":
            return self._cmd_clip()

        # ── /journal ──────────────────────────────────────────────────────────
        if s == "/journal":
            return self._cmd_journal("")
        if s.startswith("/journal "):
            return self._cmd_journal(s[9:].strip())

        # ── /password ─────────────────────────────────────────────────────
        if s == "/password clear":
            return self._cmd_password_clear()

        if s.startswith("/password"):
            return self._cmd_password(s[9:].strip())

        # ── /teach ────────────────────────────────────────────────────────
        if s == "/teach":
            return (
                "Usage: /teach <topic>       start a lesson\n"
                "       /teach quiz          quiz on the last topic\n"
                "       /teach topics        list topics you've studied\n"
                "       /teach reset         clear study history\n"
                "Example: /teach recursion"
            )

        if s == "/teach quiz":
            return self._cmd_teach_quiz()

        if s == "/teach topics":
            return self._cmd_teach_topics()

        if s == "/teach reset":
            return self._cmd_teach_reset()

        if s.startswith("/teach "):
            return self._cmd_teach(s[7:].strip())

        # ── /slides <topic> ───────────────────────────────────────────────
        if s.startswith("/slides "):
            return self._cmd_slides(s[8:].strip())

        # ── /pdf <topic> ──────────────────────────────────────────────────
        if s.startswith("/pdf "):
            return self._cmd_pdf(s[5:].strip())

        # ── /calendar commands ────────────────────────────────────────────
        if s in ("/calendar", "/events"):
            return self._cmd_cal_list(7)

        if s == "/calendar today":
            return self._cmd_cal_today()

        if s.startswith("/calendar add "):
            return self._cmd_cal_add(s[14:].strip())

        if s.startswith("/event add "):
            return self._cmd_cal_add(s[11:].strip())

        if s.startswith("/calendar delete "):
            return self._cmd_cal_delete(s[17:].strip())

        if s.startswith("/event delete "):
            return self._cmd_cal_delete(s[14:].strip())

        if s == "/calendar setup":
            return self._cmd_cal_setup()

        # ── /themes ───────────────────────────────────────────────────────
        if s == "/themes":
            current_slide = self.config.get("slide_theme", "dark")
            current_pdf   = self.config.get("pdf_theme", "light")
            return (
                "Available themes: dark  light  corporate  modern  warm\n\n"
                f"  Slide theme : {current_slide}   (/set slide_theme <name>)\n"
                f"  PDF theme   : {current_pdf}   (/set pdf_theme <name>)"
            )

        # ── /agent ────────────────────────────────────────────────────────
        if s == "/agent":
            return "Usage: /agent <type> <task>\nTypes: explorer  coder  planner  debugger  orchestrator\n       /agent auto <task>  /agent background <type> <task>  /agent status  /agent list  /agent history"
        if s.startswith("/agent "):
            return self._cmd_agent(s[7:].strip())

        # ── /set <key> <value> ────────────────────────────────────────────
        if s.startswith("/set provider "):
            val = s[14:].strip()
            self.provider = val
            self.config.set("provider", val)
            return f"Provider switched to {val}."

        if s.startswith("/set persona "):
            val = s[13:].strip()
            self.persona = val
            PERSONA_FILE.write_text(val, encoding="utf-8")
            return "Persona updated and saved."

        if s.startswith("/set model "):
            val = s[11:].strip()
            self.config.set("model", val)
            return f"Model set to {val}."

        if s.startswith("/set "):
            parts = s[5:].split(None, 1)
            if len(parts) == 2:
                key, value = parts
                try:
                    value = int(value)
                except ValueError:
                    if value.lower() in ("true", "yes"):
                        value = True
                    elif value.lower() in ("false", "no"):
                        value = False
                self.config.set(key, value)
                return f"Config: {key} = {value}"
            return "Usage: /set <key> <value>"

        # ── /pixel — ecosystem launcher ───────────────────────────────────
        if s == "/pixel" or s.startswith("/pixel "):
            return self._cmd_pixel(s[7:].strip() if s.startswith("/pixel ") else "")

        # ── /update ───────────────────────────────────────────────────────
        if s == "/update":
            return (
                "Usage:\n"
                "  /update debug              scan source for bugs and auto-fix them\n"
                "  /update upgrade            implement next planned feature\n"
                "  /update full               debug pass then upgrade pass\n"
                "  /update check              scan source for bugs (report only)\n"
            "  /update feature <desc>     generate and apply a new command\n"
            "  /update skill <desc>       generate a new skill module in src/skills/\n"
            "  /update fix <desc>         generate and apply a targeted fix\n"
                "  /update log                show update history\n"
                "  /update rollback           restore last backup of main.py\n"
                "  /update planned            show planned features list"
            )

        if s == "/update debug":
            return self._cmd_update_debug()

        if s == "/update upgrade":
            return self._cmd_update_upgrade()

        if s == "/update full":
            return self._cmd_update_full()

        if s == "/update check":
            return self._cmd_update_check()

        if s == "/update skill":
            return (
                "Usage: /update skill <description>\n"
                "Example: /update skill currency converter using exchangerate-api"
            )

        if s.startswith("/update skill "):
            return self._cmd_update_skill(s[13:].strip())

        if s.startswith("/update feature "):
            return self._cmd_update_feature(s[16:].strip())

        if s.startswith("/update fix "):
            return self._cmd_update_fix(s[12:].strip())

        if s == "/update log":
            return self._cmd_update_log()

        if s == "/update rollback":
            return self._cmd_update_rollback()

        if s == "/update planned":
            return self._cmd_update_planned()

        # ── /security ─────────────────────────────────────────────────────
        if s == "/security":
            return (
                "Usage:\n"
                "  /security audit            scan all open ports and score risk\n"
                "  /security fix              block all high/medium/unknown risk ports\n"
                "  /security fix <port>       block a specific port  e.g. /security fix 3389\n"
            )

        if s == "/security audit":
            return self._cmd_security_audit()

        if s == "/security fix":
            return self._cmd_security_fix()

        if s.startswith("/security fix "):
            return self._cmd_security_fix_port(s[14:].strip())

        # ── /encrypt / /decrypt / /hash ───────────────────────────────────
        if s == "/encrypt":
            return (
                "Usage: /encrypt <method> <key> <text>\n"
                "Methods: aes  xor  caesar  vigenere  file\n"
                "  aes      — AES-256 (requires cryptography package)\n"
                "  xor      — XOR + base64\n"
                "  caesar   — Caesar cipher  (key = shift number)\n"
                "  vigenere — Vigenère cipher\n"
                "  file     — encrypt a file  (key = password, text = file path)\n"
                "Example: /encrypt aes mysecret Hello World"
            )

        if s.startswith("/encrypt "):
            return self._cmd_encrypt(s[9:].strip())

        if s == "/decrypt":
            return (
                "Usage: /decrypt <method> <key> <ciphertext>\n"
                "Methods: aes  xor  caesar  vigenere  file\n"
                "Example: /decrypt aes mysecret <ciphertext>"
            )

        if s.startswith("/decrypt "):
            return self._cmd_decrypt(s[9:].strip())

        if s == "/hash":
            return (
                "Usage: /hash [algorithm] <text>\n"
                "Default algorithm: sha256\n"
                "Algorithms: md5  sha1  sha224  sha256  sha384  sha512  blake2b  blake2s\n"
                "Example: /hash sha256 hello world"
            )

        if s.startswith("/hash "):
            return self._cmd_hash(s[6:].strip())

        # ── /stego ────────────────────────────────────────────────────────
        if s in ("/stego", "/steganography"):
            return (
                "Steganography — hide messages inside image files:\n\n"
                "  /stego hide <image> <message>              hide plaintext\n"
                "  /stego hide <image> <password> <message>   hide AES-encrypted message\n"
                "  /stego reveal <image>                      extract hidden message\n"
                "  /stego reveal <image> <password>           extract + decrypt\n"
                "  /stego capacity <image>                    show max bytes an image can hide\n\n"
                "Output image is saved as <original>_stego.<ext> by default.\n"
                "Use PNG or BMP — JPEG compression destroys hidden data."
            )

        if s.startswith("/stego "):
            return self._cmd_stego(s[7:].strip())

        # ── /news ────────────────────────────────────────────────────────
        if s == "/news":
            return self._cmd_news(None)
        if s.startswith("/news "):
            return self._cmd_news(s[6:].strip())

        # ── /convert ─────────────────────────────────────────────────────
        if s.startswith("/convert "):
            return self._cmd_convert(s[9:].strip())

        # ── /qr ──────────────────────────────────────────────────────────
        if s.startswith("/qr "):
            return self._cmd_qr(s[4:].strip())

        # ── /regex ───────────────────────────────────────────────────────
        if s.startswith("/regex "):
            return self._cmd_regex(s[7:].strip())

        # ── /ip ──────────────────────────────────────────────────────────
        if s == "/ip":
            return self._cmd_ip()

        # ── /ping ────────────────────────────────────────────────────────
        if s.startswith("/ping "):
            return self._cmd_ping(s[6:].strip())

        # ── /diff ────────────────────────────────────────────────────────
        if s.startswith("/diff "):
            return self._cmd_diff(s[6:].strip())

        # ── /encode ──────────────────────────────────────────────────────
        if s == "/encode":
            return "Usage: /encode <method> <text>  methods: base64  url  hex"
        if s.startswith("/encode "):
            return self._cmd_encode(s[8:].strip())

        # ── /decode ──────────────────────────────────────────────────────
        if s == "/decode":
            return "Usage: /decode <method> <text>  methods: base64  url  hex"
        if s.startswith("/decode "):
            return self._cmd_decode(s[8:].strip())

        # ── /uuid ────────────────────────────────────────────────────────
        if s == "/uuid":
            return self._cmd_uuid("1")
        if s.startswith("/uuid "):
            return self._cmd_uuid(s[6:].strip())

        # ── /lorem ───────────────────────────────────────────────────────
        if s == "/lorem":
            return self._cmd_lorem("3")
        if s.startswith("/lorem "):
            return self._cmd_lorem(s[7:].strip())

        # ── /flip ────────────────────────────────────────────────────────
        if s.startswith("/flip "):
            return self._cmd_flip(s[6:].strip())

        # ── /ascii ───────────────────────────────────────────────────────
        if s == "/ascii":
            return "Usage: /ascii <text>  — convert text to ASCII art banner"
        if s.startswith("/ascii "):
            return self._cmd_ascii(s[7:].strip())

        return None

    # ── Notes ────────────────────────────────────────────────────────────

    def _notes_lines(self) -> list[str]:
        if not NOTES_FILE.exists():
            return []
        return [l for l in NOTES_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]

    def _notes_write(self, lines: list[str]):
        NOTES_FILE.parent.mkdir(exist_ok=True)
        NOTES_FILE.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    def _cmd_note_add(self, text: str) -> str:
        if not text:
            return "Usage: /note <text>"
        lines = self._notes_lines()
        lines.append(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] {text}")
        self._notes_write(lines)
        return f"Note #{len(lines)} saved."

    def _cmd_notes_list(self) -> str:
        lines = self._notes_lines()
        if not lines:
            return "No notes yet. Add one with: /note <text>"
        numbered = "\n".join(f"  {i+1:>3}. {l}" for i, l in enumerate(lines))
        return f"Notes ({len(lines)}):\n{numbered}"

    def _cmd_note_delete(self, arg: str) -> str:
        lines = self._notes_lines()
        if not lines:
            return "No notes to delete."
        # accept a number or "last"
        if arg.lower() == "last":
            idx = len(lines) - 1
        else:
            try:
                idx = int(arg) - 1
            except ValueError:
                return "Usage: /note delete <number>  or  /note delete last"
        if idx < 0 or idx >= len(lines):
            return f"No note #{idx + 1}. You have {len(lines)} note(s)."
        removed = lines.pop(idx)
        self._notes_write(lines)
        return f"Deleted: {removed}"

    def _cmd_note_clear(self) -> str:
        count = len(self._notes_lines())
        self._notes_write([])
        return f"Cleared {count} note(s)."

    def _cmd_note_search(self, query: str) -> str:
        if not query:
            return "Usage: /note search <keyword>"
        lines = self._notes_lines()
        hits = [(i + 1, l) for i, l in enumerate(lines) if query.lower() in l.lower()]
        if not hits:
            return f"No notes matching '{query}'."
        return "\n".join(f"  {n:>3}. {l}" for n, l in hits)

    # ── Email drafting ────────────────────────────────────────────────────

    def _cmd_email(self, description: str) -> str:
        if not description:
            return "Describe the email: /email <description>"
        prompt = (
            f"Draft a professional email based on this request:\n{description}\n\n"
            f"Reply ONLY with the email in this format:\n"
            f"Subject: <subject line>\n\n"
            f"<email body>\n\n"
            f"Keep it concise and professional. Do not add any commentary outside the email."
        )
        show_info("Drafting email...")
        raw = self._ask_llm([{"role": "user", "content": prompt}])
        if not self._printed:
            console.print(
                Panel(raw, title="[bold cyan]Draft Email[/bold cyan]",
                      border_style="cyan", expand=False)
            )
            self._printed = True
        from core_files.platform import copy_clipboard
        if copy_clipboard(raw):
            show_success("Copied to clipboard.")
        return raw

    # ── Voice helpers ─────────────────────────────────────────────────────

    def _get_voice(self):
        """Return existing voice or create and cache one on demand."""
        if self.voice:
            return self.voice
        try:
            from core_files.voice_setup import check as _chk
            if not _chk(require_microphone=False):
                return None
            from core_files.voice import Voice
            self.voice = Voice(rate=self.config.tts_rate, volume=self.config.tts_volume)
            return self.voice
        except Exception as e:
            show_error(f"Voice unavailable: {e}")
            return None

    # ── /speak ────────────────────────────────────────────────────────────

    def _cmd_speak(self, text: str) -> str:
        v = self._get_voice()
        if v is None:
            return (
                "TTS not available. Install deps:\n"
                "  pip install pyttsx3\n"
                "  pip install pipwin && pipwin install pyaudio"
            )
        v.speak_streaming(text)
        return f"Spoke: {text[:60]}{'...' if len(text) > 60 else ''}"

    # ── /conversation ─────────────────────────────────────────────────────

    def _cmd_conversation(self) -> str:
        v = self._get_voice()
        if v is None:
            return (
                "Voice not available — install deps first:\n"
                "  python -m core_files.voice_setup --install"
            )

        show_panel("Voice Conversation",
                    "Speak naturally. Say 'stop', 'exit', or 'end conversation' to quit.\n"
                    "Press Ctrl+C to exit.",
                    border_style=C_PRIMARY)

        try:
            from core_files.tray import set_state
        except Exception:
            def set_state(_): pass

        EXIT_PHRASES = {"stop", "exit", "quit", "end conversation",
                        "stop conversation", "goodbye", "bye"}

        v.speak("Conversation mode started. How can I help?")
        _silence_streak = 0

        while True:
            try:
                set_state("listening")
                show_info("Listening...")
                text = v.listen(timeout=10, phrase_time_limit=30)

                if not text:
                    _silence_streak += 1
                    if _silence_streak >= 6:   # 60 s of silence → exit
                        show_info("No speech detected. Ending conversation.")
                        set_state("idle")
                        break
                    time.sleep(0.5)
                    continue
                _silence_streak = 0

                show_user_message(text)

                if any(p in text.lower() for p in EXIT_PHRASES):
                    v.speak("Ending conversation. Goodbye!")
                    set_state("idle")
                    break

                set_state("processing")
                response = self.handle_prompt(text)
                self._printed = False

                if response:
                    show_response(response)

                set_state("responding")
                v.speak_streaming(response or "")
                set_state("idle")

            except KeyboardInterrupt:
                show_info("Conversation ended.")
                set_state("idle")
                break

        return ""

    # ── Translate ─────────────────────────────────────────────────────────

    def _cmd_translate(self, language: str, text: str, explain: bool = False) -> str:
        from skills.language import build_translation_prompt, translate_offline, LANG_CODE
        # Try offline first for simple (non-explain) translations
        if not explain:
            lang_key = language.lower()
            lang_code = LANG_CODE.get(lang_key)
            if lang_code:
                offline = translate_offline(text, lang_code)
                if offline:
                    return f"[{language}] {offline}"
        prompt = build_translation_prompt(text, language, explain=explain)
        result = self._ask_llm([{"role": "user", "content": prompt}])
        if not self._printed:
            console.print(Markdown(result))
            self._printed = True
        return result.strip()

    def _cmd_translate_file(self, language: str, path: str) -> str:
        p = Path(path.strip('"').strip("'"))
        if not p.exists():
            return f"File not found: {path}"
        try:
            text = p.read_text(encoding="utf-8")
        except Exception as e:
            return f"Could not read file: {e}"
        if len(text) > 8000:
            text = text[:8000]
            show_warning("File truncated to 8000 chars for translation.")
        from skills.language import build_translation_prompt
        prompt = build_translation_prompt(text, language, explain=False)
        result = self._ask_llm([{"role": "user", "content": prompt}])
        out_path = p.with_stem(p.stem + f"_{language.lower()}")
        out_path.write_text(result, encoding="utf-8")
        show_success(f"Saved: {out_path}")
        self._printed = True
        return f"File translated to {language} → {out_path.name}"

    # ── Define ────────────────────────────────────────────────────────────

    def _cmd_define(self, word: str) -> str:
        if not word:
            return "Usage: /define <word>"
        prompt = (
            f"Define '{word}' clearly and concisely.\n"
            f"Use this format:\n"
            f"**{word}** (part of speech)\n"
            f"1. <primary meaning>\n"
            f"2. <secondary meaning if applicable>\n\n"
            f"Example: <one short example sentence>\n\n"
            f"Etymology: <brief origin if interesting, otherwise omit>"
        )
        result = self._ask_llm([{"role": "user", "content": prompt}])
        if not self._printed:
            console.print(Markdown(result))
            self._printed = True
        return result

    # ── Summarize ─────────────────────────────────────────────────────────

    def _cmd_summarize(self, text: str | None) -> str:
        if text:
            target = text
        elif self.history:
            last_assistant = next(
                (m["content"] for m in reversed(self.history) if m["role"] == "assistant"),
                None,
            )
            if not last_assistant:
                return "No previous response to summarize. Pass text: /summarize <text>"
            target = last_assistant
        else:
            return "No conversation history. Pass text: /summarize <text>"

        prompt = (
            f"Summarize the following in 3 bullet points. Be concise:\n\n{target}"
        )
        result = self._ask_llm([{"role": "user", "content": prompt}])
        return result.strip()

    # ── Todo list ─────────────────────────────────────────────────────────

    _TODO_FILE = BASE / "functionalities" / "todos.json"

    def _load_todos(self) -> list[dict]:
        if self._TODO_FILE.exists():
            try:
                return json.loads(self._TODO_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return []

    def _save_todos(self, todos: list[dict]):
        self._TODO_FILE.parent.mkdir(exist_ok=True)
        self._TODO_FILE.write_text(
            json.dumps(todos, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def _cmd_todo_list(self) -> str:
        todos = self._load_todos()
        if not todos:
            return "No todos. Add one: /todo add <task>"
        lines = []
        for i, t in enumerate(todos, 1):
            done = "[x]" if t.get("done") else "[ ]"
            lines.append(f"  {i:>3}. {done} {t['task']}")
        pending = sum(1 for t in todos if not t.get("done"))
        return f"Todos ({pending} pending / {len(todos)} total):\n" + "\n".join(lines)

    def _cmd_todo_add(self, task: str) -> str:
        if not task:
            return "Usage: /todo add <task>"
        todos = self._load_todos()
        todos.append({"task": task, "done": False, "added": datetime.now().strftime("%Y-%m-%d")})
        self._save_todos(todos)
        return f"Added #{len(todos)}: {task}"

    def _cmd_todo_done(self, arg: str) -> str:
        todos = self._load_todos()
        if not todos:
            return "No todos."
        try:
            idx = int(arg) - 1
        except ValueError:
            return "Usage: /todo done <number>"
        if idx < 0 or idx >= len(todos):
            return f"No todo #{idx + 1}."
        todos[idx]["done"] = True
        self._save_todos(todos)
        return f"Marked done: {todos[idx]['task']}"

    def _cmd_todo_delete(self, arg: str) -> str:
        todos = self._load_todos()
        if not todos:
            return "No todos."
        try:
            idx = int(arg) - 1
        except ValueError:
            return "Usage: /todo delete <number>"
        if idx < 0 or idx >= len(todos):
            return f"No todo #{idx + 1}."
        removed = todos.pop(idx)
        self._save_todos(todos)
        return f"Deleted: {removed['task']}"

    def _cmd_todo_clear(self) -> str:
        todos = self._load_todos()
        pending = [t for t in todos if not t.get("done")]
        self._save_todos(pending)
        cleared = len(todos) - len(pending)
        return f"Cleared {cleared} completed todo(s). {len(pending)} pending remain."

    # ── Timer ─────────────────────────────────────────────────────────────

    def _cmd_timer(self, arg: str) -> str:
        if not arg:
            return "Usage: /timer <duration>  e.g. /timer 5min"
        try:
            secs = _parse_duration(arg)
        except ValueError as e:
            return str(e)

        def _run_timer():
            start = time.time()
            try:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[cyan]{task.description}[/cyan]"),
                    transient=False,
                    console=console,
                ) as prog:
                    task_id = prog.add_task(f"Timer: {arg}", total=secs)
                    while True:
                        elapsed = time.time() - start
                        remaining = max(0, secs - elapsed)
                        prog.update(task_id, completed=elapsed,
                                    description=f"Timer: {arg}  ({int(remaining)}s left)")
                        if elapsed >= secs:
                            break
                        time.sleep(0.5)
            except Exception:
                pass
            console.print(f"\n[bold yellow]Timer done:[/bold yellow] {arg}\n")
            from core_files.platform import play_beep
            play_beep()

        threading.Thread(target=_run_timer, daemon=True).start()
        return f"Timer started: {arg}."

    # ── Self-update ───────────────────────────────────────────────────────

    def _cmd_pixel(self, arg: str) -> str:
        import sys as _sys
        from pathlib import Path as _Path
        _eco_parent = _Path(__file__).parent.parent.parent  # portfolio/
        _sys.path.insert(0, str(_eco_parent))
        try:
            from pixel_ecosystem.registry import PIXEL_APPS
            from pixel_ecosystem.launcher import launch, list_apps
        except ImportError:
            return (
                "pixel_ecosystem module not found.\n"
                "Expected at: portfolio/pixel_ecosystem/"
            )

        if not arg:
            lines = list_apps()
            return "Pixel Ecosystem — all apps:\n\n" + lines + "\n\nLaunch with: /pixel <app-name>"

        launch(arg)
        return f"Launched: {arg}"

    def _cmd_update_debug(self) -> str:
        show_info("Starting self-debug pass...")
        from skills.self_update import run_debug_pass
        result = run_debug_pass(self._ask_llm, self._confirm)
        if not self._printed:
            console.print(result)
            self._printed = True
        return result

    def _cmd_update_upgrade(self) -> str:
        show_info("Starting self-upgrade pass...")
        from skills.self_update import run_upgrade_pass
        result = run_upgrade_pass(self._ask_llm, self._confirm)
        if not self._printed:
            console.print(result)
            self._printed = True
        return result

    def _cmd_update_full(self) -> str:
        show_info("Starting full self-update (debug + upgrade)...")
        from skills.self_update import run_full_pass
        result = run_full_pass(self._ask_llm, self._confirm)
        if not self._printed:
            console.print(result)
            self._printed = True
        return result

    def _cmd_update_planned(self) -> str:
        from skills.self_update import PLANNED_MD, _ensure_planned_md
        _ensure_planned_md()
        text = PLANNED_MD.read_text(encoding="utf-8")
        console.print(text)
        self._printed = True
        return text

    def _cmd_update_check(self) -> str:
        show_info("Scanning source files...")
        from skills.self_update import check_code
        result = check_code(self._ask_llm)
        if not self._printed:
            console.print(Markdown(result))
            self._printed = True
        return result

    def _cmd_update_feature(self, description: str) -> str:
        if not description:
            return "Describe the feature: /update feature <description>"
        show_info(f"Generating feature: {description}")
        from skills.self_update import generate_feature
        return generate_feature(description, self._ask_llm, self._confirm)

    def _cmd_update_fix(self, description: str) -> str:
        if not description:
            return "Describe the bug: /update fix <description>"
        show_info(f"Generating fix: {description}")
        from skills.self_update import generate_fix
        return generate_fix(description, self._ask_llm, self._confirm)

    def _cmd_update_skill(self, description: str) -> str:
        if not description:
            return "Describe the skill: /update skill <description>\nExample: /update skill currency converter using exchangerate-api"
        show_info(f"Generating new skill module: {description}")
        from skills.self_update import generate_skill
        return generate_skill(description, self._ask_llm, self._confirm)

    def _cmd_update_log(self) -> str:
        from skills.self_update import show_log
        return show_log()

    def _cmd_update_rollback(self) -> str:
        confirmed = self._confirm("Restore main.py from last backup? [y/N] ")
        if not confirmed:
            return "Rollback cancelled."
        from skills.self_update import rollback
        return rollback()

    def _confirm(self, prompt: str) -> bool:
        """Prompt user for y/N confirmation in the terminal."""
        try:
            ans = input(prompt).strip().lower()
            return ans in ("y", "yes")
        except (KeyboardInterrupt, EOFError):
            return False

    # ── /prompt ───────────────────────────────────────────────────────────

    def _cmd_prompt(self, raw: str) -> str:
        """Send plain text directly to the LLM, bypassing all shortcuts."""
        bare   = False
        system = None

        if raw.startswith("--bare "):
            bare = True
            raw  = raw[7:].strip()
        elif raw.startswith("--system "):
            # everything up to next quoted block or end is the system prompt;
            # treat the rest as the user message
            rest = raw[9:]
            # split on first '|' if present, otherwise the whole thing is system
            if "|" in rest:
                system, _, raw = rest.partition("|")
                system = system.strip()
                raw    = raw.strip()
            else:
                system = rest.strip()
                raw    = ""

        if not raw and not system:
            return "No text provided. Usage: /prompt <text>"

        if system and not raw:
            return (
                "Provide a user message after the system prompt.\n"
                "Usage: /prompt --system <system prompt> | <user message>"
            )

        if bare:
            messages = [{"role": "user", "content": raw}]
        elif system:
            messages = [
                {"role": "system", "content": system},
                {"role": "user",   "content": raw},
            ]
        else:
            # Normal persona + history, but shortcuts already skipped
            messages = self._build_messages(raw)

        response = self._ask_llm(messages)

        if not bare:
            self.history.append({"role": "user",      "content": raw or system})
            self.history.append({"role": "assistant",  "content": response})
            _save_history(self.history)

        return response

    # ── Teach ────────────────────────────────────────────────────────────

    _TEACH_FILE = BASE / "functionalities" / "teach_history.json"

    def _load_teach_history(self) -> dict:
        if self._TEACH_FILE.exists():
            try:
                import json as _json
                return _json.loads(self._TEACH_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"topics": [], "last_topic": None, "last_keywords": []}

    def _save_teach_history(self, data: dict):
        import json as _json
        self._TEACH_FILE.parent.mkdir(exist_ok=True)
        self._TEACH_FILE.write_text(
            _json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def _cmd_teach(self, topic: str) -> str:
        if not topic:
            return "Provide a topic: /teach <topic>"

        prompt = (
            f"You are a clear, engaging teacher. Teach me about: {topic}\n\n"
            f"Structure your lesson EXACTLY like this (use these headings):\n\n"
            f"## What is {topic}?\n"
            f"<2–3 sentence plain-English explanation>\n\n"
            f"## Core Concepts\n"
            f"<3–5 bullet points covering the fundamentals>\n\n"
            f"## Example\n"
            f"<one concrete, easy-to-follow example — use code if relevant>\n\n"
            f"## Common Mistakes\n"
            f"<2–3 pitfalls beginners hit>\n\n"
            f"## Keywords to explore next\n"
            f"<comma-separated list of 4–6 related subtopics the learner can type "
            f"after '/teach' to go deeper>\n\n"
            f"Keep the whole lesson concise but complete. "
            f"Use markdown formatting for readability."
        )

        messages = [{"role": "user", "content": prompt}]
        show_info(f"Teaching: {topic}...")
        raw = self._ask_llm(messages)

        # Extract suggested keywords from the "Keywords to explore" section
        keywords: list[str] = []
        in_kw = False
        for line in raw.splitlines():
            if "keywords to explore" in line.lower():
                in_kw = True
                continue
            if in_kw and line.strip():
                keywords = [k.strip().strip("*_`") for k in line.split(",") if k.strip()]
                break

        # Persist to study history
        data = self._load_teach_history()
        entry = {"topic": topic, "date": datetime.now().strftime("%Y-%m-%d")}
        if entry not in data["topics"]:
            data["topics"].append(entry)
        data["last_topic"] = topic
        data["last_keywords"] = keywords
        self._save_teach_history(data)

        if not self._printed:
            # Non-streaming provider: render with full formatting
            console.print(f"\n[bold cyan]Lesson: {topic}[/bold cyan]")
            console.print(Markdown(raw))
            self._printed = True

        # Always print keyword suggestions (short, additive)
        if keywords:
            kw_str = "  ".join(f"[cyan]/teach {k}[/cyan]" for k in keywords[:5])
            show_info(f"Explore next: {kw_str}")

        return raw

    def _cmd_teach_quiz(self) -> str:
        data = self._load_teach_history()
        topic = data.get("last_topic")
        if not topic:
            return "No lesson on record yet. Start with: /teach <topic>"

        prompt = (
            f"Create a 5-question quiz on: {topic}\n\n"
            f"Format each question like this:\n"
            f"Q1. <question>\n"
            f"a) <option>  b) <option>  c) <option>  d) <option>\n"
            f"Answer: <letter>) <correct answer>\n\n"
            f"Mix multiple-choice and short-answer questions. "
            f"Cover different aspects of the topic. No extra commentary."
        )
        show_info(f"Generating quiz on {topic}...")
        raw = self._ask_llm([{"role": "user", "content": prompt}])
        if not self._printed:
            console.print(f"\n[bold cyan]Quiz: {topic}[/bold cyan]\n")
            console.print(Markdown(raw))
            self._printed = True
        return raw

    def _cmd_teach_topics(self) -> str:
        data = self._load_teach_history()
        topics = data.get("topics", [])
        if not topics:
            return "No topics studied yet. Start with: /teach <topic>"
        lines = ["Topics you've studied:\n"]
        for i, entry in enumerate(topics, 1):
            lines.append(f"  {i:2}. {entry['topic']}  ({entry.get('date', '')})")
        last = data.get("last_topic")
        if last:
            kws = data.get("last_keywords", [])
            lines.append(f"\nLast lesson: {last}")
            if kws:
                lines.append(f"Suggested next: {', '.join(kws)}")
        return "\n".join(lines)

    def _cmd_teach_reset(self) -> str:
        self._save_teach_history({"topics": [], "last_topic": None, "last_keywords": []})
        return "Study history cleared."

    # ── Calendar ─────────────────────────────────────────────────────────

    def _cmd_cal_setup(self) -> str:
        creds = BASE.parent / "credentials.json"
        return (
            "Google Calendar setup:\n"
            "  1. Go to https://console.cloud.google.com/\n"
            "  2. Create a project → APIs & Services → Enable 'Google Calendar API'\n"
            "  3. Credentials → + Create Credentials → OAuth 2.0 Client ID\n"
            "     Application type: Desktop app\n"
            "  4. Download the JSON → save it as:\n"
            f"     {creds}\n"
            "  5. Run /calendar — a browser tab opens for one-time login.\n"
            "     Token is cached; you won't be asked again."
        )

    def _cal_ready(self) -> str | None:
        """Return an error string only if credentials.json is missing."""
        from skills.calendar_gcal import CREDS_FILE
        if not CREDS_FILE.exists():
            return "Google Calendar not set up. Run /calendar setup for instructions."
        return None

    def _cmd_cal_list(self, days: int) -> str:
        err = self._cal_ready()
        if err:
            return err
        try:
            from skills.calendar_gcal import format_events, list_events
            events = list_events(days=days)
            return format_events(events, header=f"Upcoming {days} days:\n")
        except Exception as e:
            return f"Calendar error: {e}"

    def _cmd_cal_today(self) -> str:
        err = self._cal_ready()
        if err:
            return err
        try:
            from skills.calendar_gcal import format_events, list_today
            events = list_today()
            return format_events(events, header="Today's events:\n")
        except Exception as e:
            return f"Calendar error: {e}"

    def _cmd_cal_add(self, text: str) -> str:
        if not text:
            return "Usage: /calendar add <natural language description>\nExample: /calendar add dentist tomorrow at 2pm for 1 hour"
        err = self._cal_ready()
        if err:
            return err
        try:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
            prompt = (
                f"Today is {now_str}.\n"
                f"Parse this calendar event request and reply ONLY in this exact format:\n"
                f"SUMMARY: <title>\n"
                f"DATE: <YYYY-MM-DD>\n"
                f"TIME: <HH:MM>   (24h)\n"
                f"DURATION: <minutes>\n"
                f"DESCRIPTION: <optional, blank if none>\n"
                f"LOCATION: <optional, blank if none>\n\n"
                f"Request: {text}"
            )
            raw = self._ask_llm([{"role": "user", "content": prompt}])
            self._printed = False

            fields = {}
            for line in raw.splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    fields[k.strip().upper()] = v.strip()

            summary  = fields.get("SUMMARY", text)
            date_str = fields.get("DATE", "")
            time_str = fields.get("TIME", "09:00")
            duration = int(fields.get("DURATION", "60") or "60")
            desc     = fields.get("DESCRIPTION", "")
            location = fields.get("LOCATION", "")

            if not date_str:
                return "Could not parse a date from your request. Try: /calendar add meeting 2026-04-25 at 3pm"

            from datetime import timedelta
            start = datetime.fromisoformat(f"{date_str}T{time_str}:00")
            end   = start + timedelta(minutes=duration)

            from skills.calendar_gcal import create_event
            ev = create_event(summary, start, end, description=desc, location=location)
            link = ev.get("htmlLink", "")
            return (
                f"Event created: {summary}\n"
                f"  {start.strftime('%a %b %d at %I:%M %p')} → {end.strftime('%I:%M %p')}"
                + (f"\n  {link}" if link else "")
            )
        except FileNotFoundError as e:
            return str(e)
        except Exception as e:
            return f"Could not create event: {e}"

    def _cmd_cal_delete(self, event_id: str) -> str:
        if not event_id:
            return "Usage: /calendar delete <event-id>\nGet IDs from /calendar"
        err = self._cal_ready()
        if err:
            return err
        try:
            from skills.calendar_gcal import delete_event
            delete_event(event_id)
            return f"Event {event_id} deleted."
        except Exception as e:
            return f"Could not delete event: {e}"

    # ── Agent system ──────────────────────────────────────────────────────

    def _cmd_agent(self, arg: str) -> str:
        if arg == "list":
            from skills.agent import list_agent_types
            return list_agent_types()
        if arg == "history":
            from skills.agent import list_agent_history
            return list_agent_history()
        if arg == "status":
            from skills.agent import active_agent_status
            return active_agent_status()
        parts = arg.split(None, 1)
        if len(parts) < 2:
            return "Usage: /agent <type> <task>\nTypes: explorer  coder  planner  debugger  orchestrator"
        agent_type, task = parts[0].lower(), parts[1]

        # Background mode: /agent background <type> <task>
        if agent_type == "background":
            bg_parts = task.split(None, 1)
            if len(bg_parts) < 2:
                return "Usage: /agent background <type> <task>"
            bg_type, bg_task = bg_parts[0].lower(), bg_parts[1]
            from skills.agent import AGENT_PERSONAS, Agent
            if bg_type not in AGENT_PERSONAS:
                return f"Unknown agent type '{bg_type}'. Choose: {', '.join(AGENT_PERSONAS)}"
            bg_agent = Agent(bg_type, self._ask_llm)
            console.print(f"[bold cyan]Spawning [bold]{bg_type}[/bold] agent in background...[/bold cyan]")
            bg_agent.run_async(bg_task)
            return f"Agent '{bg_type}' running in background."

        from skills.agent import AGENT_PERSONAS
        if agent_type == "auto":
            from skills.agent import detect_agent_type
            detected = detect_agent_type(task)
            if detected is None:
                return "Query seems simple — no agent needed. Try /prompt or ask directly."
            console.print(f"[bold cyan]Auto-detected: [bold]{detected}[/bold] agent[/bold cyan]")
            agent_type = detected
        elif agent_type not in AGENT_PERSONAS:
            return f"Unknown agent type '{agent_type}'. Choose: {', '.join(AGENT_PERSONAS)}"

        from skills.agent import Agent
        agent = Agent(agent_type, self._ask_llm)

        console.print(f"[bold cyan]Spawning {agent_type} agent...[/bold cyan]")
        show_info(f"Task: {task[:100]}")
        with Progress(
            SpinnerColumn(),
            TextColumn(f"[cyan]{agent_type} agent working...[/cyan]"),
            transient=True, console=console,
        ) as prog:
            prog.add_task("", total=None)
            result = agent.run(task)
        console.print(f"[bold green]{agent_type} agent done[/bold green] "
                      f"({result.elapsed:.1f}s, {result.tool_calls} tool calls)")
        if result.sub_agent_results:
            for sr in result.sub_agent_results:
                show_info(f"↳ spawned {sr.agent_type} ({sr.elapsed:.1f}s)")
        return str(result)

    # ── Password management ───────────────────────────────────────────────

    def _cmd_password(self, new_pw: str) -> str:
        import getpass
        from core_files.auth import has_password, set_password, verify_password
        if has_password():
            current = getpass.getpass("Current password: ")
            if not verify_password(current):
                return "Incorrect password. No changes made."
        if not new_pw:
            new_pw = getpass.getpass("New password: ")
            confirm = getpass.getpass("Confirm password: ")
            if new_pw != confirm:
                return "Passwords do not match. No changes made."
        set_password(new_pw)
        return "Password updated. Hash stored in .env."

    def _cmd_password_clear(self) -> str:
        import getpass
        from core_files.auth import clear_password, has_password, verify_password
        if not has_password():
            return "No password is currently set."
        current = getpass.getpass("Current password: ")
        if not verify_password(current):
            return "Incorrect password. No changes made."
        clear_password()
        return "Password removed."

    # ── Slide / PDF generation ────────────────────────────────────────────

    def _parse_sections(self, topic: str, num_slides: int = 4) -> tuple[str, list]:
        """Use LLM to generate structured slide content."""
        prompt = (
            f"Create a {num_slides}-slide presentation on: {topic}\n\n"
            f"Respond ONLY in this exact format (no extra text):\n"
            f"TITLE: <presentation title>\n"
            f"SLIDE: <heading>\n"
            f"- <bullet point>\n"
            f"- <bullet point>\n"
            f"- <bullet point>\n"
            f"SLIDE: <next heading>\n"
            f"- ...\n"
            f"(repeat for all {num_slides} slides)"
        )
        messages = [{"role": "user", "content": prompt}]
        raw = self._ask_llm(messages)
        self._printed = False

        title = topic
        sections = []
        current = None
        for line in raw.splitlines():
            line = line.strip()
            if line.startswith("TITLE:"):
                title = line[6:].strip()
            elif line.startswith("SLIDE:"):
                if current:
                    sections.append(current)
                current = {"heading": line[6:].strip(), "bullets": []}
            elif line.startswith("- ") and current:
                current["bullets"].append(line[2:].strip())
        if current:
            sections.append(current)

        if not sections:
            sections = [{"heading": topic, "bullets": [raw[:300]]}]

        return title, sections

    def _cmd_slides(self, topic: str) -> str:
        if not topic:
            return "Usage: /slides <topic>"
        theme = self.config.get("slide_theme", "dark")
        show_info(f"Generating slides on '{topic}' (theme: {theme})...")
        try:
            title, sections = self._parse_sections(topic)
            from skills.slides import generate_slides
            out = generate_slides(title, sections, theme=theme)
            from core_files.platform import open_file
            open_file(str(out))
            return f"Slides saved: {out.name}  (theme: {theme})"
        except Exception as e:
            return f"Slide generation failed: {e}"

    def _cmd_pdf(self, topic: str) -> str:
        if not topic:
            return "Usage: /pdf <topic>"
        theme = self.config.get("pdf_theme", "light")
        show_info(f"Generating PDF on '{topic}' (theme: {theme})...")
        try:
            title, sections = self._parse_sections(topic)
            from skills.pdf_gen import generate_pdf
            out = generate_pdf(title, sections, theme=theme)
            from core_files.platform import open_file
            open_file(str(out))
            return f"PDF saved: {out.name}  (theme: {theme})"
        except Exception as e:
            return f"PDF generation failed: {e}"

    # ── Morning briefing ─────────────────────────────────────────────────

    def _cmd_morning(self) -> str:
        now = datetime.now()
        hour = now.hour
        greeting = (
            "Good morning" if hour < 12
            else "Good afternoon" if hour < 17
            else "Good evening"
        )
        parts = [f"{greeting}! Here's your briefing for {now.strftime('%A, %B %d')}.\n"]

        # Weather
        try:
            r = requests.get(
                "https://wttr.in/?format=3",
                headers={"User-Agent": "curl/7.0"},
                timeout=(4, 8),
            )
            parts.append(f"Weather: {r.text.strip()}")
        except Exception:
            pass

        # Calendar (only if already authenticated)
        from skills.calendar_gcal import TOKEN_FILE
        if TOKEN_FILE.exists():
            try:
                from skills.calendar_gcal import format_events, list_today
                events = list_today()
                if events:
                    parts.append(f"\nCalendar:\n{format_events(events)}")
                else:
                    parts.append("Calendar: No events today.")
            except Exception:
                parts.append("Calendar: unavailable (run /calendar setup).")
        else:
            parts.append("Calendar: not connected (run /calendar setup).")

        # Pending todos
        todos    = self._load_todos()
        pending  = [t for t in todos if not t.get("done")]
        if pending:
            lines = "\n".join(f"  - {t['task']}" for t in pending[:5])
            extra = f"\n  ...and {len(pending) - 5} more" if len(pending) > 5 else ""
            parts.append(f"\nTodos ({len(pending)} pending):\n{lines}{extra}")
        else:
            parts.append("Todos: all clear!")

        return "\n".join(parts)

    # ── Proactive check ───────────────────────────────────────────────────

    def _cmd_check(self) -> str:
        today  = datetime.now().date()
        todos  = self._load_todos()
        pending = [t for t in todos if not t.get("done")]
        parts  = []

        overdue = []
        for t in pending:
            try:
                age = (today - datetime.strptime(t["added"], "%Y-%m-%d").date()).days
                if age > 7:
                    overdue.append((t, age))
            except Exception:
                pass

        if overdue:
            lines = "\n".join(
                f"  - {t['task']}  ({age}d old)" for t, age in overdue
            )
            parts.append(f"Overdue (>7 days, {len(overdue)} items):\n{lines}")

        parts.append(
            f"\nTodos: {len(pending)} pending / {len(todos)} total."
            if todos else "Todos: none on record."
        )

        from skills.calendar_gcal import TOKEN_FILE
        if TOKEN_FILE.exists():
            try:
                from skills.calendar_gcal import format_events, list_events
                events = list_events(days=2)
                if events:
                    parts.append(f"\nNext 2 days:\n{format_events(events)}")
                else:
                    parts.append("Calendar: nothing in the next 2 days.")
            except Exception:
                pass

        return "\n".join(parts)

    # ── User memory ───────────────────────────────────────────────────────

    _MEMORY_FILE = BASE / "functionalities" / "memories.md"

    def _cmd_remember(self, fact: str) -> str:
        if not fact:
            return "Usage: /remember <fact>"
        self._MEMORY_FILE.parent.mkdir(exist_ok=True)
        ts   = datetime.now().strftime("%Y-%m-%d")
        text = (
            self._MEMORY_FILE.read_text(encoding="utf-8")
            if self._MEMORY_FILE.exists() else ""
        )
        text += f"- [{ts}] {fact}\n"
        self._MEMORY_FILE.write_text(text, encoding="utf-8")
        return f"Remembered: {fact}"

    def _cmd_memories(self) -> str:
        if not self._MEMORY_FILE.exists():
            return "No memories yet. Add one: /remember <fact>"
        text = self._MEMORY_FILE.read_text(encoding="utf-8").strip()
        return f"Memories:\n{text}" if text else "No memories yet."

    def _cmd_forget(self, query: str) -> str:
        if not self._MEMORY_FILE.exists():
            return "No memories to forget."
        lines   = [l for l in self._MEMORY_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]
        removed = [l for l in lines if query.lower() in l.lower()]
        kept    = [l for l in lines if query.lower() not in l.lower()]
        if not removed:
            return f"No memories matching '{query}'."
        self._MEMORY_FILE.write_text("\n".join(kept) + "\n", encoding="utf-8")
        return f"Forgot {len(removed)} entr{'y' if len(removed)==1 else 'ies'} matching '{query}'."

    # ── Language auto-detection ───────────────────────────────────────────

    def _cmd_lang(self, arg: str) -> str:
        if arg == "auto":
            self.config.set("auto_lang", True)
            return "Auto-language ON — Pixel will respond in whatever language you write in."
        if arg == "off":
            self.config.set("auto_lang", False)
            return "Auto-language OFF."
        return "Usage: /lang auto  |  /lang off  |  /lang learn <language>  |  /lang vocab <language>"

    # ── Language learning commands ────────────────────────────────────────

    def _cmd_lang_learn(self, lang: str) -> str:
        """Interactive language learning session — lesson + drill."""
        if not lang:
            return "Usage: /lang learn <language>  e.g. /lang learn Spanish"
        from skills.language import build_lesson_prompt, run_drill_session, LANG_CODE
        lang_name = lang.title()
        console.print(f"[bold cyan]Starting {lang_name} learning session...[/bold cyan]")
        # First, AI lesson on core vocabulary
        topic = "greetings and basics"
        prompt = build_lesson_prompt(lang, topic, level="beginner")
        lesson = self._ask_llm([{"role": "user", "content": prompt}])
        console.print(Markdown(lesson))
        self._printed = True
        # Then a quick vocab drill
        console.print(f"\n[bold yellow]Now let's practice! Starting a vocabulary drill...[/bold yellow]")
        drill_result = run_drill_session(lang.lower(), topic="greetings", count=5)
        console.print(drill_result)
        return f"Session complete! Use '/lang lesson {lang} <topic>' for more topics, or '/lang vocab {lang}' for more drills."

    def _cmd_lang_vocab(self, lang: str, topic: str = "all") -> str:
        """Vocabulary flashcard drill."""
        if not lang:
            return "Usage: /lang vocab <language> [topic]\nTopics: greetings · numbers · phrases · days · colors"
        from skills.language import run_drill_session
        console.print(f"[bold cyan]Starting vocabulary drill: {lang.title()} — {topic}[/bold cyan]\n")
        result = run_drill_session(lang.lower(), topic=topic, count=8)
        console.print(result)
        self._printed = True
        return f"Drill complete! Try '/lang progress' to see your stats."

    def _cmd_lang_lesson(self, lang: str, topic: str) -> str:
        """AI-tutor structured lesson."""
        if not lang or not topic:
            return "Usage: /lang lesson <language> <topic>  e.g. /lang lesson French past tense"
        from skills.language import build_lesson_prompt
        level = "beginner"
        prompt = build_lesson_prompt(lang, topic, level=level)
        show_info(f"Generating {lang.title()} lesson on '{topic}'...")
        result = self._ask_llm([{"role": "user", "content": prompt}])
        if not self._printed:
            console.print(Markdown(result))
            self._printed = True
        return result

    def _cmd_lang_conversation(self, lang: str, scene: str) -> str:
        """AI conversation partner roleplay."""
        if not lang:
            return "Usage: /lang conversation <language> [scenario]  e.g. /lang conversation Japanese at a restaurant"
        from skills.language import build_conversation_prompt
        prompt = build_conversation_prompt(lang, scene)
        show_info(f"Setting up conversation practice in {lang.title()}...")
        result = self._ask_llm([{"role": "user", "content": prompt}])
        if not self._printed:
            console.print(Markdown(result))
            self._printed = True
        return result

    def _cmd_lang_progress(self) -> str:
        """Show language learning progress."""
        from skills.language import progress_report
        report = progress_report()
        console.print(report)
        self._printed = True
        return report

    def _cmd_lang_download(self, lang: str) -> str:
        """Download offline translation pack for a language."""
        if not lang:
            return "Usage: /lang download <language>  e.g. /lang download Spanish"
        from skills.language import download_offline_pack
        show_info(f"Downloading offline pack for {lang.title()}...")
        result = download_offline_pack(lang)
        console.print(result)
        self._printed = True
        return result

    def _cmd_lang_offline(self) -> str:
        """Show installed offline translation packs."""
        from skills.language import check_offline_status
        result = check_offline_status()
        console.print(result)
        self._printed = True
        return result

    # ── Wikipedia ────────────────────────────────────────────────────────

    def _cmd_wiki(self, topic: str) -> str:
        if not topic:
            return "Usage: /wiki <topic>"
        try:
            r = requests.get(
                "https://en.wikipedia.org/api/rest_v1/page/summary/"
                + urllib.parse.quote(topic, safe=""),
                headers={"User-Agent": "PixelAssistant/1.0"},
                timeout=10,
            )
            if r.status_code == 404:
                return f"No Wikipedia article found for '{topic}'."
            d       = r.json()
            title   = d.get("title", topic)
            extract = d.get("extract", "No summary available.")
            url     = d.get("content_urls", {}).get("desktop", {}).get("page", "")
            result  = f"**{title}**\n\n{extract}"
            if url:
                result += f"\n\n<{url}>"
            console.print(Markdown(result))
            self._printed = True
            return result
        except Exception as e:
            return f"Wikipedia error: {e}"

    # ── Code generation ──────────────────────────────────────────────────

    def _cmd_code(self, task: str) -> str:
        if not task:
            return "Usage: /code <task>  e.g. /code binary search in Python"
        prompt = (
            f"Write clean, working code for: {task}\n\n"
            f"- Detect the language from context; default to Python if ambiguous\n"
            f"- Add a one-line comment at the top explaining what it does\n"
            f"- Wrap in a markdown fenced code block with the correct language tag\n"
            f"- No preamble or explanation outside the code block"
        )
        result = self._ask_llm([{"role": "user", "content": prompt}])
        if not self._printed:
            console.print(Markdown(result))
            self._printed = True
        return result

    # ── Pomodoro timer ───────────────────────────────────────────────────

    def _cmd_pomodoro(self, arg: str) -> str:
        work_min, break_min = 25, 5
        if arg:
            parts = arg.split("/")
            try:
                work_min  = int(parts[0])
                break_min = int(parts[1]) if len(parts) > 1 else 5
            except ValueError:
                return "Usage: /pomodoro [work/break]  e.g. /pomodoro 25/5"

        def _run():
            for cycle in range(1, 5):
                console.print(
                    f"\n[bold green]Pomodoro #{cycle} -- {work_min} min work[/bold green]"
                )
                time.sleep(work_min * 60)
                from core_files.platform import play_beep
                play_beep()
                if cycle < 4:
                    console.print(
                        f"[bold yellow]Break -- {break_min} min[/bold yellow]"
                    )
                    time.sleep(break_min * 60)
                    from core_files.platform import play_beep
                    play_beep()
                else:
                    console.print(
                        "[bold cyan]Session complete! Take a long break.[/bold cyan]"
                    )

        threading.Thread(target=_run, daemon=True).start()
        return f"Pomodoro started: {work_min}min work / {break_min}min break × 4 cycles."

    # ── Clipboard copy ───────────────────────────────────────────────────

    def _cmd_clip(self) -> str:
        last = next(
            (m["content"] for m in reversed(self.history) if m["role"] == "assistant"),
            None,
        )
        if not last:
            return "No assistant response in history to copy."
        try:
            import pyperclip
            pyperclip.copy(last)
            return f"Copied to clipboard ({len(last)} chars)."
        except ImportError:
            pass
        try:
            import subprocess as _sp
            _sp.run(["clip"], input=last.encode("utf-8"), check=True)
            return f"Copied to clipboard ({len(last)} chars)."
        except Exception as e:
            return f"Clipboard error: {e}\nInstall pyperclip for cross-platform support: pip install pyperclip"

    # ── Journal ──────────────────────────────────────────────────────────

    _JOURNAL_FILE = BASE / "functionalities" / "journal.md"

    def _cmd_journal(self, entry: str) -> str:
        today = datetime.now().strftime("%Y-%m-%d")
        if not entry:
            if not self._JOURNAL_FILE.exists():
                return "No journal entries yet.  Add one: /journal <text>"
            lines = self._JOURNAL_FILE.read_text(encoding="utf-8").splitlines()
            in_today: bool = False
            today_lines: list[str] = []
            for line in lines:
                if line.startswith(f"## {today}"):
                    in_today = True
                elif line.startswith("## ") and in_today:
                    break
                elif in_today:
                    today_lines.append(line)
            if not today_lines:
                return f"No entries for today ({today}).  Add one: /journal <text>"
            return f"Journal — {today}:\n" + "\n".join(today_lines)

        self._JOURNAL_FILE.parent.mkdir(exist_ok=True)
        ts   = datetime.now().strftime("%H:%M")
        text = (
            self._JOURNAL_FILE.read_text(encoding="utf-8")
            if self._JOURNAL_FILE.exists()
            else ""
        )
        if f"## {today}" not in text:
            text += f"\n## {today}\n"
        text += f"- {ts}  {entry}\n"
        self._JOURNAL_FILE.write_text(text, encoding="utf-8")
        return f"Journal entry saved at {ts}."

    def _cmd_status(self) -> str:
        model = self.config.smart_model if self.config.get("smart_mode") else self.config.model
        show_table("Status", ["Setting", "Value"], [
            ("Provider", self.provider),
            ("Model", f"{model}{' [smart]' if self.config.get('smart_mode') else ''}"),
            ("History", f"{len(self.history)//2} turns (max {self.config.max_history})"),
            ("Voice", "on" if self.voice else "off"),
            ("Debug", "on" if self.debug else "off"),
            ("Logging", "on" if self.config.log_conversations else "off"),
        ], border_style=C_PRIMARY)
        self._printed = True
        return "\n".join(f"{k}: {v}" for k, v in [
            ("Provider", self.provider),
            ("Model", model),
            ("History", len(self.history)//2),
            ("Voice", "on" if self.voice else "off"),
            ("Debug", "on" if self.debug else "off"),
            ("Logging", "on" if self.config.log_conversations else "off"),
        ])

    def _help_text(self) -> str:
        text = (
            "─── Commands ────────────────────────────────────────\n"
            "  /help                       this message\n"
            "  /status                     show current config\n"
            "  /models                     list available models\n"
            "  /smart                      toggle 70B smart model\n"
            "\n"
            "─── Conversation ────────────────────────────────────\n"
            "  /history                    show last 20 turns\n"
            "  /clear                      wipe conversation history\n"
            "\n"
            "─── Config ──────────────────────────────────────────\n"
            "  /set provider <groq|gemini|mistral>\n"
            "  /set model <model-name>\n"
            "  /set persona <text>         update system prompt\n"
            "  /set <key> <value>          edit any config.yaml key\n"
            "\n"
            "─── Tools ───────────────────────────────────────────\n"
            "  /calc <expr>                calculator  e.g. /calc 2**10\n"
            "  /weather [city]             current weather\n"
            "  /remind <time> <msg>        reminder  e.g. /remind 10min stretch\n"
            "  /run <python code>          run a Python snippet\n"
            "  /open <path>                open a file or folder\n"
            "  /sys                        CPU / RAM / disk usage\n"
            "  /note <text>                save a note\n"
            "  /notes                      list all notes (numbered)\n"
            "  /note delete <n>            delete note by number\n"
            "  /note delete last           delete the most recent note\n"
            "  /note search <keyword>      search notes\n"
            "  /note clear                 delete all notes\n"
            "  /email <description>        draft an email with AI\n"
            "  /speak <text>               read text aloud (TTS)\n"
            "  /conversation               start a voice conversation\n"
            "  /wiki <topic>               Wikipedia summary\n"
            "  /code <task>                generate code for a task\n"
            "  /pomodoro [work/break]      Pomodoro timer (default 25/5 × 4)\n"
            "  /clip                       copy last reply to clipboard\n"
            "  /journal [entry]            append to / view today's journal\n"
            "\n"
            "─── Proactive ───────────────────────────────────────\n"
            "  /morning                    daily briefing: weather + calendar + todos\n"
            "  /check                      review overdue tasks and upcoming events\n"
            "\n"
            "─── Memory ──────────────────────────────────────────\n"
            "  /remember <fact>            persist a fact about you into context\n"
            "  /memories                   show all remembered facts\n"
            "  /forget <keyword>           remove memories matching keyword\n"
            "\n"
            "─── Language & Translation ──────────────────────────\n"
            "  /translate <lang> <text>             quick translation\n"
            "  /translate --explain <lang> <text>   full breakdown: pronunciation, alternatives, grammar\n"
            "  /translate file <lang> <path>        translate a text file\n"
            "  /lang learn <language>               interactive lesson + vocabulary drill\n"
            "  /lang vocab <language> [topic]       flashcard drill  (topics: greetings numbers phrases days colors)\n"
            "  /lang lesson <language> <topic>      structured AI-tutor lesson\n"
            "  /lang conversation <language> [scene]  conversation roleplay practice\n"
            "  /lang progress                       your stats across all languages\n"
            "  /lang download <language>            download argostranslate offline pack\n"
            "  /lang offline                        show installed offline packs\n"
            "  /lang auto                           auto-detect language, respond in kind\n"
            "  /lang off                            always respond in English\n"
            "\n"
            "─── Media ───────────────────────────────────────────\n"
            "  generate an image of <desc>   free image generation\n"
            "  generate a video of <desc>    free video generation\n"
            "  search for <query>            web search\n"
            "\n"
            "─── Direct LLM ──────────────────────────────────────\n"
            "  /prompt <text>             send text straight to LLM (no shortcuts)\n"
            "  /prompt --bare <text>      no persona, no history\n"
            "  /prompt --system <sp> | <msg>  custom system prompt + message\n"
            "\n"
            "─── Learning ────────────────────────────────────────\n"
            "  /teach <topic>             structured lesson on any topic\n"
            "  /teach quiz                quiz on the last lesson\n"
            "  /teach topics              list everything you've studied\n"
            "  /teach reset               clear study history\n"
            "\n"
            "─── Calendar ────────────────────────────────────────\n"
            "  /calendar                   upcoming events (7 days)\n"
            "  /calendar today             today's events\n"
            "  /calendar add <desc>        add event (natural language)\n"
            "  /calendar delete <id>       delete event by ID\n"
            "  /calendar setup             show Google Calendar setup guide\n"
            "  e.g. /calendar add dentist friday at 10am for 1 hour\n"
            "\n"
            "─── Documents ───────────────────────────────────────\n"
            "  /slides <topic>             generate a .pptx presentation\n"
            "  /pdf <topic>               generate a themed PDF\n"
            "  /themes                    list themes & current settings\n"
            "  /set slide_theme <name>    set slide theme\n"
            "  /set pdf_theme <name>      set PDF theme\n"
            "  themes: dark  light  corporate  modern  warm\n"
            "\n"
            "─── Security ────────────────────────────────────────\n"
            "  /password <new-pw>          set or change startup password\n"
            "  /password clear             remove startup password\n"
            "  /security audit             scan all open ports for risks\n"
            "  /security fix               block all high/medium risk ports\n"
            "  /security fix <port>        block a specific port (requires admin)\n"
            "  /encrypt aes <pw> <text>    AES-256 encrypt text\n"
            "  /encrypt xor <key> <text>   XOR cipher\n"
            "  /encrypt caesar <n> <text>  Caesar cipher (shift n)\n"
            "  /encrypt vigenere <k> <t>   Vigenère cipher\n"
            "  /encrypt file <pw> <path>   encrypt a file\n"
            "  /decrypt <method> <k> <ct>  decrypt (same methods as encrypt)\n"
            "  /hash [algo] <text>         hash text  (default sha256)\n"
            "  /stego hide <img> <msg>     hide a message inside an image (LSB)\n"
            "  /stego hide <img> <pw> <m>  hide AES-encrypted message\n"
            "  /stego reveal <img> [pw]    extract hidden message from image\n"
            "  /stego capacity <img>       show how much an image can hold\n"
            "\n"
            "─── Pixel Ecosystem ─────────────────────────────────\n"
            "  /web                        open Pixel Assistant web UI (http://localhost:8000)\n"
            "  /pixel                      list all Pixel apps and their status\n"
            "  /pixel <app>                launch a Pixel app\n"
            "  Apps: pixelcode · pixel-assistant · pixel-game · pixel-teacher · fun-games\n"
            "\n"
            "─── Utilities ───────────────────────────────────────\n"
            "  /news [topic]               latest news headlines\n"
            "  /convert <v> <from> to <to>  currency conversion\n"
            "  /qr <text>                  generate a QR code image\n"
            "  /regex <pattern> <text>      test a regex pattern\n"
            "  /ip                         show your public IP address\n"
            "  /ping <host>                ping a hostname or IP\n"
            "  /diff <a> | <b>             compare two texts\n"
            "  /encode base64|url|hex <t>   encode text\n"
            "  /decode base64|url|hex <t>   decode text\n"
            "  /uuid [n]                   generate UUID(s)\n"
            "  /lorem [n]                  generate lorem ipsum paragraph(s)\n"
            "  /flip <text>                flip text upside down\n"
            "  /ascii <text>               ASCII art banner\n"
            "\n"
            "─── Agents ──────────────────────────────────────────\n"
            "  /agent <type> <task>         spawn an agent (explorer|coder|planner|debugger|orchestrator)\n"
            "  /agent auto <task>          auto-detect best agent type for this task\n"
            "  /agent background <type> <task>  run agent in background\n"
            "  /agent status               show running agents\n"
            "  /agent list                 show available agent types\n"
            "  /agent history              show past agent runs\n"
            "\n"
            "─── Self-update ─────────────────────────────────────\n"
            "  /update debug               scan source; find + auto-fix real bugs\n"
            "  /update upgrade             implement next planned feature\n"
            "  /update full                debug pass then upgrade pass\n"
            "  /update check               scan and report bugs (no auto-fix)\n"
            "  /update feature <desc>      generate + apply a new command\n"
            "  /update skill <desc>        generate a new skill module (in src/skills/)\n"
            "  /update fix <desc>          generate + apply a targeted bug fix\n"
            "  /update planned             show planned features list\n"
            "  /update log                 update history\n"
            "  /update rollback            restore last backup of main.py\n"
            "\n"
            "  exit / quit                 close Pixel\n"
            "─────────────────────────────────────────────────────"
        )
        show_help_panel(text)
        self._printed = True
        return text

    # ── Security commands ─────────────────────────────────────────────────

    def _cmd_security_audit(self) -> str:
        from security import audit_ports, format_audit_report
        show_info("Scanning open ports...")
        audit = audit_ports()
        report = format_audit_report(audit)
        console.print(report)
        self._printed = True
        return report

    def _cmd_security_fix(self) -> str:
        from security import audit_ports, fix_security
        show_info("Scanning ports...")
        audit = audit_ports()
        if not audit.get("risks"):
            return "No high/medium/unknown risks found. Your firewall looks clean."
        show_info(f"Blocking {len(audit['risks'])} risky port(s)...")
        lines = fix_security(audit)
        result = "\n".join(lines)
        console.print(result)
        self._printed = True
        return result

    def _cmd_security_fix_port(self, arg: str) -> str:
        from security import fix_port
        parts = arg.split("/", 1)
        try:
            port = int(parts[0].strip())
        except ValueError:
            return f"Invalid port: {arg!r}. Usage: /security fix <port>[/proto]"
        proto = parts[1].strip().lower() if len(parts) > 1 else "tcp"
        result = fix_port(port, proto)
        console.print(result)
        self._printed = True
        return result

    # ── Steganography commands ────────────────────────────────────────────

    def _cmd_stego(self, arg: str) -> str:
        parts = arg.split(None, 1)
        if not parts:
            return "Usage: /stego hide|reveal|capacity ..."
        sub = parts[0].lower()
        rest = parts[1] if len(parts) > 1 else ""

        from security import stego_capacity, stego_hide, stego_reveal

        if sub == "capacity":
            if not rest:
                return "Usage: /stego capacity <image_path>"
            result = stego_capacity(rest.strip())
            console.print(result)
            self._printed = True
            return result

        if sub == "hide":
            # /stego hide <path> <message>           — no encryption
            # /stego hide <path> <password> <message> — encrypted (3+ tokens)
            tokens = rest.split(None, 2)
            if len(tokens) < 2:
                return "Usage: /stego hide <image> <message>  OR  /stego hide <image> <password> <message>"
            if len(tokens) == 2:
                path, message, password = tokens[0], tokens[1], ""
            else:
                path, password, message = tokens[0], tokens[1], tokens[2]
            result = stego_hide(path, message, password)
            console.print(result)
            self._printed = True
            return result

        if sub == "reveal":
            tokens = rest.split(None, 1)
            if not tokens:
                return "Usage: /stego reveal <image> [password]"
            path = tokens[0]
            password = tokens[1] if len(tokens) > 1 else ""
            result = stego_reveal(path, password)
            console.print(f"[bold cyan]Hidden message:[/bold cyan] {result}")
            self._printed = True
            return result

        return f"Unknown subcommand '{sub}'. Use: hide  reveal  capacity"

    # ── Encryption commands ────────────────────────────────────────────────

    def _cmd_encrypt(self, arg: str) -> str:
        parts = arg.split(None, 2)
        if len(parts) < 3:
            return "Usage: /encrypt <method> <key> <text|path>"
        method, key, text = parts[0].lower(), parts[1], parts[2]
        from security import (
            encrypt_aes, encrypt_caesar, encrypt_file, encrypt_vigenere, encrypt_xor,
        )
        if method == "aes":
            return encrypt_aes(text, key)
        if method == "xor":
            return encrypt_xor(text, key)
        if method == "caesar":
            try:
                shift = int(key)
            except ValueError:
                return "Caesar cipher key must be an integer shift (e.g. /encrypt caesar 13 hello)"
            return encrypt_caesar(text, shift)
        if method == "vigenere":
            return encrypt_vigenere(text, key)
        if method == "file":
            return encrypt_file(text, key)
        return f"Unknown method '{method}'. Use: aes  xor  caesar  vigenere  file"

    def _cmd_decrypt(self, arg: str) -> str:
        parts = arg.split(None, 2)
        if len(parts) < 3:
            return "Usage: /decrypt <method> <key> <ciphertext|path>"
        method, key, text = parts[0].lower(), parts[1], parts[2]
        from security import (
            decrypt_aes, decrypt_caesar, decrypt_file, decrypt_vigenere, decrypt_xor,
        )
        if method == "aes":
            return decrypt_aes(text, key)
        if method == "xor":
            return decrypt_xor(text, key)
        if method == "caesar":
            try:
                shift = int(key)
            except ValueError:
                return "Caesar cipher key must be an integer shift."
            return decrypt_caesar(text, shift)
        if method == "vigenere":
            return decrypt_vigenere(text, key)
        if method == "file":
            return decrypt_file(text, key)
        return f"Unknown method '{method}'. Use: aes  xor  caesar  vigenere  file"

    def _cmd_hash(self, arg: str) -> str:
        from security import hash_text
        ALGOS = {"md5", "sha1", "sha224", "sha256", "sha384", "sha512", "blake2b", "blake2s"}
        parts = arg.split(None, 1)
        if len(parts) == 2 and parts[0].lower().replace("-", "") in ALGOS:
            algo, text = parts[0], parts[1]
        else:
            algo, text = "sha256", arg
        return hash_text(text, algo)

    # ── New commands ─────────────────────────────────────────────────────

    def _cmd_news(self, topic: str | None) -> str:
        query = topic or "latest news"
        try:
            results = Search(f"{query} news").search(max_results=5)
            return f"News — {query}:\n{results}"
        except Exception as e:
            return f"News unavailable: {e}"

    def _cmd_convert(self, arg: str) -> str:
        parts = arg.split()
        if len(parts) < 4 or parts[2].lower() not in ("to", "in"):
            return "Usage: /convert <value> <from> to <to>  e.g. /convert 100 usd to eur"
        try:
            value = float(parts[0])
        except ValueError:
            return f"Invalid number: {parts[0]}"
        from_unit = parts[1].lower()
        to_unit = parts[3].lower()
        r = requests.get(
            f"https://api.exchangerate-api.com/v4/latest/{from_unit.upper()}",
            timeout=10,
        )
        if r.status_code == 200:
            rates = r.json().get("rates", {})
            target = to_unit.upper()
            if target in rates:
                converted = value * rates[target]
                return f"{value} {from_unit.upper()} = {converted:.2f} {target}"
            return f"Unknown currency: {to_unit}"
        return f"Conversion unavailable (status {r.status_code})."

    def _cmd_qr(self, text: str) -> str:
        if not text:
            return "Usage: /qr <text>  — generate a QR code image"
        try:
            import qrcode
            img = qrcode.make(text)
            out = Path.home() / f"pixel_qr_{int(time.time())}.png"
            img.save(out)
            from core_files.platform import open_file
            open_file(str(out))
            return f"QR code saved: {out.name}"
        except ImportError:
            return "Install qrcode: pip install qrcode[pil]"

    def _cmd_regex(self, arg: str) -> str:
        parts = arg.split(None, 1)
        if len(parts) < 2:
            return "Usage: /regex <pattern> <text>  — test a regex against text"
        from skills.text_tools import test_regex
        return test_regex(parts[0], parts[1])

    def _cmd_ip(self) -> str:
        from skills.net_tools import get_public_ip
        return get_public_ip()

    def _cmd_ping(self, host: str) -> str:
        if not host:
            return "Usage: /ping <hostname or IP>"
        from skills.net_tools import ping_host
        return ping_host(host)

    def _cmd_diff(self, arg: str) -> str:
        if " | " not in arg:
            return "Usage: /diff <text1> | <text2>  — compare two strings"
        from skills.text_tools import text_diff
        a, b = arg.split(" | ", 1)
        return text_diff(a, b)

    def _cmd_encode(self, arg: str) -> str:
        parts = arg.split(None, 1)
        if len(parts) < 2:
            return "Usage: /encode <method> <text>  methods: base64  url  hex"
        from skills.text_tools import encode_text
        return encode_text(parts[0], parts[1])

    def _cmd_decode(self, arg: str) -> str:
        parts = arg.split(None, 1)
        if len(parts) < 2:
            return "Usage: /decode <method> <text>  methods: base64  url  hex"
        from skills.text_tools import decode_text
        return decode_text(parts[0], parts[1])

    def _cmd_uuid(self, count: str) -> str:
        import uuid
        n = 1
        if count.strip().isdigit():
            n = max(1, min(int(count.strip()), 20))
        uuids = [str(uuid.uuid4()) for _ in range(n)]
        return "\n".join(uuids)

    def _cmd_lorem(self, count: str) -> str:
        from skills.text_tools import lorem_ipsum
        n = int(count.strip()) if count.strip().isdigit() else 3
        return lorem_ipsum(n)

    def _cmd_flip(self, text: str) -> str:
        if not text:
            return "Usage: /flip <text>  — flip text upside down"
        from skills.text_tools import flip_text
        return flip_text(text)

    def _cmd_ascii(self, text: str) -> str:
        if not text:
            return "Usage: /ascii <text>  — convert text to ASCII art banner"
        try:
            import pyfiglet
            return pyfiglet.figlet_format(text)
        except ImportError:
            return "Install pyfiglet: pip install pyfiglet"

    # ── LLM calls ─────────────────────────────────────────────────────────

    def _build_messages(self, user_input: str) -> list:
        persona = self.persona

        # Inject persisted user memories
        if self._MEMORY_FILE.exists():
            mem = self._MEMORY_FILE.read_text(encoding="utf-8").strip()
            if mem:
                persona += f"\n\nUser facts & preferences (use these to personalise responses):\n{mem}"

        # Auto-language detection
        if self.config.get("auto_lang"):
            persona += (
                "\nAlways detect the language the user is writing in "
                "and respond entirely in that same language."
            )

        messages = [{"role": "system", "content": persona}]
        messages.extend(self.history[-(self.config.max_history * 2):])
        messages.append({"role": "user", "content": user_input})
        return messages

    def _stream_groq(self, messages: list) -> str:
        model = self.config.smart_model if self.config.get("smart_mode") else self.config.model
        stream = self.groq_client.chat.completions.create(
            model=model, messages=messages, stream=True, temperature=0.7,
        )
        full = ""
        if self.token_callback:
            for chunk in stream:
                token = chunk.choices[0].delta.content or ""
                if token:
                    self.token_callback(token)
                full += token
        else:
            show_streaming_start()
            for chunk in stream:
                token = chunk.choices[0].delta.content or ""
                print(token, end="", flush=True)
                full += token
            show_streaming_end()
        self._printed = True
        return full

    def _call_gemini(self, messages: list) -> str:
        from google.genai import types as _gtypes
        system_msg = next((m["content"] for m in messages if m["role"] == "system"), None)
        chat_msgs = [
            _gtypes.Content(
                role="user" if m["role"] == "user" else "model",
                parts=[_gtypes.Part(text=m["content"])],
            )
            for m in messages if m["role"] != "system"
        ]
        cfg = _gtypes.GenerateContentConfig(system_instruction=system_msg) if system_msg else None
        response = self.gemini.models.generate_content(
            model="gemini-2.0-flash",
            contents=chat_msgs,
            config=cfg,
        )
        return response.text

    def _call_mistral(self, messages: list) -> str:
        return self.mistral.chat.complete(
            model="mistral-small-latest", messages=messages
        ).choices[0].message.content

    def _call_ollama(self, messages: list) -> str:
        try:
            resp = requests.post(
                f"{self.ollama_url}/api/chat",
                json={"model": self.ollama_model, "messages": messages, "stream": False},
                timeout=120,
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"]
        except Exception as e:
            raise RuntimeError(f"Ollama error: {e}")

    def _call_openai(self, messages: list) -> str:
        try:
            resp = requests.post(
                f"{self.openai_base}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.openai_key}",
                    "Content-Type": "application/json",
                },
                json={"model": self.openai_model, "messages": messages},
                timeout=120,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            raise RuntimeError(f"OpenAI error: {e}")

    PROVIDER_CHAIN = ["groq", "gemini", "mistral", "openai", "ollama"]

    def _get_provider_fn(self, provider: str):
        mapping = {
            "groq": self._stream_groq if self.groq_client else None,
            "gemini": self._call_gemini if self.gemini else None,
            "mistral": self._call_mistral if self.mistral else None,
            "openai": self._call_openai if self.openai_key else None,
            "ollama": self._call_ollama,
        }
        return mapping.get(provider)

    def _ask_llm(self, messages: list) -> str:
        chain = [self.provider] + [p for p in self.PROVIDER_CHAIN if p != self.provider]
        errors = []
        for prov in chain:
            fn = self._get_provider_fn(prov)
            if fn is None:
                continue
            try:
                return fn(messages)
            except Exception as e:
                errors.append(f"{prov}: {e}")
                continue
        raise RuntimeError(f"All providers failed: {'; '.join(errors)}")

    # ── Main handler ──────────────────────────────────────────────────────

    def handle_prompt(self, prompt: str) -> str:
        prompt = prompt.strip()
        if not prompt:
            return ""

        self._printed = False

        if self.debug:
            show_info(f"debug: provider={self.provider} "
                      f"model={'smart' if self.config.get('smart_mode') else 'fast'}")

        meta = self._check_meta(prompt)
        if meta is not None:
            return meta

        # Plugin commands (from src/skills/*.py via @command decorator)
        if prompt.startswith("/"):
            pcs = prompt[1:].split(None, 1)
            cmd_name = pcs[0].lower()
            cmd_args = pcs[1] if len(pcs) > 1 else ""
            from skills import dispatch
            plugin_result = dispatch(cmd_name, cmd_args, self)
            if plugin_result is not None:
                return plugin_result

        # Unrecognised slash command → treat as /prompt (send directly to LLM)
        if prompt.startswith("/"):
            show_info("Unknown command — sending to AI...")
            return self._cmd_prompt(prompt.lstrip("/").strip())

        shortcut = self._check_shortcut(prompt)
        if shortcut is not None:
            return shortcut

        # ── Auto-agent routing ────────────────────────────────────────────
        if len(prompt.split()) > 5:
            from skills.agent import auto_route
            auto_result = auto_route(prompt, self)
            if auto_result is not None:
                return auto_result

        messages = self._build_messages(prompt)
        try:
            response = self._ask_llm(messages)
        except Exception as e:
            logger.error(f"LLM error: {e}")
            return f"Error: {e}"

        self.history.append({"role": "user", "content": prompt})
        self.history.append({"role": "assistant", "content": response})
        _save_history(self.history)

        if self.config.log_conversations:
            log_conversation(prompt, response, self.provider)

        return response

    # ── Run loops ─────────────────────────────────────────────────────────

    def run_text(self):
        show_header()

        try:
            import readline
            readline.set_history_length(500)
        except ImportError:
            pass

        while True:
            try:
                user_input = input_styled()
            except (KeyboardInterrupt, EOFError):
                show_farewell()
                break
            if user_input.lower() in ("exit", "quit", "bye"):
                show_farewell()
                break
            if not user_input:
                continue

            show_user_message(user_input)

            response = self.handle_prompt(user_input)

            # Streaming (Groq) already printed; print everything else here
            if response and not self._printed:
                show_response(response)

    def run_voice(self):
        from core_files.tray import set_state

        wake_word = self.config.wake_word.lower()
        from core_files.ui import show_header
        show_header()
        show_info(f"Voice mode — say '{wake_word}' to activate, Ctrl+C to exit")
        activated = False

        while True:
            try:
                set_state("listening")
                text = self.voice.listen(timeout=10, phrase_time_limit=30)
                if not text:
                    activated = False
                    set_state("idle")
                    continue

                if self.debug:
                    show_info(f"heard: {text}")

                if not activated:
                    if wake_word in text.lower():
                        activated = True
                        command = text.lower().replace(wake_word, "").strip()
                        if not command:
                            self.voice.speak("Yes?")
                            continue
                        text = command
                    else:
                        set_state("idle")
                        continue

                set_state("processing")
                show_user_message(text)
                response = self.handle_prompt(text)
                if response and not self._printed:
                    show_response(response)
                set_state("responding")
                self.voice.speak_streaming(response)
                set_state("idle")
                activated = False

            except KeyboardInterrupt:
                show_farewell()
                set_state("idle")
                break
