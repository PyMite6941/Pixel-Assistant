"""
Voice dependency checker for Pixel Assistant.
Run: python -m core_files.voice_setup
or call check() from run.py before initializing Voice.
"""
import subprocess
import sys


_DEPS = [
    ("pyttsx3",           "pyttsx3",           "TTS engine"),
    ("speech_recognition","SpeechRecognition",  "STT (Google / offline)"),
    ("pyaudio",           "PyAudio",            "microphone I/O"),
]

_PYAUDIO_HELP = """
PyAudio install instructions (Windows):
  Option 1 — pre-built wheel (easiest):
    pip install pipwin
    pipwin install pyaudio

  Option 2 — direct wheel:
    pip install PyAudio

  Option 3 — conda:
    conda install pyaudio

  If you see a VC++ error: install Microsoft C++ Build Tools first.
  https://visualstudio.microsoft.com/visual-cpp-build-tools/
"""

_WHISPER_DEPS = [
    ("whisper",    "openai-whisper", "offline STT model"),
    ("soundfile",  "soundfile",      "audio file I/O for Whisper"),
]


def check(require_microphone: bool = True, whisper: bool = False) -> bool:
    """
    Returns True if all required voice deps are present.
    Prints a targeted error + fix instructions for anything missing.
    """
    ok = True

    for module, package, label in _DEPS:
        try:
            __import__(module)
        except ImportError:
            ok = False
            print(f"\n[voice] Missing: {package}  ({label})")
            if package == "PyAudio":
                print(_PYAUDIO_HELP)
            else:
                print(f"  Fix: pip install {package}")

    if whisper:
        for module, package, label in _WHISPER_DEPS:
            try:
                __import__(module)
            except ImportError:
                ok = False
                print(f"\n[voice] Missing: {package}  ({label})")
                print(f"  Fix: pip install {package}")

    if require_microphone and ok:
        ok = _check_microphone()

    return ok


def _check_microphone() -> bool:
    try:
        import pyaudio
        pa = pyaudio.PyAudio()
        count = pa.get_device_count()
        pa.terminate()
        if count == 0:
            print("\n[voice] No audio input devices found.")
            print("  Connect a microphone and try again.")
            return False
        return True
    except Exception as e:
        print(f"\n[voice] Microphone check failed: {e}")
        return False


def install_missing() -> None:
    """Attempt to pip-install everything that is missing."""
    for module, package, _ in _DEPS + _WHISPER_DEPS:
        try:
            __import__(module)
        except ImportError:
            print(f"Installing {package}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", package, "-q"])
    print("Done. Re-run Pixel Assistant to use voice mode.")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--install", action="store_true", help="Install missing deps")
    p.add_argument("--whisper", action="store_true", help="Also check Whisper deps")
    args = p.parse_args()
    if args.install:
        install_missing()
    else:
        ok = check(whisper=args.whisper)
        sys.exit(0 if ok else 1)
