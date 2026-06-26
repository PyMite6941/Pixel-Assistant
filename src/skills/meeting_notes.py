"""
Meeting notes for Pixel Assistant.
Live transcription, meeting recording, note-taking, and LLM summarization.
Uses SpeechRecognition (already in requirements.txt) for STT.
"""
import json
import os
import re
import sys
import tempfile
import threading
import time
import wave
from datetime import datetime
from pathlib import Path

from skills import command

OUTPUT_DIR = Path(__file__).parent.parent.parent / "generated"
MEETINGS_DIR = OUTPUT_DIR / "meetings"

_listening_active = False
_listening_thread = None
_listening_transcript: list[dict] = []
_listening_lock = threading.Lock()
_listening_start = 0.0


def _ensure_dirs():
    MEETINGS_DIR.mkdir(parents=True, exist_ok=True)


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _format_transcript(entries: list[dict]) -> str:
    lines = []
    for e in entries:
        ts = e.get("time", "?")
        speaker = e.get("speaker", "Speaker")
        text = e.get("text", "")
        lines.append(f"[{ts}] {speaker}: {text}")
    return "\n".join(lines)


def start_listening(speaker: str = "Speaker") -> str:
    """Start live transcription from microphone."""
    global _listening_active, _listening_thread, _listening_transcript, _listening_start

    if _listening_active:
        return "Meeting notes already active."

    try:
        import speech_recognition as sr
    except ImportError:
        return "SpeechRecognition not installed. Run: pip install SpeechRecognition"

    _ensure_dirs()
    _listening_active = True
    _listening_transcript = []
    _listening_start = time.time()

    recognizer = sr.Recognizer()
    recognizer.energy_threshold = 300
    recognizer.dynamic_energy_threshold = True
    recognizer.pause_threshold = 0.8

    def _listen_loop():
        source = None
        try:
            mic = sr.Microphone()
            with mic as s:
                recognizer.adjust_for_ambient_noise(s, duration=0.5)
            source = sr.Microphone()

            while _listening_active:
                try:
                    audio = recognizer.listen(source, timeout=2, phrase_time_limit=15)
                    text = recognizer.recognize_google(audio)
                    if text.strip():
                        elapsed = time.time() - _listening_start
                        minutes = int(elapsed // 60)
                        seconds = int(elapsed % 60)
                        entry = {
                            "time": f"{minutes:02d}:{seconds:02d}",
                            "speaker": speaker,
                            "text": text.strip(),
                        }
                        with _listening_lock:
                            _listening_transcript.append(entry)
                except sr.WaitTimeoutError:
                    continue
                except sr.UnknownValueError:
                    continue
                except Exception:
                    continue
        except Exception:
            pass
        finally:
            if source:
                try:
                    source.__exit__(None, None, None)
                except Exception:
                    pass

    _listening_thread = threading.Thread(target=_listen_loop, daemon=True)
    _listening_thread.start()

    return (
        f"Meeting notes started. Speaker tag: '{speaker}'\n"
        f"Listening from microphone... Use /meeting stop to end."
    )


def stop_listening(llm_fn=None) -> str:
    """Stop transcription and save meeting notes."""
    global _listening_active, _listening_thread

    if not _listening_active:
        return "No active meeting."

    _listening_active = False
    if _listening_thread:
        _listening_thread.join(timeout=5)
        _listening_thread = None

    elapsed = time.time() - _listening_start if _listening_start else 0
    with _listening_lock:
        entries = list(_listening_transcript)
        _listening_transcript.clear()

    ts = _timestamp()
    _ensure_dirs()

    # Save raw transcript
    transcript_text = _format_transcript(entries)
    transcript_path = MEETINGS_DIR / f"meeting_{ts}_transcript.txt"
    transcript_path.write_text(transcript_text, encoding="utf-8")

    # Save JSON
    data = {
        "date": datetime.now().isoformat(),
        "duration_sec": elapsed,
        "entries": entries,
        "entry_count": len(entries),
    }
    json_path = MEETINGS_DIR / f"meeting_{ts}.json"
    json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    # Generate summary via LLM if available
    summary_text = ""
    if llm_fn and entries:
        try:
            transcript_sample = transcript_text[:3000]
            prompt = (
                f"You are a meeting note-taking assistant. Summarize this meeting transcript.\n\n"
                f"TRANSCRIPT:\n{transcript_sample}\n\n"
                f"Please provide:\n"
                f"1. Meeting Summary (2-3 sentences)\n"
                f"2. Key Points (bullet list)\n"
                f"3. Action Items (bullet list with assignees)\n"
                f"4. Decisions Made\n"
                f"5. Questions Left Open"
            )
            summary = llm_fn([{"role": "user", "content": prompt}])
            summary_text = summary.strip() if summary else ""
            if summary_text:
                summary_path = MEETINGS_DIR / f"meeting_{ts}_summary.txt"
                summary_path.write_text(summary_text, encoding="utf-8")
        except Exception:
            summary_text = ""

    # Stats
    word_count = sum(len(e["text"].split()) for e in entries)
    result = (
        f"── Meeting Notes Saved ──────────────────────\n"
        f"  Duration : {elapsed:.0f}s ({elapsed / 60:.1f} min)\n"
        f"  Entries  : {len(entries)}\n"
        f"  Words    : {word_count}\n"
        f"  File     : {json_path.name}\n"
    )
    if summary_text:
        result += f"  Summary  : meeting_{ts}_summary.txt\n"
        result += f"\n{summary_text}\n"
    result += "──────────────────────────────────────────────"
    return result


def meeting_status() -> str:
    """Check if meeting notes is active."""
    if _listening_active:
        elapsed = time.time() - _listening_start
        with _listening_lock:
            count = len(_listening_transcript)
        return f"Meeting active: {elapsed:.0f}s, {count} entries transcribed"
    return "No active meeting."


def list_meetings(limit: int = 10) -> str:
    """List past meetings."""
    _ensure_dirs()
    meetings = sorted(MEETINGS_DIR.glob("meeting_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not meetings:
        return "No meetings recorded yet."

    lines = [f"Recent meetings ({min(len(meetings), limit)} shown):\n"]
    for m in meetings[:limit]:
        try:
            data = json.loads(m.read_text(encoding="utf-8"))
            date = data.get("date", "?")[:16]
            dur = data.get("duration_sec", 0)
            count = data.get("entry_count", 0)
            lines.append(f"  {m.stem:45s} {date}  {dur:.0f}s  {count} entries")
        except Exception:
            lines.append(f"  {m.stem:45s} [dim](corrupted)[/dim]")
    return "\n".join(lines)


def show_latest_meeting() -> str:
    """Show the most recent meeting summary."""
    _ensure_dirs()
    meetings = sorted(MEETINGS_DIR.glob("meeting_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not meetings:
        return "No meetings found."
    latest = meetings[0]
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
        entries = data.get("entries", [])
        transcript = _format_transcript(entries)
        summary_path = latest.with_name(latest.stem.replace("meeting_", "meeting_").replace(".json", "_summary.txt"))
        summary = ""
        if summary_path.exists():
            summary = summary_path.read_text(encoding="utf-8")

        lines = [
            f"── Latest Meeting: {data.get('date', '?')} ──",
            f"Duration: {data.get('duration_sec', 0):.0f}s  |  Entries: {data.get('entry_count', 0)}",
        ]
        if summary:
            lines.extend(["", "── Summary ──", summary])
        lines.extend(["", "── Transcript ──", transcript])
        return "\n".join(lines)
    except Exception as e:
        return f"Error reading meeting: {e}"


# ── Transcribe audio file ───────────────────────────────────────────────────

def transcribe_file(audio_path: str, llm_fn=None) -> str:
    """Transcribe an audio file (WAV/MP3/etc.) using SpeechRecognition or Whisper."""
    path = Path(audio_path)
    if not path.exists():
        return f"File not found: {audio_path}"

    try:
        import speech_recognition as sr
        recognizer = sr.Recognizer()

        # Try Whisper first (more accurate)
        try:
            import whisper
            model = whisper.load_model("tiny")
            result = model.transcribe(str(path))
            text = result.get("text", "")
        except Exception:
            # Fallback to Google STT
            with sr.AudioFile(str(path)) as source:
                audio = recognizer.record(source)
            text = recognizer.recognize_google(audio)

        if not text.strip():
            return "No speech detected in file."

        ts = _timestamp()
        _ensure_dirs()
        out_path = MEETINGS_DIR / f"transcript_{ts}.txt"
        out_path.write_text(text.strip(), encoding="utf-8")

        summary = ""
        if llm_fn and len(text) > 50:
            try:
                prompt = (
                    f"Summarize this transcript in 3-5 bullet points "
                    f"and list any action items:\n\n{text[:3000]}"
                )
                summary = llm_fn([{"role": "user", "content": prompt}])
                if summary:
                    summary_path = MEETINGS_DIR / f"transcript_{ts}_summary.txt"
                    summary_path.write_text(summary.strip(), encoding="utf-8")
            except Exception:
                pass

        result = (
            f"── Transcription Complete ──\n"
            f"  Source: {path.name}\n"
            f"  Words:  {len(text.split())}\n"
            f"  Saved:  transcript_{ts}.txt\n"
        )
        if summary:
            result += f"\n{summary.strip()}\n"
        return result
    except ImportError as e:
        return f"Missing dependency: {e}. Install: pip install SpeechRecognition"
    except Exception as e:
        return f"Transcription error: {e}"


@command(name="meeting", aliases=["meet", "meetings"],
         help_text="Meeting notes: /meeting start [speaker], /meeting stop, /meeting status, /meeting list")
def cmd_meeting(args: str, assistant) -> str:
    parts = args.strip().split()
    if not parts:
        return (
            "Usage:\n"
            "  /meeting start [speaker_name]  — start live transcription\n"
            "  /meeting stop                  — stop and save meeting notes\n"
            "  /meeting status                — check meeting status\n"
            "  /meeting list                  — list past meetings\n"
            "  /meeting latest                — show most recent meeting\n"
            "  /meeting transcribe <file>     — transcribe audio file\n"
        )
    action = parts[0].lower()
    if action == "start":
        speaker = " ".join(parts[1:]) if len(parts) > 1 else "Speaker"
        return start_listening(speaker)
    elif action == "stop":
        llm_fn = getattr(assistant, "_ask_llm", None)
        return stop_listening(llm_fn)
    elif action == "status":
        return meeting_status()
    elif action == "list":
        return list_meetings()
    elif action == "latest":
        return show_latest_meeting()
    elif action == "transcribe":
        filepath = " ".join(parts[1:]) if len(parts) > 1 else ""
        if not filepath:
            return "Usage: /meeting transcribe <audio_file>"
        llm_fn = getattr(assistant, "_ask_llm", None)
        return transcribe_file(filepath, llm_fn)
    return f"Unknown action: {action}"
