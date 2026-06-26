"""
Pixel Assistant — Textual TUI.
Professional multi-domain interface with auto-skill creation.
"""
import asyncio
import json
import os
import re
import shutil
import sys
import textwrap
import time
import threading
from datetime import datetime
from pathlib import Path

from rich.text import Text
from rich.markdown import Markdown
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import (
    Container, Horizontal, Vertical, ScrollableContainer,
)
from textual.css.query import NoMatches
from textual.message import Message
from textual.reactive import reactive
from textual.screen import Screen, ModalScreen
from textual.widgets import (
    Button, Header, Footer, Input, Label, ListItem, ListView,
    Markdown as TMarkdown, RichLog, Select, Static, TabbedContent,
    TabPane, TextArea, Tree, LoadingIndicator,
)
from textual.widgets.tree import TreeNode

SRC_DIR = Path(__file__).parent.parent
BASE = SRC_DIR

sys.path.insert(0, str(SRC_DIR))

from core_files.config import Config
from core_files.logger import setup_logger, log_conversation

from skills import load_skills, get_all_commands, LAZY_SKILLS
from skills.__init__ import _COMMANDS, LAZY_SKILLS as _LAZY_SKILLS_SET

logger = setup_logger()


# ── Colour / theme ─────────────────────────────────────────────────────────────

PIXEL_THEME = {
    "primary": "#00ffff",
    "secondary": "#ff00ff",
    "accent": "#00ff88",
    "surface": "#0d1117",
    "panel": "#161b22",
    "text": "#e6edf3",
    "text_muted": "#8b949e",
    "success": "#00ff88",
    "warning": "#ffaa00",
    "error": "#ff3355",
    "user_bg": "#003d1a",
    "assistant_bg": "#0a2a3d",
    "border": "#30363d",
}


# ── Global assistant instance ──────────────────────────────────────────────────

def _create_assistant(provider: str | None = None) -> "PixelAssistant":
    from main import PixelAssistant
    try:
        assistant = PixelAssistant(provider=provider)
    except Exception as e:
        logger.warning(f"Assistant init error (provider clients): {e}")
        # Create assistant with forced safe init
        import types
        assistant = PixelAssistant.__new__(PixelAssistant)
        # Minimal init to make it functional
        from core_files.config import Config
        assistant.config = Config()
        assistant.provider = provider or assistant.config.provider
        assistant.debug = False
        assistant.voice = None
        assistant.token_callback = None
        assistant.history = []
        assistant.persona = "You are Pixel, a helpful AI assistant."
        assistant.shortcuts = {}
        assistant._printed = False
        assistant.ollama_url = "http://localhost:11434"
        assistant.ollama_model = "llama3.2"
        assistant.openai_base = "https://api.openai.com/v1"
        assistant.openai_key = ""
        assistant.openai_model = "gpt-4o-mini"
        assistant.groq_client = None
        assistant.gemini = None
        assistant.mistral = None
        assistant._ask_llm = lambda msgs: "Assistant initialized with limited functionality. Configure an API key."
    return assistant


# ── Helpers ────────────────────────────────────────────────────────────────────

def _command_list_for_domain() -> dict[str, list[dict]]:
    """Group commands by domain."""
    commands = get_all_commands()
    domain_keywords: dict[str, list[str]] = {
        "General":     ["help", "status", "models", "smart", "clear", "history", "prompt", "web"],
        "Notes":       ["note", "notes"],
        "Todos":       ["todo"],
        "Calendar":    ["calendar"],
        "Journal":     ["journal"],
        "Memory":      ["remember", "memories", "forget", "recall"],
        "Timers":      ["timer", "remind", "pomodoro", "check"],
        "Language":    ["translate", "define", "summarize", "teach", "lang"],
        "Files":       ["slides", "pdf", "themes", "qr"],
        "Images":      ["images", "imagesource", "imagine", "gallery", "imgls", "genimg", "draw", "imgsrc", "imgcontext"],
        "Media":       ["image", "video"],
        "Network":     ["ip", "ping", "diff", "encode", "decode", "uuid", "lorem", "flip", "ascii"],
        "Security":    ["encrypt", "decrypt", "hash", "stego", "security"],
        "System":      ["calc", "weather", "wiki", "sys", "run", "open", "speak", "clip", "convert", "news", "regex"],
        "Agents":      ["agent"],
        "IoT":         ["iot"],
        "P2P":         ["p2p"],
        "Self-Update": ["update"],
        "Settings":    ["set"],
        "Email":       ["email"],
    }
    domains: dict[str, list[dict]] = {}
    for domain, prefixes in domain_keywords.items():
        items = []
        for name, entry in commands.items():
            if any(name.startswith(p) for p in prefixes):
                items.append({"name": name, "help": entry.get("help", ""), "aliases": entry.get("aliases", [])})
        if items:
            domains[domain] = items
    domains["All Commands"] = [
        {"name": n, "help": e.get("help", ""), "aliases": e.get("aliases", [])}
        for n, e in commands.items()
    ]
    return domains


DOMAIN_ICONS: dict[str, str] = {
    "Chat":        "",
    "Skills":      "",
    "Notes":       "",
    "Todos":       "",
    "Calendar":    "",
    "Journal":     "",
    "Memory":      "",
    "Timers":      "",
    "Language":    "",
    "Files":       "",
    "Images":      "🖼️",
    "Media":       "",
    "Network":     "",
    "Security":    "",
    "System":      "",
    "Agents":      "",
    "IoT":         "",
    "P2P":         "",
    "Self-Update": "",
    "Settings":    "",
    "Email":       "",
    "General":     "",
    "All Commands":"",
}


# ── Widgets ────────────────────────────────────────────────────────────────────

class StatusBar(Static):
    """Top status bar showing provider, model, connection."""

    def on_mount(self):
        self._provider = "groq"
        self._model = "openai/gpt-oss-20b"
        self._smart = False
        self._skills_count = 0
        self._uptime = "0:00:00"
        self._last_cleanup = 0.0
        self.styles.height = 1
        self.set_interval(30, self._tick)
        self._tick()
        self._render()

    def set_provider(self, val: str):
        self._provider = val
        self._render()
    def set_model(self, val: str):
        self._model = val
        self._render()
    def set_smart(self, val: bool):
        self._smart = val
        self._render()
    def set_skills_count(self, val: int):
        self._skills_count = val
        self._render()

    def _cleanup_caches(self):
        import shutil
        src_dir = Path(__file__).parent.parent
        for root_dir in [src_dir, src_dir.parent / "tests"]:
            for p in list(root_dir.rglob("__pycache__")):
                if p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)
            for p in list(root_dir.rglob("*.pyc")):
                if p.is_file():
                    try: p.unlink()
                    except Exception: pass

    def _tick(self):
        if hasattr(self.app, "_start_time"):
            elapsed = time.time() - self.app._start_time
            h, r = divmod(int(elapsed), 3600)
            m, s = divmod(r, 60)
            self._uptime = f"{h:02d}:{m:02d}:{s:02d}"
            self._render()
            # Clean caches every 5 minutes
            if elapsed - self._last_cleanup > 300:
                self._last_cleanup = elapsed
                self._cleanup_caches()

    def _render(self):
        smart_mark = " SMART" if self._smart else ""
        parts = (
            f" Pixel Assistant "
            f"│ {self._provider.upper()} "
            f"│ {self._model}{smart_mark} "
            f"│ skills: {self._skills_count} "
            f"│ uptime: {self._uptime} "
        )
        self.update(parts)


