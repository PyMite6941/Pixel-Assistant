"""
Professional terminal UI for Pixel Assistant.
Styled chat bubbles, headers, input prompts, and status indicators.
"""
import shutil
from datetime import datetime

from rich import box
from rich.align import Align
from rich.console import Console, Group
from rich.rule import Rule
from rich.panel import Panel
from rich.style import Style
from rich.table import Table
from rich.text import Text

console = Console()

C_PRIMARY   = "cyan"
C_USER      = "green"
C_ASSISTANT = "cyan"
C_DIM       = "bright_black"
C_SUCCESS   = "green"
C_WARN      = "yellow"
C_ERROR     = "red"
C_ACCENT    = "magenta"

BOX_STYLE = box.ROUNDED


def _term_width() -> int:
    return min(shutil.get_terminal_size().columns, 88)


def show_header():
    """Professional startup header."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    inner = Table.grid(padding=0)
    inner.add_column(justify="center")
    inner.add_row(Text("Pixel Assistant", style=f"bold {C_PRIMARY}"))
    inner.add_row(Text("Autonomous AI Assistant", style=C_DIM))
    inner.add_row(Text(now, style=C_DIM))
    panel = Panel(
        Align.center(inner),
        box=box.HEAVY,
        border_style=C_PRIMARY,
        padding=(1, 2),
        width=_term_width(),
    )
    console.print()
    console.print(panel)
    console.print()
    return panel


def show_farewell():
    """Styled exit message."""
    text = Text("Goodbye!", style=f"bold {C_ASSISTANT}")
    panel = Panel(
        Align.center(text),
        box=BOX_STYLE,
        border_style=C_DIM,
        padding=(1, 2),
        width=_term_width(),
    )
    console.print()
    console.print(panel)
    console.print()


def show_user_message(text: str):
    """Display a user message bubble with timestamp."""
    ts = datetime.now().strftime("%H:%M")
    label = Text(f" You  {ts} ", style=f"bold white on {C_USER}")
    content = Text(text or "(empty)")
    inner = Panel(
        content,
        title=label,
        title_align="left",
        box=BOX_STYLE,
        border_style=C_USER,
        padding=(1, 2),
        width=_term_width(),
    )
    console.print(inner)
    console.print()


def show_response(text: str, timing: str = ""):
    """Display assistant response with optional timing info."""
    ts = datetime.now().strftime("%H:%M")
    label = Text(f" Pixel Assistant  {ts}", style=f"bold white on {C_ASSISTANT}")
    if timing:
        label.append(f"  {timing}", style=C_DIM)
    content = Text(text or "...")
    inner = Panel(
        content,
        title=label,
        title_align="left",
        box=BOX_STYLE,
        border_style=C_ASSISTANT,
        padding=(1, 2),
        width=_term_width(),
    )
    console.print(inner)
    console.print()


def show_streaming_start():
    """Print a compact prefix line before streaming tokens."""
    ts = datetime.now().strftime("%H:%M")
    label = Text(f" Pixel Assistant  {ts}", style=f"bold white on {C_ASSISTANT}")
    top = Panel(
        "",
        title=label,
        title_align="left",
        box=box.MINIMAL,
        border_style=C_ASSISTANT,
        padding=(0, 2),
        width=_term_width(),
    )
    console.print(top, end="")


def show_streaming_end():
    """Print closing line after streaming finishes."""
    console.print()


def show_info(message: str, style: str = C_DIM, prefix: str = "∙"):
    """Display an info status message."""
    console.print(f"  [{style}]{prefix} {message}[/{style}]")


def show_error(message: str):
    """Display an error message."""
    console.print(f"  [{C_ERROR}]✗ {message}[/{C_ERROR}]")


def show_success(message: str):
    """Display a success message."""
    console.print(f"  [{C_SUCCESS}]✓ {message}[/{C_SUCCESS}]")


def show_warning(message: str):
    """Display a warning message."""
    console.print(f"  [{C_WARN}]⚠ {message}[/{C_WARN}]")


def divider():
    """Print a subtle separator."""
    console.print(Rule(style=C_DIM))


def input_styled(prompt_text: str = "You", show_separator: bool = True) -> str:
    """Styled input prompt."""
    if show_separator:
        divider()
    try:
        return console.input(f"[bold {C_USER}]╰─ {prompt_text} [/bold {C_USER}]").strip()
    except (KeyboardInterrupt, EOFError):
        raise


def show_panel(title: str, content: str, border_style: str = C_DIM):
    """Generic styled panel."""
    panel = Panel(
        Text(content),
        title=Text(title, style=f"bold {border_style}"),
        title_align="left",
        box=BOX_STYLE,
        border_style=border_style,
        padding=(1, 2),
        width=_term_width(),
    )
    console.print(panel)
    console.print()


def show_markdown(title: str, content: str, border_style: str = C_DIM):
    """Styled panel for Markdown content (uses string, Rich Markdown is handled by caller)."""
    panel = Panel(
        content,
        title=Text(title, style=f"bold {border_style}"),
        title_align="left",
        box=BOX_STYLE,
        border_style=border_style,
        padding=(1, 2),
        width=_term_width(),
    )
    console.print(panel)


def show_table(title: str, headers: list, rows: list, border_style: str = C_DIM):
    """Styled table."""
    table = Table(
        title=Text(title, style=f"bold {border_style}"),
        title_justify="left",
        box=BOX_STYLE,
        border_style=border_style,
        width=_term_width(),
    )
    for h in headers:
        table.add_column(h, style="white", header_style=f"bold {border_style}")
    for row in rows:
        table.add_row(*[str(c) for c in row])
    console.print(table)
    console.print()


def show_help_panel(text: str):
    """Styled help display."""
    panel = Panel(
        Text(text, style="white"),
        title=Text(" Help ", style=f"bold white on {C_ACCENT}"),
        title_align="left",
        box=BOX_STYLE,
        border_style=C_ACCENT,
        padding=(1, 2),
        width=_term_width(),
    )
    console.print(panel)
    console.print()
