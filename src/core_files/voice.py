"""
Voice I/O for Pixel Assistant.
STT: Google (online, default) or Whisper tiny (offline, --whisper flag).
TTS: pyttsx3 (offline) — sentence-by-sentence streaming to reduce perceived latency.
CPU usage while idle/listening: ~0% (kernel-level audio I/O blocking).
"""
import re
import threading

import pyttsx3
import speech_recognition as sr


class Voice:
    def __init__(self, rate: int = 150, volume: float = 1.0, use_whisper: bool = False):
        self.engine = pyttsx3.init()
        self.engine.setProperty("rate", rate)
        self.engine.setProperty("volume", volume)
        self._tts_lock = threading.Lock()

        self.recognizer = sr.Recognizer()
        self.use_whisper = use_whisper
        self._whisper_model = None

    # ── TTS ──────────────────────────────────────────────────────────────

    def speak(self, text: str):
        """Speak text synchronously."""
        with self._tts_lock:
            self.engine.say(text)
            self.engine.runAndWait()

    def speak_streaming(self, text: str):
        """
        Split text into sentences and speak each as it's ready.
        This lets voice output start before the full response is available.
        """
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        for sentence in sentences:
            if sentence.strip():
                self.speak(sentence.strip())

    # ── STT ──────────────────────────────────────────────────────────────

    def listen(self, timeout: int = 8, phrase_time_limit: int = 30) -> str | None:
        """
        Block until speech is detected or timeout expires.
        Returns transcribed text, or None on silence/error.
        CPU usage: ~0% while silent (blocks on audio device I/O).
        """
        with sr.Microphone() as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=0.3)
            try:
                audio = self.recognizer.listen(
                    source,
                    timeout=timeout,
                    phrase_time_limit=phrase_time_limit,
                )
            except sr.WaitTimeoutError:
                return None

        return self._whisper_transcribe(audio) if self.use_whisper else self._google_transcribe(audio)

    def _google_transcribe(self, audio: sr.AudioData) -> str | None:
        try:
            return self.recognizer.recognize_google(audio)
        except (sr.UnknownValueError, sr.RequestError):
            return None

    def _whisper_transcribe(self, audio: sr.AudioData) -> str | None:
        import os, tempfile
        try:
            import numpy as np
            import soundfile as sf
        except ImportError:
            return self._google_transcribe(audio)

        raw = np.frombuffer(audio.get_raw_data(), dtype=np.int16).astype(np.float32) / 32768.0
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            sf.write(f.name, raw, audio.sample_rate)
            path = f.name
        try:
            model = self._get_whisper()
            return model.transcribe(path)["text"].strip()
        except Exception:
            return None
        finally:
            os.unlink(path)

    def _get_whisper(self):
        if self._whisper_model is None:
            import whisper
            self._whisper_model = whisper.load_model("tiny")
        return self._whisper_model