class DomainSidebar(Static):
    """Left sidebar with domain navigation."""

    class DomainSelected(Message):
        def __init__(self, domain: str):
            super().__init__()
            self.domain = domain

    def compose(self) -> ComposeResult:
        yield Static(" [bold]DOMAINS[/]", id="sidebar-title")
        yield ListView(id="domain-list")

    def on_mount(self):
        domains = [
            "Chat", "Skills", "Notes", "Todos", "Calendar",
            "System", "Agents", "Screen", "Meetings", "Files",
            "Images", "Network", "Security",
            "Language", "Memory", "IoT", "P2P", "Settings",
        ]
        list_view = self.query_one("#domain-list", ListView)
        for d in domains:
            icon = DOMAIN_ICONS.get(d, " ")
            list_view.append(ListItem(Label(f"{icon} {d}"), id=f"dom-{d.lower()}"))
        list_view.index = 0
        self.styles.width = 20

    def on_list_view_selected(self, event: ListView.Selected):
        if event.item:
            label = event.item.query_one(Label).render()
            domain = label.plain.strip()
            self.post_message(self.DomainSelected(domain))


class ChatMessage(Static):
    """A single chat message bubble."""

    def __init__(self, role: str, content: str, timing: str = ""):
        super().__init__()
        self._role = role
        self._content = content
        self._timing = timing

    def on_mount(self):
        is_user = self._role == "user"
        bg = PIXEL_THEME["user_bg"] if is_user else PIXEL_THEME["assistant_bg"]
        border = PIXEL_THEME["accent"] if is_user else PIXEL_THEME["primary"]
        label = "You" if is_user else "Pixel Assistant"
        ts = datetime.now().strftime("%H:%M")
        self.styles.margin = (0, 1)
        self.styles.padding = (0, 1)
        try:
            md = Markdown(self._content)
            html = str(md)
            self.update(html)
        except Exception:
            self.update(self._content)


class ChatView(ScrollableContainer):
    """Scrollable chat area."""

    def add_message(self, role: str, content: str, timing: str = ""):
        msg = ChatMessage(role, content, timing)
        self.mount(msg)
        self.scroll_end(animate=False)


class SkillItem(Static):
    """A skill with status indicator."""

    def __init__(self, name: str, help_text: str, status: str = "loaded"):
        super().__init__()
        self._name = name
        self._help = help_text
        self._status = status

    def on_mount(self):
        icon = "" if self._status == "loaded" else ""
        color = PIXEL_THEME["success"] if self._status == "loaded" else PIXEL_THEME["warning"]
        content = f"[{color}]{icon}[/] [bold]{self._name}[/]  [dim]{self._help[:60]}[/dim]"
        self.update(content)
        self.styles.margin = (0, 0, 0, 0)
        self.styles.padding = (0, 1)


class SkillsScreen(ScrollableContainer):
    """Skills browser and manager."""

    def compose(self) -> ComposeResult:
        yield Static(" [bold]Skills & Commands[/]", classes="panel-title")
        yield Static("All loaded skills and commands. Use [bold]/update skill <description>[/] to create new ones.", classes="panel-subtitle")
        yield Static("", id="skills-content")

    def on_mount(self):
        self.refresh_skills()

    def refresh_skills(self):
        container = self.query_one("#skills-content", Static)
        commands = get_all_commands()
        domains = _command_list_for_domain()
        lines = []
        for domain, items in domains.items():
            if not items or domain == "All Commands":
                continue
            lines.append(f"\n[bold underline]{domain}[/]  ({len(items)} commands)")
            for cmd in items:
                aliases = f" [dim]({', '.join(cmd['aliases'])})[/dim]" if cmd.get("aliases") else ""
                help_text = cmd["help"][:80] if cmd["help"] else ""
                lines.append(f"  [cyan]/{cmd['name']}[/]  {help_text}{aliases}")
        if not lines:
            lines = ["No skills loaded."]
        container.update("\n".join(lines))


class NotesPanel(ScrollableContainer):
    """Notes CRUD."""

    def compose(self) -> ComposeResult:
        yield Static(" [bold]Notes[/]", classes="panel-title")
        yield Input(placeholder="Add a note... (Enter to save)", id="note-input")
        yield Static("", id="notes-list")

    def on_mount(self):
        self.load_notes()

    def load_notes(self):
        notes_file = BASE / "functionalities" / "notes.txt"
        container = self.query_one("#notes-list", Static)
        if notes_file.exists():
            notes = notes_file.read_text(encoding="utf-8").strip()
            if notes:
                lines = []
                for i, note in enumerate(notes.split("\n"), 1):
                    lines.append(f"  [dim]{i}.[/] {note}")
                container.update("\n".join(lines))
            else:
                container.update("[dim]No notes yet.[/dim]")
        else:
            container.update("[dim]No notes yet.[/dim]")

    def on_input_submitted(self, event: Input.Submitted):
        if event.value.strip():
            notes_file = BASE / "functionalities" / "notes.txt"
            notes_file.parent.mkdir(exist_ok=True)
            with open(notes_file, "a", encoding="utf-8") as f:
                f.write(event.value.strip() + "\n")
            self.query_one("#note-input", Input).value = ""
            self.load_notes()


class TodoPanel(ScrollableContainer):
    """Todo list."""

    def compose(self) -> ComposeResult:
        yield Static(" [bold]Todos[/]", classes="panel-title")
        yield Input(placeholder="Add a todo... (Enter to save)", id="todo-input")
        yield Static("", id="todos-list")

    def on_mount(self):
        self.load_todos()

    def load_todos(self):
        todos_file = BASE / "functionalities" / "todos.json"
        container = self.query_one("#todos-list", Static)
        if todos_file.exists():
            try:
                todos = json.loads(todos_file.read_text(encoding="utf-8"))
                lines = []
                for i, t in enumerate(todos, 1):
                    status = "[green][/]" if t.get("done") else "[yellow][/]"
                    lines.append(f"  {status} [dim]{i}.[/] {t.get('text', '')}")
                if not lines:
                    lines = ["[dim]No todos yet.[/dim]"]
                container.update("\n".join(lines))
            except Exception:
                container.update("[red]Error loading todos[/red]")
        else:
            container.update("[dim]No todos yet.[/dim]")

    def on_input_submitted(self, event: Input.Submitted):
        if event.value.strip():
            todos_file = BASE / "functionalities" / "todos.json"
            todos_file.parent.mkdir(exist_ok=True)
            todos = []
            if todos_file.exists():
                try:
                    todos = json.loads(todos_file.read_text(encoding="utf-8"))
                except Exception:
                    pass
            todos.append({"text": event.value.strip(), "done": False})
            todos_file.write_text(json.dumps(todos, indent=2), encoding="utf-8")
            self.query_one("#todo-input", Input).value = ""
            self.load_todos()


class SystemMonitorPanel(ScrollableContainer):
    """System vitals."""

    def compose(self) -> ComposeResult:
        yield Static(" [bold]System Monitor[/]", classes="panel-title")
        yield Static("", id="sys-content")
        yield Static("", id="process-content")

    def on_mount(self):
        self.refresh()
        self.set_interval(5, self.refresh)

    def refresh(self):
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=0)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            net = psutil.net_io_counters()
            uptime_sec = time.time() - psutil.boot_time()
            h, r = divmod(int(uptime_sec), 3600)
            m, s = divmod(r, 60)

            sys_text = (
                f"[bold]CPU:[/] {cpu:.1f}% [cyan]{'|' * int(cpu / 5)}[/]\n"
                f"[bold]RAM:[/] {mem.percent:.0f}% ({mem.used // (1024**3)}GB / {mem.total // (1024**3)}GB)\n"
                f"[bold]Disk:[/] {disk.percent:.0f}% ({disk.used // (1024**3)}GB / {disk.total // (1024**3)}GB)\n"
                f"[bold]Net:[/]  ↓{net.bytes_recv // (1024**2)}MB ↑{net.bytes_sent // (1024**2)}MB\n"
                f"[bold]Uptime:[/] {h}h {m}m\n"
            )
            self.query_one("#sys-content", Static).update(sys_text)

            proc_lines = ["[bold underline]Top Processes[/]"]
            for p in sorted(psutil.process_iter(["name", "cpu_percent", "memory_percent"]),
                           key=lambda p: p.info["cpu_percent"] or 0, reverse=True)[:10]:
                name = p.info.get("name", "?")[:20]
                cpu_p = p.info.get("cpu_percent", 0) or 0
                mem_p = p.info.get("memory_percent", 0) or 0
                proc_lines.append(f"  {name:20s} CPU:{cpu_p:5.1f}% MEM:{mem_p:5.1f}%")
            self.query_one("#process-content", Static).update("\n".join(proc_lines))
        except ImportError:
            self.query_one("#sys-content", Static).update("[yellow]psutil not installed[/yellow]")


