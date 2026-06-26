"""
System tray icon for Pixel Assistant.
Uses pystray with run_detached() — non-blocking, runs in its own thread.
CPU usage while idle: ~0% (event-driven, no polling).
"""
from PIL import Image, ImageDraw
import pystray

_icon: pystray.Icon | None = None

_COLORS = {
    "idle":       (180, 180, 180, 120),  # translucent grey
    "listening":  (255, 255, 255, 255),  # bright white
    "processing": (30,  120, 255, 255),  # electric blue
    "responding": (100, 160, 255, 200),  # soft blue
    "error":      (255, 80,  80,  255),  # red
}


def _make_image(state: str = "idle") -> Image.Image:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, 60, 60], fill=_COLORS.get(state, _COLORS["idle"]))
    return img


def set_state(state: str):
    global _icon
    if _icon is not None:
        try:
            _icon.icon = _make_image(state)
        except Exception:
            pass


def start(on_exit=None):
    global _icon

    def _do_exit(icon, item):
        icon.stop()
        if on_exit:
            on_exit()

    menu = pystray.Menu(
        pystray.MenuItem("Pixel Assistant", lambda i, it: None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Exit", _do_exit),
    )
    _icon = pystray.Icon(
        name="PixelAssistant",
        icon=_make_image("idle"),
        title="Pixel Assistant",
        menu=menu,
    )
    _icon.run_detached()
