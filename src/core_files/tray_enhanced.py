"""
Enhanced system tray with global hotkey and quick-search overlay.
Windows-only features gracefully fall back on other platforms.
"""
import sys
import threading
import time
from pathlib import Path

_registered_hotkey = None
_hotkey_callbacks = {}

def register_hotkey(hotkey: str, callback):
    """Register a global hotkey. Uses platform-specific implementation.
    
    Args:
        hotkey: e.g. "ctrl+shift+p"
        callback: function to call when hotkey is pressed
    """
    global _registered_hotkey
    _registered_hotkey = hotkey
    key = hotkey.lower().replace("+", "_")
    _hotkey_callbacks[key] = callback
    
    if sys.platform == "win32":
        _register_hotkey_win32(hotkey, callback)
    else:
        print(f"  [dim]Global hotkey '{hotkey}' requires Windows. On your platform, "
              f"map a keyboard shortcut to: python -m src.scripts.quick_search[/dim]")

def _register_hotkey_win32(hotkey: str, callback):
    """Register global hotkey using Windows API."""
    try:
        import ctypes
        from ctypes import wintypes
        
        VK_MAP = {
            "ctrl": 0x11, "shift": 0x10, "alt": 0x12,
            "p": 0x50, "a": 0x41, "s": 0x53, "d": 0x44, "f": 0x46,
            "g": 0x47, "h": 0x48, "j": 0x4A, "k": 0x4B, "l": 0x4C,
            "space": 0x20, "enter": 0x0D, "escape": 0x1B,
        }
        
        parts = hotkey.lower().split("+")
        if not parts:
            return
        
        fs_mods = 0
        MOD_MAP = {"ctrl": 2, "shift": 4, "alt": 1, "win": 8}
        key_parts = []
        for p in parts:
            if p in MOD_MAP:
                fs_mods |= MOD_MAP[p]
            else:
                key_parts.append(p)
        
        if not key_parts:
            return
        
        vk = VK_MAP.get(key_parts[0], ord(key_parts[0].upper()))
        
        user32 = ctypes.windll.user32
        atom = 0xC001
        
        result = user32.RegisterHotKey(None, atom, fs_mods, vk)
        if not result:
            print(f"  [dim]Could not register hotkey '{hotkey}' (might be in use)[/dim]")
            return
        
        def _hotkey_listener():
            while True:
                msg = ctypes.wintypes.MSG()
                if user32.GetMessageW(ctypes.byref(msg), None, 0, 0):
                    if msg.message == 0x0312:
                        if msg.wParam == atom:
                            callback()
                time.sleep(0.05)
        
        t = threading.Thread(target=_hotkey_listener, daemon=True)
        t.start()
        print(f"  [green]✓ Global hotkey '{hotkey}' registered[/green]")
        
    except Exception as e:
        print(f"  [dim]Hotkey registration failed: {e}[/dim]")


def show_quick_search():
    """Display a quick-search overlay in the terminal."""
    import shutil
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    
    c = Console()
    width = min(shutil.get_terminal_size().columns, 60)
    
    c.clear()
    c.print(Panel(
        "[bold cyan]Quick Search[/bold cyan]\n\n"
        "[dim]Type a command or question, then press Enter.\n"
        "Press Ctrl+C or Escape to cancel.[/dim]",
        width=width, border_style="cyan",
    ))
    
    try:
        query = c.input("[bold green]╰─ Search [/bold green]").strip()
        if query:
            from run import quick_query
            result = quick_query(query)
            c.print(Panel(
                Text(result or "(no result)"),
                title="Result", title_align="left",
                border_style="cyan", width=width,
            ))
            c.input("\n[dim]Press Enter to close...[/dim]")
    except (KeyboardInterrupt, EOFError):
        pass
    
    c.clear()


def start_tray():
    """Start system tray icon with menu options."""
    from core_files.tray import start_tray as _original_tray
    try:
        import PIL.Image
        import pystray
        _start_tray_pystray()
    except ImportError:
        _original_tray()

def _start_tray_pystray():
    """pystray-based system tray icon."""
    try:
        import pystray
        from PIL import Image, ImageDraw
        
        def create_image():
            img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.ellipse([8, 8, 56, 56], fill=(64, 160, 255, 255))
            draw.text((16, 16), "P", fill=(255, 255, 255, 255))
            return img
        
        def on_quit(icon, item):
            icon.stop()
            import os
            os._exit(0)
        
        def on_show(icon, item):
            show_quick_search()
        
        icon = pystray.Icon(
            "pixel",
            create_image(),
            "Pixel Assistant",
            menu=pystray.Menu(
                pystray.MenuItem("Quick Search (Ctrl+Shift+P)", on_show),
                pystray.MenuItem("Quit", on_quit),
            ),
        )
        icon.run()
        
    except ImportError:
        print("[dim]pystray not available. Install: pip install pystray pillow[/dim]")
        from core_files.tray import start_tray as _fallback
        _fallback()
