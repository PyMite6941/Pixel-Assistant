"""
Screen capture and recording for Pixel Assistant.
Screenshots (static) and screen recording (timed frame capture).
Uses Pillow (already in requirements.txt), no heavy deps needed.
"""
import os
import sys
import time
import json
import threading
import subprocess
from datetime import datetime
from pathlib import Path

from PIL import ImageGrab

from skills import command

OUTPUT_DIR = Path(__file__).parent.parent.parent / "generated"
SCREENSHOT_DIR = OUTPUT_DIR / "screenshots"
RECORDING_DIR = OUTPUT_DIR / "recordings"

_recording_active = False
_recording_thread = None
_recording_frames: list[str] = []
_recording_lock = threading.Lock()
_recording_start = 0.0


def _ensure_dirs():
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    RECORDING_DIR.mkdir(parents=True, exist_ok=True)


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def capture_screenshot(region: str = "") -> str:
    """Take a screenshot. Optionally region: 'full' (default), 'screen', or 'window'."""
    _ensure_dirs()
    ts = _timestamp()
    path = SCREENSHOT_DIR / f"screenshot_{ts}.png"

    try:
        if region.lower() in ("screen", "full", ""):
            img = ImageGrab.grab()
        else:
            img = ImageGrab.grab()

        img.save(str(path))
        size = path.stat().st_size
        return f"Screenshot saved: {path.name} ({size:,} bytes)"
    except Exception as e:
        return f"Screenshot error: {e}"


def capture_region(x: int, y: int, w: int, h: int) -> str:
    """Capture a specific screen region."""
    _ensure_dirs()
    ts = _timestamp()
    path = SCREENSHOT_DIR / f"region_{ts}.png"
    try:
        img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
        img.save(str(path))
        return f"Region captured: {path.name}"
    except Exception as e:
        return f"Region capture error: {e}"


def list_screenshots(limit: int = 20) -> str:
    """List recent screenshots."""
    _ensure_dirs()
    files = sorted(SCREENSHOT_DIR.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return "No screenshots yet."
    lines = [f"Recent screenshots ({min(len(files), limit)} shown):\n"]
    for f in files[:limit]:
        ts = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        size = f.stat().st_size
        lines.append(f"  {f.name:40s} {ts}  {size:,}b")
    return "\n".join(lines)


def start_recording(fps: int = 2, duration: int = 60) -> str:
    """Start screen recording at given fps (frames per second) for duration seconds."""
    global _recording_active, _recording_thread, _recording_frames, _recording_start

    if _recording_active:
        return "Recording already in progress."

    _ensure_dirs()
    _recording_active = True
    _recording_frames = []
    _recording_start = time.time()
    interval = 1.0 / max(fps, 1)

    ts = _timestamp()
    session_dir = RECORDING_DIR / f"recording_{ts}"
    session_dir.mkdir(parents=True, exist_ok=True)

    def _capture_loop():
        frame_count = 0
        start = time.time()
        while _recording_active and (time.time() - start) < duration:
            try:
                img = ImageGrab.grab()
                fname = session_dir / f"frame_{frame_count:06d}.png"
                img.save(str(fname))
                with _recording_lock:
                    _recording_frames.append(str(fname))
                frame_count += 1
            except Exception:
                pass
            time.sleep(interval)

        # Save metadata
        meta = {
            "date": datetime.now().isoformat(),
            "fps": fps,
            "duration": min(time.time() - start, duration),
            "frames": frame_count,
            "session_dir": str(session_dir),
            "files": _recording_frames.copy(),
        }
        (session_dir / "_metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        with _recording_lock:
            _recording_frames.clear()

    _recording_thread = threading.Thread(target=_capture_loop, daemon=True)
    _recording_thread.start()
    return f"Recording started: {fps} fps, max {duration}s → {session_dir.name}"


def stop_recording() -> str:
    """Stop active screen recording and optionally create a summary."""
    global _recording_active, _recording_thread

    if not _recording_active:
        return "No active recording."

    _recording_active = False
    if _recording_thread:
        _recording_thread.join(timeout=5)
        _recording_thread = None

    elapsed = time.time() - _recording_start if _recording_start else 0
    frame_count = len(_recording_frames)

    # Try to create a GIF from frames
    gif_path = None
    if frame_count > 1:
        try:
            from PIL import Image
            frames = []
            for f in _recording_frames[:100]:
                try:
                    frames.append(Image.open(f))
                except Exception:
                    pass
            if frames:
                ts = _timestamp()
                gif_path = RECORDING_DIR / f"recording_{ts}.gif"
                frames[0].save(
                    str(gif_path),
                    save_all=True,
                    append_images=frames[1:],
                    duration=1000 // max(1, int(frame_count / max(elapsed, 1))),
                    loop=0,
                )
        except Exception:
            pass

    with _recording_lock:
        _recording_frames.clear()

    result = (
        f"Recording stopped.\n"
        f"  Duration: {elapsed:.1f}s\n"
        f"  Frames:   {frame_count}\n"
    )
    if gif_path:
        result += f"  GIF:      {gif_path.name} ({gif_path.stat().st_size:,} bytes)\n"
    result += f"  Frames in: recording_{_timestamp()}/"
    return result


def recording_status() -> str:
    """Check if recording is active."""
    if _recording_active:
        elapsed = time.time() - _recording_start
        frames = len(_recording_frames)
        return f"Recording active: {elapsed:.0f}s, {frames} frames captured"
    return "No active recording."


def list_recordings(limit: int = 10) -> str:
    """List past recordings."""
    _ensure_dirs()
    gifs = sorted(RECORDING_DIR.glob("*.gif"), key=lambda p: p.stat().st_mtime, reverse=True)
    dirs = sorted(RECORDING_DIR.glob("recording_*"), key=lambda p: p.stat().st_mtime, reverse=True)

    lines = [f"Recent recordings ({limit} shown):\n"]

    for d in dirs[:limit]:
        meta_file = d / "_metadata.json"
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                lines.append(f"  {d.name:40s} {meta['frames']} frames, {meta['duration']:.0f}s")
            except Exception:
                lines.append(f"  {d.name:40s} [dim](frames)[/dim]")

    for g in gifs[:limit]:
        size = g.stat().st_size
        lines.append(f"  {g.name:40s} {size:,}b [dim](GIF)[/dim]")

    if len(lines) == 1:
        lines.append("  [dim]No recordings yet.[/dim]")

    return "\n".join(lines)


@command(name="screenshot", aliases=["scrot", "capture"],
         help_text="Take a screenshot: /screenshot [full|screen]")
def cmd_screenshot(args: str, assistant) -> str:
    return capture_screenshot(args)


@command(name="record", aliases=["screenrecord", "rec"],
         help_text="Screen recording: /record start [fps=2] [duration=60], /record stop, /record status")
def cmd_record(args: str, assistant) -> str:
    parts = args.strip().lower().split()
    if not parts:
        return (
            "Usage:\n"
            "  /record start [fps] [duration_sec]  — start recording\n"
            "  /record stop                        — stop recording\n"
            "  /record status                      — check recording state\n"
            "  /record list                        — list past recordings\n"
        )
    action = parts[0]
    if action == "start":
        fps = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 2
        dur = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 60
        return start_recording(fps, dur)
    elif action == "stop":
        return stop_recording()
    elif action == "status":
        return recording_status()
    elif action == "list":
        return list_recordings()
    return f"Unknown action: {action}. Use: start, stop, status, list"
