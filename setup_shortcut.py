"""
Creates a Pixel Assistant shortcut on the Desktop and pins it to the taskbar.
Run once: python setup_shortcut.py
"""
import ctypes
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    from PIL import Image, ImageDraw
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow", "-q"])
    from PIL import Image, ImageDraw

try:
    import win32com.client
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pywin32", "-q"])
    import win32com.client


# ── Paths ─────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent.resolve()
ICON_PATH    = PROJECT_ROOT / "pixel_icon.ico"

# Default: launch TUI. Change to SCRIPT_TERMINAL for classic CLI.
SCRIPT_TUI  = PROJECT_ROOT / "run.py"       # "python run.py tui"
SCRIPT_TERMINAL = PROJECT_ROOT / "src" / "run.py"  # "python src/run.py"
SCRIPT_PATH = SCRIPT_TUI  # <-- switch here for terminal vs TUI mode


def _get_desktop() -> Path:
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders",
        )
        val, _ = winreg.QueryValueEx(key, "Desktop")
        return Path(val)
    except Exception:
        return Path.home() / "Desktop"


DESKTOP  = _get_desktop()
SHORTCUT = DESKTOP / "Pixel Assistant.lnk"


def _short_path(path: str) -> str:
    """Return the 8.3 short path — no Unicode, safe for COM/WScript."""
    fn = ctypes.windll.kernel32.GetShortPathNameW
    fn.restype = wintypes.DWORD
    n = fn(path, None, 0)
    buf = ctypes.create_unicode_buffer(n)
    fn(path, buf, n)
    return buf.value


# ── 1. Icon ───────────────────────────────────────────────────────────────────

def make_icon():
    sizes = [256, 128, 64, 48, 32, 16]
    frames = []
    for size in sizes:
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        m = size // 8
        d.ellipse([m, m, size - m, size - m], fill=(15, 20, 40, 255))
        i = size // 4
        d.ellipse([i, i, size - i, size - i], fill=(40, 120, 255, 230))
        c = int(size * 0.38)
        d.ellipse([c, c, size - c, size - c], fill=(220, 235, 255, 255))
        frames.append(img)
    frames[0].save(
        ICON_PATH,
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=frames[1:],
    )
    print("  Icon created.")


# ── 2. Shortcut ───────────────────────────────────────────────────────────────

def make_shortcut():
    import shutil

    python   = Path(sys.executable)            # python.exe (has stdin/stdout)
    short_script = _short_path(str(SCRIPT_PATH))
    short_root   = _short_path(str(PROJECT_ROOT))
    short_icon   = _short_path(str(ICON_PATH))

    # Prefer Windows Terminal; fall back to cmd.exe
    wt = shutil.which("wt")

    # Determine launch args based on which script we're using
    if SCRIPT_PATH.name == "run.py":
        script_args = "tui"  # run.py needs a mode argument
    else:
        script_args = ""     # src/run.py has its own arg parser

    if wt:
        target = wt
        args = f'-- "{python}" "{short_script}" {script_args}'
    else:
        target = r"C:\Windows\System32\cmd.exe"
        args = f'/k "{python}" "{short_script}" {script_args}'

    shell = win32com.client.Dispatch("WScript.Shell")
    lnk = shell.CreateShortCut(str(SHORTCUT))
    lnk.TargetPath       = target
    lnk.Arguments        = args
    lnk.WorkingDirectory = short_root
    lnk.IconLocation     = f"{short_icon}, 0"
    lnk.Description      = "Pixel Assistant"
    lnk.WindowStyle      = 1
    lnk.Save()
    print(f"  Shortcut created (using {'Windows Terminal' if wt else 'cmd.exe'}).")


# ── 3. Pin to taskbar ─────────────────────────────────────────────────────────

def pin_to_taskbar():
    desktop_str = str(DESKTOP)
    ps = (
        f'$f = (New-Object -Com Shell.Application).Namespace("{desktop_str}");'
        f'$i = $f.ParseName("Pixel Assistant.lnk");'
        f'$v = $i.Verbs() | Where-Object {{ $_.Name -match "Pin to taskbar" }};'
        f'if ($v) {{ $v.DoIt(); Write-Host "Pinned to taskbar." }}'
        f'else {{ Write-Host "Auto-pin not available — right-click the Desktop shortcut and pin manually." }}'
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
        capture_output=True, text=True,
    )
    msg = (result.stdout + result.stderr).strip()
    print(f"  {msg}" if msg else "  (no output from PowerShell)")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Setting up Pixel Assistant...")
    make_icon()
    make_shortcut()
    pin_to_taskbar()

    # Verify the shortcut reads back correctly
    shell = win32com.client.Dispatch("WScript.Shell")
    lnk = shell.CreateShortCut(str(SHORTCUT))
    print(f"\n  Target : {lnk.TargetPath}")
    print(f"  Args   : {lnk.Arguments}")
    print(f"  Icon   : {lnk.IconLocation}")
    print("\nDone.")
    print("If auto-pin failed: right-click 'Pixel Assistant' on your Desktop → Pin to taskbar.")
