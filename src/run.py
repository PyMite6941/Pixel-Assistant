"""
Entry point for Pixel Assistant.

Usage:
  python src/run.py                    # text mode, default provider
  python src/run.py --voice-only       # voice mode
  python src/run.py --provider gemini  # use Gemini
  python src/run.py --smart            # use 70B model
  python src/run.py --debug            # show routing info
  python src/run.py --whisper          # offline STT (Whisper tiny)
"""
import sys
from pathlib import Path


def _ensure_venv():
    """Restart under the .venv interpreter if we're not already running inside it."""
    root = Path(__file__).parent.parent
    venv_py = root / ".venv" / (
        "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
    )
    if venv_py.exists() and Path(sys.executable).resolve() != venv_py.resolve():
        import subprocess
        sys.exit(subprocess.run([str(venv_py)] + sys.argv).returncode)


_ensure_venv()

import argparse
import traceback

# Ensure src/ is on the path when running as `python src/run.py`
SRC = Path(__file__).parent
sys.path.insert(0, str(SRC))

# When launched via pythonw.exe (no console), log crashes to a file
# so errors are never silently swallowed.
_LOG = SRC.parent / "logs" / "startup.log"


def _setup_crash_log():
    _LOG.parent.mkdir(exist_ok=True)

    class _Tee:
        def __init__(self, stream, path):
            self._s = stream
            self._f = open(path, "a", encoding="utf-8")

        def write(self, data):
            self._f.write(data)
            self._f.flush()
            if self._s:
                try:
                    self._s.write(data)
                except Exception:
                    pass

        def flush(self):
            self._f.flush()

    if sys.stderr is None:
        sys.stderr = _Tee(None, _LOG)
    else:
        sys.stderr = _Tee(sys.stderr, _LOG)


_setup_crash_log()


def parse_args():
    p = argparse.ArgumentParser(description="Pixel Assistant")
    p.add_argument("--provider", choices=["groq", "gemini", "mistral"], help="LLM provider")
    p.add_argument("--voice-only", action="store_true", help="Voice I/O only")
    p.add_argument("--text-only",  action="store_true", help="Text I/O only")
    p.add_argument("--debug",      action="store_true", help="Show debug info")
    p.add_argument("--smart",      action="store_true", help="Use larger model (70B)")
    p.add_argument("--whisper",    action="store_true", help="Offline STT via Whisper tiny")
    return p.parse_args()


def main():
    args = parse_args()

    from skills import load_skills
    load_skills()
    print("Pixel Assistant v1.0.0 — skills loaded. Type /help for commands.\n")

    from core_files.config import Config
    config = Config()

    # ── Startup auth ──────────────────────────────────────────────────────
    from core_files.auth import prompt_login
    if not prompt_login():
        sys.exit(1)

    if args.smart:
        config.set("smart_mode", True)

    # ── System tray (non-blocking daemon) ─────────────────────────────────
    try:
        from core_files.tray import start as start_tray
        start_tray()
    except Exception as e:
        sys.stderr.write(f"Tray error: {e}\n{traceback.format_exc()}")

    # ── Voice setup ───────────────────────────────────────────────────────
    use_voice = args.voice_only or (not args.text_only and config.voice_enabled)
    voice = None

    if use_voice:
        from core_files.voice_setup import check as check_voice
        if not check_voice(whisper=args.whisper):
            sys.stderr.write(
                "\n[voice] One or more voice dependencies are missing.\n"
                "  Run:  python -m core_files.voice_setup --install\n"
                "  Or check the messages above for manual install steps.\n\n"
            )
            if args.voice_only:
                sys.exit(1)
            use_voice = False

    if use_voice:
        try:
            from core_files.voice import Voice
            voice = Voice(
                rate=config.tts_rate,
                volume=config.tts_volume,
                use_whisper=args.whisper,
            )
        except Exception as e:
            sys.stderr.write(f"Voice error: {e}\n")
            use_voice = False

    # ── Launch assistant ──────────────────────────────────────────────────
    from main import PixelAssistant

    assistant = PixelAssistant(
        provider=args.provider or config.provider,
        debug=args.debug or config.debug,
        voice=voice,
    )

    if use_voice:
        assistant.run_voice()
    else:
        assistant.run_text()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.stderr.write(traceback.format_exc())
        raise