class AgentPanel(ScrollableContainer):
    """Agent management."""

    def compose(self) -> ComposeResult:
        yield Static(" [bold]Autonomous Agents[/]", classes="panel-title")
        yield Static("", id="agent-content")

    def on_mount(self):
        self.refresh()

    def refresh(self):
        try:
            from skills.agent import list_agent_types
            info = list_agent_types()
            self.query_one("#agent-content", Static).update(info)
        except Exception as e:
            self.query_one("#agent-content", Static).update(f"[red]Error: {e}[/red]")


class SettingsPanel(ScrollableContainer):
    """Settings and configuration."""

    def compose(self) -> ComposeResult:
        yield Static(" [bold]Settings[/]", classes="panel-title")
        yield Static("", id="settings-content")

    def on_mount(self):
        self.refresh()

    def refresh(self):
        try:
            cfg = Config()
            lines = [
                f"[bold]Provider:[/] {cfg.provider}",
                f"[bold]Model:[/] {cfg.model}",
                f"[bold]Smart Model:[/] {cfg.smart_model}",
                f"[bold]Smart Mode:[/] {'ON' if cfg.get('smart_mode', False) else 'OFF'}",
                f"[bold]Voice Enabled:[/] {cfg.voice_enabled}",
                f"[bold]TTS Rate:[/] {cfg.tts_rate}",
                f"[bold]TTS Volume:[/] {cfg.tts_volume}",
                f"[bold]Wake Word:[/] {cfg.wake_word}",
                f"[bold]Log Conversations:[/] {cfg.log_conversations}",
                f"[bold]Debug:[/] {cfg.debug}",
                "",
                "[dim]Use /set command in chat to change settings.[/dim]",
            ]
            self.query_one("#settings-content", Static).update("\n".join(lines))
        except Exception as e:
            self.query_one("#settings-content", Static).update(f"[red]Error: {e}[/red]")


class CalendarPanel(ScrollableContainer):
    """Calendar integration — live Google Calendar data."""

    def compose(self) -> ComposeResult:
        yield Static(" [bold]Calendar[/]", classes="panel-title")
        yield Input(placeholder="Search events or /cmd ...", id="cal-input")
        yield Static("", id="calendar-content")

    def on_mount(self):
        self.refresh()
        self.set_interval(60, self.refresh)

    def refresh(self):
        try:
            from skills.calendar_gcal import calendar_list, is_configured
            if not is_configured():
                content = (
                    "[yellow]Google Calendar not configured[/yellow]\n\n"
                    "Run [/cyan]/calendar setup[/] to authenticate with Google.\n"
                    "Place credentials.json in the project root.\n\n"
                    "Once configured, you'll see today's events here."
                )
            else:
                events = calendar_list(max_results=10)
                if events:
                    lines = ["[bold underline]Upcoming Events[/]\n"]
                    for ev in events:
                        start = ev.get("start", {}).get("dateTime", ev.get("start", {}).get("date", "?"))
                        summary = ev.get("summary", "Untitled")
                        lines.append(f"  [cyan]{start[:16]}[/]  {summary}")
                    content = "\n".join(lines)
                else:
                    content = "[dim]No upcoming events found.[/dim]"
        except Exception as e:
            content = (
                "[yellow]Calendar Commands[/yellow]\n\n"
                f"  /calendar today      — today's events\n"
                f"  /calendar add <d> <t> <desc> — add event\n"
                f"  /calendar setup      — configure Google Calendar\n\n"
                f"[dim]Status: {e}[/dim]"
            )
        self.query_one("#calendar-content", Static).update(content)


class ScreenCapturePanel(ScrollableContainer):
    """Screen capture and recording panel."""

    def compose(self) -> ComposeResult:
        yield Static(" [bold]Screen Capture & Recording[/]", classes="panel-title")
        yield Static("", id="screen-content")

    def on_mount(self):
        self.refresh()

    def refresh(self):
        try:
            from skills.screen_capture import list_screenshots, list_recordings, recording_status
            screenshots = list_screenshots(10)
            recordings = list_recordings(5)
            status = recording_status()

            lines = [
                "[bold underline]Status[/]\n",
                f"  {status}",
                "",
                "[bold underline]Commands[/]\n",
                "  /screenshot [full|screen]   — take a screenshot",
                "  /record start [fps] [dur]   — start screen recording (default: 2fps, 60s)",
                "  /record stop                — stop recording and create GIF",
                "  /record status              — check recording state",
                "  /record list                — list past recordings",
                "",
                "[bold underline]Recent Screenshots[/]\n",
                screenshots,
                "",
                "[bold underline]Recent Recordings[/]\n",
                recordings,
            ]
            self.query_one("#screen-content", Static).update("\n".join(lines))
        except Exception as e:
            self.query_one("#screen-content", Static).update(
                f"[yellow]Screen Capture Module[/yellow]\n\n"
                f"  /screenshot       — take a screenshot\n"
                f"  /record start     — start recording\n"
                f"  /record stop      — stop recording\n\n"
                f"[red]Error: {e}[/red]"
            )


class MeetingNotesPanel(ScrollableContainer):
    """Meeting notes and transcription panel."""

    def compose(self) -> ComposeResult:
        yield Static(" [bold]Meeting Notes[/]", classes="panel-title")
        yield Static("", id="meetings-content")

    def on_mount(self):
        self.refresh()
        self.set_interval(5, self.refresh)

    def refresh(self):
        try:
            from skills.meeting_notes import meeting_status, list_meetings
            status = meeting_status()
            meetings = list_meetings(10)

            lines = [
                "[bold underline]Status[/]\n",
                f"  {status}",
                "",
                "[bold underline]Commands[/]\n",
                "  /meeting start [name]        — start live transcription from mic",
                "  /meeting stop                — stop and save meeting notes with AI summary",
                "  /meeting status              — check transcription state",
                "  /meeting list                — list past meetings",
                "  /meeting latest              — show most recent meeting with summary",
                "  /meeting transcribe <file>   — transcribe audio file (WAV/MP3)",
                "",
                "[bold underline]Past Meetings[/]\n",
                meetings,
            ]
            self.query_one("#meetings-content", Static).update("\n".join(lines))
        except Exception as e:
            self.query_one("#meetings-content", Static).update(
                f"[yellow]Meeting Notes Module[/yellow]\n\n"
                f"  /meeting start      — start live meeting notes\n"
                f"  /meeting stop       — stop and save\n"
                f"  /meeting transcribe — transcribe audio file\n\n"
                f"[red]Error: {e}[/red]"
            )


