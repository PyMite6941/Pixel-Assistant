"""
Cross-platform utilities: open files, play sounds, copy to clipboard.
Branches on sys.platform to support Windows, macOS, and Linux.
"""
import os
import subprocess
import sys


def open_file(path: str) -> bool:
    """Open a file or URL with the default system application."""
    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return True
    except Exception:
        return False


def play_beep():
    """Play a system alert beep (non-blocking)."""
    try:
        if sys.platform == "win32":
            import winsound
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        elif sys.platform == "darwin":
            subprocess.Popen(["afplay", "/System/Library/Sounds/Ping.aiff"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            print("\a", end="", flush=True)
    except Exception:
        pass


def copy_clipboard(text: str) -> bool:
    """Copy text to system clipboard. Returns True on success."""
    try:
        import pyperclip
        pyperclip.copy(text)
        return True
    except ImportError:
        pass
    try:
        if sys.platform == "win32":
            proc = subprocess.Popen(["clip"], stdin=subprocess.PIPE)
            proc.communicate(text.encode("utf-8"))
            return True
        elif sys.platform == "darwin":
            proc = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
            proc.communicate(text.encode("utf-8"))
            return True
        elif sys.platform == "linux":
            proc = subprocess.Popen(["xclip", "-selection", "clipboard"],
                                    stdin=subprocess.PIPE)
            proc.communicate(text.encode("utf-8"))
            return True
    except Exception:
        pass
    return False
