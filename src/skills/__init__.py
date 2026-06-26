"""
Plugin system for Pixel Assistant.
Skills auto-register via @command decorator — no main.py editing needed.

Usage:
    from skills import command

    @command(name="hello", aliases=["hi", "hey"], help_text="Say hello")
    def cmd_hello(args: str, assistant) -> str:
        return f"Hello! You said: {args}"
"""
import importlib
import pkgutil
import re
from pathlib import Path

_COMMANDS = {}

_ALIAS_MAP = {}

LAZY_SKILLS = {"calendar_gcal", "image_gen", "video_gen", "slides", "pdf_gen", "language", "net_tools", "text_tools", "weather"}
_LAZY_REGISTRY = {}


def command(name: str, aliases: list = None, help_text: str = ""):
    """Decorator: register a function as a /command."""
    def decorator(fn):
        entry = {
            "handler": fn,
            "help": help_text or (fn.__doc__ or "").strip(),
            "aliases": aliases or [],
            "name": name,
        }
        _COMMANDS[name] = entry
        for alias in (aliases or []):
            _ALIAS_MAP[alias] = name
        return fn
    return decorator


def get_command(name: str) -> dict | None:
    if name in _COMMANDS:
        return _COMMANDS[name]
    if name in _ALIAS_MAP:
        return _COMMANDS.get(_ALIAS_MAP[name])
    return None


def get_all_commands() -> dict:
    return dict(_COMMANDS)


def dispatch(name: str, args: str, assistant) -> str | None:
    entry = get_command(name)
    if entry is not None:
        return entry["handler"](args, assistant)
    if _LAZY_REGISTRY:
        import logging as _logging
        for modname in list(_LAZY_REGISTRY.keys()):
            try:
                importlib.import_module(_LAZY_REGISTRY[modname])
            except Exception as e:
                _logging.getLogger(__name__).warning(f"Failed to lazy-load skill '{modname}': {e}")
            del _LAZY_REGISTRY[modname]
        entry = get_command(name)
        if entry is not None:
            return entry["handler"](args, assistant)
    return None


def load_skills():
    """Auto-import every module in src/skills/ so decorators fire.
    Heavy modules (image_gen, video_gen, calendar_gcal, etc.) are deferred
    and loaded on demand when their commands are first dispatched.
    """
    pkg_dir = Path(__file__).parent
    for importer, modname, ispkg in pkgutil.iter_modules([str(pkg_dir)]):
        if modname.startswith("_"):
            continue
        if modname in LAZY_SKILLS:
            _LAZY_REGISTRY[modname] = f"skills.{modname}"
            continue
        try:
            importlib.import_module(f"skills.{modname}")
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                f"Failed to load skill '{modname}': {e}"
            )


def _register_memory_commands():
    """Register memory commands as plugin commands."""
    def _cmd_remember(args, assistant):
        if not args:
            return "Usage: /remember <fact>\nExample: /remember my name is Alice"
        from skills.memory import remember
        return remember(args)

    def _cmd_memories(args, assistant):
        from skills.memory import all_memories
        mems = all_memories()
        if not mems:
            return "No memories yet. Use /remember <fact> to store one."
        lines = ["Your memories:\n"]
        for m in mems[-20:]:
            lines.append(f"  {m['id']}. {m['fact'][:120]}")
        return "\n".join(lines)

    def _cmd_forget(args, assistant):
        if not args:
            return "Usage: /forget <keyword>"
        from skills.memory import forget
        count = forget(args)
        return f"Forgot {count} memory/memories matching '{args}'."

    def _cmd_recall(args, assistant):
        if not args:
            return "Usage: /recall <query>\nSearch your memories for relevant facts."
        from skills.memory import recall
        results = recall(args)
        if not results:
            return f"No memories found matching '{args}'."
        lines = [f"Relevant memories for '{args}':\n"]
        for m in results:
            lines.append(f"  [{m['score']:.2f}] {m['fact'][:120]}")
        return "\n".join(lines)

    for name, handler, aliases, help_text in [
        ("remember", _cmd_remember, [], "Store a fact in long-term memory"),
        ("memories", _cmd_memories, ["memory"], "Show all remembered facts"),
        ("forget", _cmd_forget, [], "Remove memories matching a keyword"),
        ("recall", _cmd_recall, [], "Search memories semantically"),
    ]:
        _COMMANDS[name] = {"handler": handler, "help": help_text, "aliases": aliases, "name": name}
        for alias in aliases:
            _ALIAS_MAP[alias] = name


_register_memory_commands()


def _register_iot_commands():
    """Register IoT commands (lazy import to avoid circular deps)."""
    try:
        from skills.iot import register_commands as _reg
        _reg()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Failed to register IoT commands: {e}")


def _register_system_commands():
    """Register system control commands (lazy import to avoid circular deps)."""
    try:
        from skills.system_control import register_commands as _reg
        _reg()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Failed to register system commands: {e}")


_register_iot_commands()
_register_system_commands()