class FileGenPanel(ScrollableContainer):
    """File generation — show generated files."""

    def compose(self) -> ComposeResult:
        yield Static(" [bold]File Generation[/]", classes="panel-title")
        yield Static("", id="filegen-content")

    def on_mount(self):
        self.refresh()
        self.set_interval(30, self.refresh)

    def refresh(self):
        gen_dir = BASE / "generated"
        lines = ["[bold underline]Generated Files[/]\n"]
        if gen_dir.exists():
            files = sorted(gen_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
            if files:
                for f in files[:20]:
                    size = f.stat().st_size
                    lines.append(f"  {f.name:30s} [dim]{size:,} bytes[/dim]")
            else:
                lines.append("[dim]No generated files yet.[/dim]")
        else:
            lines.append("[dim]No generated files yet.[/dim]")

        lines.extend([
            "",
            "[bold]Commands:[/bold]",
            "  /slides <topic>   - PowerPoint presentation",
            "  /pdf <topic>      - PDF document",
            "  /image <prompt>   - AI image generation",
            "  /video <prompt>   - AI video generation",
            "  /qr <text>        - QR code",
        ])
        self.query_one("#filegen-content", Static).update("\n".join(lines))


class ImagesPanel(ScrollableContainer):
    """Local AI image gallery and generation tools."""

    def compose(self) -> ComposeResult:
        yield Static(" [bold]Image Tools[/]", classes="panel-title")
        yield Static("", id="images-content")

    def on_mount(self):
        self.refresh()

    def refresh(self):
        try:
            from skills.image_browser import _get_images, _format_size
            from datetime import datetime
            images = _get_images()
            lines = ["[bold underline]Local AI Images[/]\n"]
            if images:
                for i, img in enumerate(images[:15], 1):
                    mtime = datetime.fromtimestamp(img.stat().st_mtime).strftime("%m-%d %H:%M")
                    sz = _format_size(img.stat().st_size)
                    lines.append(f"  {i:>2}. [bold]{img.stem[:28]}[/] {sz:>8}  {mtime}")
                if len(images) > 15:
                    lines.append(f"\n  ... and {len(images) - 15} more")
            else:
                lines.append("[dim]No images yet. Use /imagine to generate one.[/dim]")

            lines.extend([
                "",
                "[bold underline]Commands[/]\n",
                "  /images [keyword]        — list images",
                "  /images --all            — show all images",
                "  /imagine <prompt>        — generate an AI image",
                "  /imagesource <n/name>    — use image as AI source/context",
            ])
            self.query_one("#images-content", Static).update("\n".join(lines))
        except Exception as e:
            self.query_one("#images-content", Static).update(f"[red]Error: {e}[/red]")


class NetworkPanel(ScrollableContainer):
    """Network tools — live network data."""

    def compose(self) -> ComposeResult:
        yield Static(" [bold]Network Tools[/]", classes="panel-title")
        yield Static("", id="network-content")

    def on_mount(self):
        self.refresh()
        self.set_interval(60, self.refresh)

    def refresh(self):
        try:
            from skills.net_tools import get_public_ip
            ip_info = get_public_ip()
        except Exception:
            ip_info = "[yellow]Could not determine public IP[/yellow]"

        try:
            import socket
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
        except Exception:
            hostname, local_ip = "?", "?"

        lines = [
            "[bold underline]Network Status[/]\n",
            f"[bold]Public IP:[/] {ip_info}",
            f"[bold]Local IP:[/]  {local_ip}",
            f"[bold]Hostname:[/]  {hostname}",
            "",
            "[bold underline]Available Commands[/]\n",
            "  /ip <host>               - Resolve IP",
            "  /ping <host>             - Ping a host",
            "  /diff <f1> <f2>          - Show file diff",
            "  /encode <fmt> <text>     - Base64/hex/rot13/url encode",
            "  /decode <fmt> <text>     - Base64/hex/rot13/url decode",
            "  /uuid                    - Generate UUID v4",
            "  /lorem [n]               - Lorem ipsum generator",
            "  /flip [coin|N]           - Flip coin / roll die",
            "  /ascii <text>            - ASCII art text",
            "  /news                    - Latest headlines",
            "  /regex <pat> <text>      - Test regex pattern",
            "  /convert <val> <from> <to> - Unit converter",
        ]
        self.query_one("#network-content", Static).update("\n".join(lines))


class SecurityPanel(ScrollableContainer):
    """Security tools — live audit status."""

    def compose(self) -> ComposeResult:
        yield Static(" [bold]Security Tools[/]", classes="panel-title")
        yield Button("Run Port Audit", id="sec-audit-btn", variant="primary")
        yield Button("Check Encryption", id="sec-encrypt-btn", variant="default")
        yield Static("", id="security-content")

    def on_mount(self):
        self.refresh()

    def refresh(self):
        lines = [
            "[bold underline]Security Status[/]\n",
            "[bold]Available commands:[/bold]\n",
            "  /security audit          — scan open ports",
            "  /security fix <port>     — block a risky port",
            "  /encrypt <method> <text> — encrypt (aes/xor/caesar/vigenere)",
            "  /decrypt <method> <text> — decrypt",
            "  /hash <text>             — hash text (SHA256/512, etc.)",
            "  /stego <image> <text>    — LSB image steganography",
            "",
            "[dim]Methods: aes (AES-256-GCM), xor, caesar, vigenere[/dim]",
        ]
        self.query_one("#security-content", Static).update("\n".join(lines))

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "sec-audit-btn":
            self._run_audit()
        elif event.button.id == "sec-encrypt-btn":
            self._check_encryption()

    def _run_audit(self):
        try:
            import security as sec
            result = sec.audit_ports()
            self.query_one("#security-content", Static).update(f"[green]Audit result:[/]\n{result[:1000]}")
        except Exception as e:
            self.query_one("#security-content", Static).update(f"[red]Error: {e}[/red]")

    def _check_encryption(self):
        try:
            import security as sec
            ct = sec.encrypt_text("aes", "test Pixel Assistant")
            pt = sec.decrypt_text("aes", ct)
            self.query_one("#security-content", Static).update(
                f"[green]Encryption test successful[/green]\n"
                f"Plaintext: test Pixel Assistant\n"
                f"Ciphertext: {ct[:60]}...\n"
                f"Decrypted: {pt}"
            )
        except Exception as e:
            self.query_one("#security-content", Static).update(f"[red]Error: {e}[/red]")


class MemoryPanel(ScrollableContainer):
    """Memory/RAG — live memory store."""

    def compose(self) -> ComposeResult:
        yield Static(" [bold]Memory & RAG[/]", classes="panel-title")
        yield Input(placeholder="Search memories... (Enter to query)", id="memory-input")
        yield Static("", id="memory-content")

    def on_mount(self):
        self.refresh()
        self.set_interval(15, self.refresh)

    def refresh(self, query: str = ""):
        try:
            from skills.memory import all_memories, recall
            if query:
                results = recall(query, top_k=5)
                if results:
                    lines = [f"[bold]Results for: {query}[/]\n"]
                    for m in results:
                        lines.append(f"  [{m['score']:.2f}] {m['fact'][:120]}")
                else:
                    lines = [f"[dim]No results for '{query}'[/dim]"]
            else:
                mems = all_memories()
                if mems:
                    lines = [f"[bold underline]Stored Memories ({len(mems)})[/]\n"]
                    for m in mems[-20:]:
                        lines.append(f"  [dim]{m['id']}.[/] {m['fact'][:120]}")
                else:
                    lines = ["[dim]No memories stored yet.[/dim]\n\nUse /remember <fact> in chat."]
        except Exception as e:
            lines = [
                "[bold]Memory System[/bold]\n\n"
                "  /remember <fact>   — store a fact\n"
                "  /memories          — list all memories\n"
                "  /recall <query>    — search memories\n"
                "  /forget <keyword>  — remove memories\n\n"
                f"[dim]Status: {e}[/dim]"
            ]
        self.query_one("#memory-content", Static).update("\n".join(lines))

    def on_input_submitted(self, event: Input.Submitted):
        if event.input.id == "memory-input" and event.value.strip():
            self.refresh(query=event.value.strip())


class LanguagePanel(ScrollableContainer):
    """Language tools."""

    def compose(self) -> ComposeResult:
        yield Static(" [bold]Language[/]", classes="panel-title")
        yield Static("", id="language-content")

    def on_mount(self):
        lines = [
            "[bold underline]Language Tools[/]\n",
            "  /translate <lang> <text>           — quick translation",
            "  /translate --explain <lang> <text>  — translate with explanation",
            "  /translate file <lang> <path>       — translate a file",
            "  /define <word>                      — word definition",
            "  /summarize [text]                   — summarize text",
            "  /teach <topic>                      — structured lesson + quiz",
            "  /lang auto                          — auto-detect language",
            "",
            "[dim]Supports all major languages via LLM.[/dim]",
        ]
        self.query_one("#language-content", Static).update("\n".join(lines))


class IoTpanel(ScrollableContainer):
    """IoT device management — live device registry with interactive device controls."""

    def compose(self) -> ComposeResult:
        yield Static(" [bold]IoT Devices[/]", classes="panel-title")
        yield Horizontal(
            Button("Rescan Network", id="iot-rescan-btn", variant="primary"),
            Button("Refresh List", id="iot-refresh-btn", variant="default"),
        )
        yield Static("", id="iot-content")
        yield Static("", id="iot-commands-content")
        yield Static("", id="iot-rules-content")

    def on_mount(self):
        self.refresh()
        self.set_interval(15, self.refresh)

    def refresh(self):
        try:
            from skills.iot import device_list

            devices = device_list()

            # Clean up old device toggle buttons
            for child in list(self.query(".device-toggle-row")):
                child.remove()

            lines = ["[bold underline]Registered Devices[/]\n"]
            if devices:
                for d in devices[:15]:
                    name = d.get("name", d.get("id", "?"))
                    did = d.get("id", "?")
                    dtype = d.get("type", "?")
                    val = d.get("value")
                    val_str = f" = {val}{d.get('unit', '')}" if val is not None else ""
                    lines.append(f"  [bold]{name}[/] ({dtype}){val_str}")
                if len(devices) > 15:
                    lines.append(f"  ... and {len(devices) - 15} more")
            else:
                lines.append("[dim]No devices registered. Use /hue/kasa/ha discover below, or /iot add to register manually.[/dim]")

            self.query_one("#iot-content", Static).update("\n".join(lines))

            # Mount interactive toggle buttons for toggle-able device types
            toggle_types = {"light", "switch", "actuator", "hue_light", "ha_entity"}
            toggle_devices = [d for d in devices if d.get("type", "").lower() in toggle_types]
            for d in toggle_devices[:10]:
                did = d.get("id", "?")
                name = d.get("name", did)
                row = Horizontal(
                    Label(f"  {name[:28]:28s}", classes="device-toggle-row"),
                    Button("ON", id=f"dev-on-{did}", variant="success", classes="device-toggle-row"),
                    Button("OFF", id=f"dev-off-{did}", variant="error", classes="device-toggle-row"),
                    classes="device-toggle-row",
                )
                self.mount(row)

            # Command reference
            cmds = [
                "",
                "[bold underline]Network & IoT Commands[/]",
                "  /iot list                 — list all devices",
                "  /iot add <type> <name>    — add device",
                "  /iot remove <id>          — remove device",
                "  /iot mqtt ...             — MQTT operations",
                "  /iot webhook ...          — webhook server",
                "  /iot rule ...             — rules engine",
                "  /iot discover             — scan LAN for TCP devices",
                "  /ble scan [secs]          — scan for BLE devices",
                "",
                "[bold underline]Real IoT Bridges[/]",
                "  /hue discover             — find Philips Hue bridges",
                "  /hue register <ip>        — register with Hue bridge",
                "  /hue lights               — list Hue lights",
                "  /hue on/off/dim <id>      — control Hue lights",
                "  /kasa discover            — find TP-Link Kasa devices",
                "  /kasa on/off <ip>         — control Kasa devices",
                "  /ha status/entities       — Home Assistant info",
                "  /ha service <d> <s> [eid] — call HA service",
                "  /ssdp                     — UPnP/SSDP device discovery",
                "  /rest get/post <url>      — generic REST API control",
            ]
            self.query_one("#iot-commands-content", Static).update("\n".join(cmds))

            # Rules
            try:
                from skills.iot import rule_list as rl
                rules = rl()
                if isinstance(rules, list) and rules:
                    rlines = ["", "[bold underline]Automation Rules[/]"]
                    for r in rules[:6]:
                        t = r.get("trigger", {})
                        a = r.get("action", {})
                        cond = f"{t.get('condition','')} {t.get('threshold','')}"
                        rlines.append(f"  IF {t.get('device','')} {cond} → {a.get('type','')}")
                    self.query_one("#iot-rules-content", Static).update("\n".join(rlines))
            except Exception:
                pass

        except Exception as e:
            self.query_one("#iot-content", Static).update(
                f"[yellow]IoT Module[/yellow]\n\n"
                f"  /iot list           — list devices\n"
                f"  /iot add <t> <n>    — add device\n"
                f"  /iot on/off <id>   — control\n\n"
                f"[red]Error: {e}[/red]"
            )

    def on_button_pressed(self, event: Button.Pressed):
        btn_id = event.button.id or ""

        if btn_id == "iot-rescan-btn":
            try:
                from skills.iot import device_discover
                result = device_discover()
            except Exception as e:
                result = str(e)
            self.query_one("#iot-content", Static).update(f"[green]Network scan:[/]\n{result}")
            return

        if btn_id == "iot-refresh-btn":
            self.refresh()
            return

        # Device toggle buttons: dev-on-<id> or dev-off-<id>
        if btn_id.startswith("dev-on-") or btn_id.startswith("dev-off-"):
            on = btn_id.startswith("dev-on-")
            did = btn_id[7:]  # strip "dev-on-" or "dev-off-"
            result = self._toggle_device(did, on)
            self.query_one("#iot-content", Static).update(result)
            return

    def _toggle_device(self, device_id: str, on: bool) -> str:
        """Try to toggle a device across all known protocols."""
        # Try iot.py protocol-agnostic on/off
        try:
            from skills.iot import device_list, device_update_value
            devices = device_list()
            target = next((d for d in devices if d.get("id") == device_id), None)
            if target:
                device_update_value(device_id, "on" if on else "off")
                proto = target.get("protocol", "")
                if proto == "hue":
                    from skills.iot_bridge import hue_set_light, _find_hue_bridge
                    bridge = _find_hue_bridge()
                    if bridge:
                        light_id = device_id.replace("hue-", "")
                        return hue_set_light(bridge["ip"], light_id, on=on, username=bridge.get("username", ""))
                elif proto == "kasa":
                    from skills.iot_bridge import kasa_control
                    ip = target.get("ip") or target.get("metadata", {}).get("host", "")
                    if ip:
                        return kasa_control(ip, on=on)
                return f"Device '{device_id}' set to {'on' if on else 'off'} (via registry)."
        except Exception:
            pass

        # Try hue directly
        try:
            from skills.iot_bridge import _find_hue_bridge, hue_set_light
            bridge = _find_hue_bridge()
            if bridge:
                light_id = device_id.replace("hue-", "").split("-")[0]
                return hue_set_light(bridge["ip"], light_id, on=on, username=bridge.get("username", ""))
        except Exception:
            pass

        return f"Could not toggle device '{device_id}'. Use /hue on/off or /kasa on/off for direct control."


class P2PPanel(ScrollableContainer):
    """P2P networking — live peer discovery."""

    def compose(self) -> ComposeResult:
        yield Static(" [bold]P2P Network[/]", classes="panel-title")
        yield Button("Force Discover", id="p2p-discover-btn", variant="primary")
        yield Static("", id="p2p-content")

    def on_mount(self):
        self.refresh()
        self.set_interval(10, self.refresh)

    def refresh(self):
        try:
            from skills.p2p import get_peers, get_status

            peers = get_peers()
            status = get_status()

            lines = ["[bold underline]Peers[/]\n"]
            if peers:
                for p in peers[:20]:
                    name = p.get("hostname", p.get("ip", "?"))
                    ip = p.get("ip", "?")
                    uptime = p.get("uptime", "?")
                    version = p.get("version", "?")
                    lines.append(f"  [green]|[/] [bold]{name}[/] at {ip} [dim](v{version})[/dim]")
            else:
                lines.append("[dim]No peers discovered. Click 'Force Discover' or use /p2p discover[/dim]")

            lines.extend([
                "",
                f"[bold]Status:[/] {status}",
                "",
                "[bold]Commands:[/bold]",
                "  /p2p discover        — scan LAN for peers",
                "  /p2p connect <ip>    — connect to peer",
                "  /p2p disconnect      — disconnect",
                "  /p2p list            — show connected peers",
            ])
            self.query_one("#p2p-content", Static).update("\n".join(lines))
        except Exception as e:
            self.query_one("#p2p-content", Static).update(
                f"[yellow]P2P Networking[/yellow]\n\n"
                f"  /p2p discover        — scan LAN for peers\n"
                f"  /p2p connect <ip>   — connect to peer\n"
                f"  /p2p list            — list peers\n\n"
                f"[red]Error: {e}[/red]"
            )

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "p2p-discover-btn":
            try:
                from skills.p2p import discover_once
                result = discover_once()
                self.query_one("#p2p-content", Static).update(f"[green]Discovery:[/]\n{result[:500]}")
            except Exception as e:
                self.query_one("#p2p-content", Static).update(f"[red]Error: {e}[/red]")


class CreateSkillScreen(ModalScreen):
    """Modal for creating a new skill via AI."""

    def __init__(self):
        super().__init__()
        self._skill_desc = ""
        self._generated = False

    def compose(self) -> ComposeResult:
        yield Container(
            Static(" [bold]Create New Skill[/]", classes="modal-title"),
            Static("Describe the capability you want to add:", id="create-desc-label"),
            Input(placeholder="e.g., a command to fetch stock prices...", id="create-input"),
            Button("Generate with AI", id="create-btn", variant="primary"),
            Button("Cancel", id="create-cancel", variant="default"),
            Static("", id="create-status"),
            id="create-dialog",
        )

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "create-cancel":
            self.dismiss(None)
        elif event.button.id == "create-btn":
            desc = self.query_one("#create-input", Input).value.strip()
            if desc:
                self._skill_desc = desc
                self._generate_skill(desc)

    @work(thread=True)
    def _generate_skill(self, description: str):
        def _update(msg: str):
            self.call_from_thread(self._set_status, msg)

        def _confirm(msg: str) -> bool:
            _update(msg)
            return True

        _update(f"[yellow]Generating skill: {description}...[/yellow]")

        try:
            from skills.self_update import generate_skill
            assistant = _create_assistant()
            result = generate_skill(description, assistant._ask_llm, _confirm)
            _update(f"[green]{result}[/green]")
            self._generated = True
            self.query_one("#create-btn", Button).disabled = True
        except Exception as e:
            _update(f"[red]Error: {e}[/red]")

    def _set_status(self, msg: str):
        self.query_one("#create-status", Static).update(msg)


class HelpScreen(ModalScreen):
    """Help overlay."""

    def compose(self) -> ComposeResult:
        yield Container(
            Static(" [bold]Pixel Assistant TUI Help[/]", classes="modal-title"),
            Static("", id="help-content"),
            Button("Close", id="help-close", variant="primary"),
            id="help-dialog",
        )

    def on_mount(self):
        content = (
            "[bold]Navigation[/bold]\n\n"
            "  [cyan]Tab[/cyan] / [cyan]Shift+Tab[/cyan]  - Move between widgets\n"
            "  [cyan]Up/Down[/cyan]          - Navigate lists\n"
            "  [cyan]Enter[/cyan]              - Select / send message\n"
            "  [cyan]Escape[/cyan]             - Close modals / go back\n\n"
            "[bold]Keyboard Shortcuts[/bold]\n\n"
            "  [cyan]F1[/cyan]                - Help (this screen)\n"
            "  [cyan]F2[/cyan]                - Skills & Commands browser\n"
            "  [cyan]F3[/cyan]                - Create new skill (AI generates the module)\n"
            "  [cyan]F4[/cyan]                - System monitor (CPU, RAM, Disk, Processes)\n"
            "  [cyan]F5[/cyan]                - Settings & Configuration\n"
            "  [cyan]Ctrl+Shift+S[/cyan]      - Take a screenshot instantly\n"
            "  [cyan]Ctrl+Shift+M[/cyan]      - Toggle meeting recording (start/stop live transcription)\n"
            "  [cyan]Ctrl+Shift+V[/cyan]      - Toggle voice assistant (shows tray icon)\n\n"
            "[bold]Chat[/bold]\n\n"
            "  Type a message and press Enter.\n"
            "  Use /command for specific actions.\n"
            "  The AI will auto-route complex tasks to agents.\n\n"
            "[bold]Skills[/bold]\n\n"
            "  Skills are auto-discovered from src/skills/.\n"
            "  Create new skills with [cyan]F3[/cyan] or /update skill <desc>.\n"
            "  The AI can detect missing capabilities and suggest creating them.\n\n"
            "[bold]Tips[/bold]\n\n"
            "  • Type /help for all available commands\n"
            "  • Use /agent auto <task> for complex multi-step tasks\n"
            "  • Skills are lazy-loaded for performance\n"
            "  • Config is in config.yaml\n"
            "  • The system tray icon (F8) gives quick access to screenshot, web UI, and voice controls\n"
        )
        self.query_one("#help-content", Static).update(content)

    def on_button_pressed(self, event: Button.Pressed):
        self.dismiss(None)

    def on_key(self, event):
        if event.key == "escape":
            self.dismiss(None)


# ── Main TUI Screen ────────────────────────────────────────────────────────────

class PixelTUIScreen(Screen):
    """Main TUI screen with sidebar, chat, and panels."""

    BINDINGS = [
        Binding("f1", "show_help", "Help"),
        Binding("f2", "show_skills", "Skills"),
        Binding("f3", "create_skill", "New Skill"),
        Binding("f4", "show_system", "System"),
        Binding("f5", "show_settings", "Settings"),
        Binding("ctrl+shift+s", "screenshot", "Screenshot"),
        Binding("ctrl+shift+m", "meeting_toggle", "Meeting"),
        Binding("ctrl+shift+v", "voice_toggle", "Voice"),
        Binding("ctrl+c", "quit", "Quit"),
    ]

    def __init__(self, assistant=None):
        super().__init__()
        self._assistant = assistant or _create_assistant()
        self._current_domain = "chat"
        self._voice_active = False
        self._voice_tray_thread = None
        self._voice_tray_active = False

    def compose(self) -> ComposeResult:
        yield StatusBar(id="status-bar")
        yield Horizontal(
            DomainSidebar(id="sidebar"),
            Vertical(
                Container(
                    ScrollableContainer(
                        Static(" [bold]Pixel Assistant Chat[/]", classes="panel-title"),
                        ChatView(id="chat-view"),
                        id="chat-container",
                    ),
                    id="chat-screen",
                ),
                Container(
                    SkillsScreen(id="skills-screen"),
                    id="skills-screen-container", classes="hidden",
                ),
                Container(
                    NotesPanel(id="notes-screen"),
                    id="notes-screen-container", classes="hidden",
                ),
                Container(
                    TodoPanel(id="todos-screen"),
                    id="todos-screen-container", classes="hidden",
                ),
                Container(
                    CalendarPanel(id="calendar-screen"),
                    id="calendar-screen-container", classes="hidden",
                ),
                Container(
                    SystemMonitorPanel(id="system-screen"),
                    id="system-screen-container", classes="hidden",
                ),
                Container(
                    AgentPanel(id="agents-screen"),
                    id="agents-screen-container", classes="hidden",
                ),
                Container(
                    ScreenCapturePanel(id="screen-screen"),
                    id="screen-screen-container", classes="hidden",
                ),
                Container(
                    MeetingNotesPanel(id="meetings-screen"),
                    id="meetings-screen-container", classes="hidden",
                ),
                Container(
                    FileGenPanel(id="files-screen"),
                    id="files-screen-container", classes="hidden",
                ),
                Container(
                    ImagesPanel(id="images-screen"),
                    id="images-screen-container", classes="hidden",
                ),
                Container(
                    NetworkPanel(id="network-screen"),
                    id="network-screen-container", classes="hidden",
                ),
                Container(
                    SecurityPanel(id="security-screen"),
                    id="security-screen-container", classes="hidden",
                ),
                Container(
                    LanguagePanel(id="language-screen"),
                    id="language-screen-container", classes="hidden",
                ),
                Container(
                    MemoryPanel(id="memory-screen"),
                    id="memory-screen-container", classes="hidden",
                ),
                Container(
                    IoTpanel(id="iot-screen"),
                    id="iot-screen-container", classes="hidden",
                ),
                Container(
                    P2PPanel(id="p2p-screen"),
                    id="p2p-screen-container", classes="hidden",
                ),
                Container(
                    SettingsPanel(id="settings-screen"),
                    id="settings-screen-container", classes="hidden",
                ),
                id="main-content",
            ),
            id="app-layout",
        )
        yield Input(
            placeholder="Type a message... (/help for commands, F1 for TUI help, Ctrl+Shift+S/M/V for shortcuts)",
            id="chat-input",
        )
        yield Footer()

    def on_mount(self):
        self.app._start_time = time.time()
        self._update_status()
        self._show_welcome()

        # Update skills count
        cmds = get_all_commands()
        sb = self.query_one("#status-bar", StatusBar)
        sb.set_skills_count(len(cmds))

        # Start auto-skill suggestion checker
        self._check_count = 0

    def _show_welcome(self):
        welcome = (
            "**Welcome to Pixel Assistant TUI!**\n\n"
            "I'm your autonomous AI assistant with multiple domains and skills.\n\n"
            "**Quick start:**\n"
            "- Type a message and press Enter to chat\n"
            "- Use **/help** for all available commands\n"
            "- Press **F1** for TUI help\n"
            "- Press **F2** to browse skills\n"
            "- Press **F3** to create a new skill with AI\n"
            "- Use the sidebar to switch between domains\n\n"
            "**Available providers:** Groq, Gemini, Mistral\n"
            f"**Current:** {self._assistant.provider.upper()}\n"
        )
        chat = self.query_one("#chat-view", ChatView)
        chat.add_message("assistant", welcome)

    def _update_status(self):
        sb = self.query_one("#status-bar", StatusBar)
        sb.set_provider(self._assistant.provider)
        model = self._assistant.config.get("smart_model") if self._assistant.config.get("smart_mode") else self._assistant.config.model
        sb.set_model(model)
        sb.set_smart(self._assistant.config.get("smart_mode", False))
        cmds = get_all_commands()
        sb.set_skills_count(len(cmds))

    def _switch_domain(self, domain: str):
        self._current_domain = domain.lower()
        domains = {
            "chat": "chat-screen",
            "skills": "skills-screen-container",
            "notes": "notes-screen-container",
            "todos": "todos-screen-container",
            "calendar": "calendar-screen-container",
            "system": "system-screen-container",
            "agents": "agents-screen-container",
            "screen": "screen-screen-container",
            "meetings": "meetings-screen-container",
            "files": "files-screen-container",
            "images": "images-screen-container",
            "network": "network-screen-container",
            "security": "security-screen-container",
            "language": "language-screen-container",
            "memory": "memory-screen-container",
            "iot": "iot-screen-container",
            "p2p": "p2p-screen-container",
            "settings": "settings-screen-container",
        }
        container_ids = list(domains.values())
        for cid in container_ids:
            try:
                container = self.query_one(f"#{cid}")
                if cid == domains.get(domain.lower(), "chat-screen"):
                    container.remove_class("hidden")
                else:
                    container.add_class("hidden")
            except NoMatches:
                pass

        # Focus appropriate widget
        if domain.lower() == "chat":
            self.query_one("#chat-input", Input).focus()

    def on_domain_sidebar_domain_selected(self, event: DomainSidebar.DomainSelected):
        self._switch_domain(event.domain)

    def on_input_submitted(self, event: Input.Submitted):
        if event.input.id != "chat-input":
            return
        text = event.value.strip()
        if not text:
            return
        self.query_one("#chat-input", Input).value = ""

        chat = self.query_one("#chat-view", ChatView)
        chat.add_message("user", text)

        # Check if this is a /command
        if text.startswith("/"):
            response = self._assistant.handle_prompt(text)
            self._display_response(response, chat)
            return

        # Check if this might need a new skill (auto-skill suggestion)
        if self._should_suggest_skill(text):
            self._check_count += 1

        # Normal chat
        try:
            response = self._assistant.handle_prompt(text)
            self._display_response(response, chat)
        except Exception as e:
            chat.add_message("assistant", f"Error: {e}")
            logger.error(f"TUI error: {e}")

    def _should_suggest_skill(self, text: str) -> bool:
        """Check if user is asking for capability we don't have."""
        commands = get_all_commands()
        cmd_names = list(commands.keys()) + ["help", "status", "clear", "history"]
        # Look for patterns suggesting a missing feature
        missing_patterns = [
            r"(can you|can't|could you|is there a way to)\s+(.+?)\??$",
            r"(how (?:do|can) I)\s+(.+?)\??$",
            r"(i need|i want|i wish|i'd like)\s+(?:a|an|to)\s+(.+?)$",
            r"(is there|do you have|do you support)\s+(.+?)\??$",
        ]
        for pat in missing_patterns:
            m = re.search(pat, text.lower())
            if m:
                return True
        return False

    def _display_response(self, response: str, chat: ChatView):
        if response:
            chat.add_message("assistant", response)
            self._update_status()

    def action_show_help(self):
        self.app.push_screen(HelpScreen())

    def action_show_skills(self):
        self._switch_domain("skills")
        try:
            screen = self.query_one("#skills-screen", SkillsScreen)
            screen.refresh_skills()
        except NoMatches:
            pass

    def action_create_skill(self):
        self.app.push_screen(CreateSkillScreen(), self._on_skill_created)

    def _on_skill_created(self, result):
        if result:
            self._update_status()
            try:
                screen = self.query_one("#skills-screen", SkillsScreen)
                screen.refresh_skills()
            except NoMatches:
                pass

    def action_show_system(self):
        self._switch_domain("system")

    def action_show_settings(self):
        self._switch_domain("settings")
        try:
            screen = self.query_one("#settings-screen", SettingsPanel)
            screen.refresh()
        except NoMatches:
            pass

    @work(thread=True)
    def action_screenshot(self):
        """F6: Take a screenshot via the screen_capture skill."""
        try:
            from skills.screen_capture import capture_screenshot
            result = capture_screenshot()
            self._show_flash(result)
        except Exception as e:
            self._show_flash(f"[red]Screenshot error: {e}[/red]")

    @work(thread=True)
    def action_meeting_toggle(self):
        """F7: Toggle meeting recording on/off."""
        try:
            from skills.meeting_notes import meeting_status, start_listening, stop_listening
            status = meeting_status()
            if "active" in status.lower():
                llm_fn = getattr(self._assistant, "_ask_llm", None)
                result = stop_listening(llm_fn)
            else:
                result = start_listening()
            self._show_flash(result[:200])
        except Exception as e:
            self._show_flash(f"[red]Meeting toggle error: {e}[/red]")

    @work(thread=True)
    def action_voice_toggle(self):
        """F8: Toggle voice assistant on/off and show tray icon."""
        if not hasattr(self, "_voice_active"):
            self._voice_active = False
        if not hasattr(self, "_tray_thread"):
            self._tray_thread = None

        self._voice_active = not self._voice_active
        if self._voice_active:
            self._start_voice_tray()
            self._show_flash("[green]Voice assistant enabled (tray icon active)[/green]")
        else:
            self._stop_voice_tray()
            self._show_flash("[yellow]Voice assistant disabled[/yellow]")

    def _show_flash(self, message: str):
        """Show a brief flash notification in the chat area."""
        try:
            chat = self.query_one("#chat-view", ChatView)
            chat.add_message("system", message)
        except NoMatches:
            pass

    _voice_tray_active = False
    _voice_tray_thread = None

    def _start_voice_tray(self):
        """Start system tray icon with voice toggle capability."""
        if self._voice_tray_active:
            return
        self._voice_tray_active = True
        import threading
        self._voice_tray_thread = threading.Thread(target=_run_tray_loop, daemon=True)
        self._voice_tray_thread.start()

    def _stop_voice_tray(self):
        """Stop the tray icon."""
        global _TRAY_ACTIVE
        _TRAY_ACTIVE = False
        self._voice_tray_active = False
        self._voice_tray_thread = None


# ── System tray icon (pystray) ─────────────────────────────────────────────────

_TRAY_ACTIVE = False

def _run_tray_loop():
    """Run pystray icon with Pixel Assistant branding and voice toggle."""
    global _TRAY_ACTIVE
    _TRAY_ACTIVE = True
    try:
        from PIL import Image, ImageDraw
        import pystray

        # Create a custom Pixel Assistant icon (256x256)
        size = 256
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        # Outer circle
        draw.ellipse([8, 8, size - 8, size - 8], fill=(15, 20, 40, 255))
        # Middle circle
        draw.ellipse([32, 32, size - 32, size - 32], fill=(40, 120, 255, 230))
        # Inner circle (pupil)
        c = int(size * 0.38)
        draw.ellipse([c, c, size - c, size - c], fill=(220, 235, 255, 255))

        icon = pystray.Icon(
            "pixel_assistant",
            img,
            "Pixel Assistant - Voice Active",
            menu=pystray.Menu(
                pystray.MenuItem("Voice: ON", lambda: None, enabled=False),
                pystray.MenuItem("Toggle Voice", lambda: _tray_toggle_voice()),
                pystray.MenuItem("Take Screenshot", lambda: _tray_screenshot()),
                pystray.MenuItem("Open Web UI", lambda: _tray_open_web()),
                pystray.MenuItem("Quit Tray", lambda: _tray_quit()),
            ),
        )
        icon.run()
    except ImportError:
        pass


def _tray_toggle_voice():
    import subprocess
    subprocess.run(["python", "run.py", "tui", "--voice-toggle"], capture_output=True)


def _tray_screenshot():
    try:
        from skills.screen_capture import capture_screenshot
        result = capture_screenshot()
        import subprocess
        subprocess.run(["python", "-c", f"print('{result}')"], capture_output=True)
    except Exception:
        pass


def _tray_open_web():
    import webbrowser
    webbrowser.open("http://localhost:8000")


def _tray_quit():
    global _TRAY_ACTIVE
    _TRAY_ACTIVE = False


# ── Main TUI App ───────────────────────────────────────────────────────────────

class PixelTUI(App):
    """Pixel Assistant Textual TUI Application."""

    CSS = """
    Screen {
        background: #0d1117;
    }

    #status-bar {
        dock: top;
        height: 1;
        background: #161b22;
        color: #8b949e;
        padding: 0 1;
    }

    #app-layout {
        height: 1fr;
    }

    #sidebar {
        width: 24;
        dock: left;
        background: #161b22;
        border-right: solid #30363d;
    }

    #sidebar-title {
        padding: 1;
        text-align: center;
        background: #0d1117;
    }

    #domain-list {
        height: 1fr;
    }

    ListView {
        background: #161b22;
    }

    ListItem {
        padding: 0 1;
    }

    ListItem:hover {
        background: #1c2333;
    }

    ListItem:focus {
        background: #1f2d47;
    }

    #main-content {
        height: 1fr;
    }

    #chat-container {
        height: 100%;
    }

    #chat-view {
        height: 1fr;
        overflow-y: auto;
    }

    #chat-input {
        dock: bottom;
        height: 3;
        background: #161b22;
        border: solid #30363d;
        margin: 0 1;
        padding: 0 1;
    }

    #chat-input:focus {
        border: solid #00ffff;
    }

    ScrollableContainer {
        scrollbar-color: #30363d;
        scrollbar-size-vertical: 1;
    }

    .panel-title {
        padding: 1 2;
        background: #161b22;
        border-bottom: solid #30363d;
        text-style: bold;
    }

    .panel-subtitle {
        padding: 0 2;
        color: #8b949e;
    }

    .hidden {
        display: none;
    }

    #help-dialog, #create-dialog {
        width: 50;
        height: auto;
        min-height: 20;
        background: #161b22;
        border: thick #00ffff;
        padding: 1;
        margin: 2 4;
    }

    .modal-title {
        padding: 1;
        text-style: bold;
        background: #0d1117;
        margin-bottom: 1;
    }

    #create-input {
        margin: 1 0;
    }

    #create-btn, #create-cancel, #help-close {
        margin: 0 1;
    }

    #create-status {
        margin-top: 1;
    }

    #skills-content, #notes-list, #todos-list, #sys-content,
    #process-content, #agent-content, #settings-content,
    #calendar-content, #filegen-content, #network-content,
    #security-content, #memory-content, #language-content,
    #iot-content, #p2p-content, #screen-content, #meetings-content {
        padding: 1 2;
    }

    Input {
        background: #161b22;
        border: solid #30363d;
        color: #e6edf3;
    }

    Input:focus {
        border: solid #00ffff;
    }

    Button {
        background: #1f2d47;
        color: #e6edf3;
    }

    Button:hover {
        background: #2a3a5c;
    }

    Button.primary {
        background: #0066cc;
        color: white;
    }

    Button.primary:hover {
        background: #0077ee;
    }

    Static {
        color: #e6edf3;
    }

    Label {
        color: #e6edf3;
    }

    Footer {
        background: #161b22;
        color: #8b949e;
    }

    Footer > .footer--key {
        color: #00ffff;
    }

    #create-desc-label {
        padding: 0 0 1 0;
        color: #8b949e;
    }
    """

    TITLE = "Pixel Assistant"
    SUB_TITLE = "Autonomous AI Assistant"

    def __init__(self, assistant=None):
        super().__init__()
        self._assistant = assistant or _create_assistant()

    def compose(self) -> ComposeResult:
        yield PixelTUIScreen(assistant=self._assistant)

    def on_screen_resume(self, screen: Screen):
        if isinstance(screen, PixelTUIScreen):
            try:
                screen.query_one("#chat-input", Input).focus()
            except NoMatches:
                pass


def run_tui(assistant=None):
    """Launch the TUI."""
    load_skills()
    app = PixelTUI(assistant=assistant)
    app.run()


if __name__ == "__main__":
    load_skills()
    run_tui()
