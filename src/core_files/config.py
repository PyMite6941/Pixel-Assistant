import os
import yaml
from pathlib import Path
from dotenv import load_dotenv

# project root: portfolio/Pixel Assistant/
BASE_DIR = Path(__file__).parent.parent.parent
CONFIG_FILE = BASE_DIR / "config.yaml"

# Lazy-load: load_dotenv is now called inside Config.__init__()
# to avoid file I/O at module import time.

DEFAULTS = {
    "provider": "groq",
    "model": "llama-3.1-8b-instant",
    "smart_model": "llama-3.3-70b-versatile",
    "voice_enabled": False,
    "tts_engine": "pyttsx3",
    "tts_rate": 150,
    "tts_volume": 1.0,
    "max_history": 20,
    "debug": False,
    "smart_mode": False,
    "wake_word": "hey pixel",
    "log_conversations": True,
    "ollama_url": "http://localhost:11434",
    "ollama_model": "llama3.2",
}


class Config:
    def __init__(self):
        load_dotenv(BASE_DIR / ".env")
        self._data = {**DEFAULTS, **self._load_yaml()}
        self.GROQ_KEY = os.getenv("GROQ_KEY")
        self.GEMINI_KEY = os.getenv("GEMINI_KEY")
        self.MISTRAL_KEY = os.getenv("MISTRAL_KEY")
        self.HF_TOKEN = os.getenv("HF_TOKEN")
        self.OLLAMA_URL = os.getenv("OLLAMA_URL", DEFAULTS["ollama_url"])
        self.OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", DEFAULTS["ollama_model"])

    def _load_yaml(self) -> dict:
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            except yaml.YAMLError as e:
                print(f"Warning: config.yaml parse error, using defaults: {e}")
        return {}

    def save(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                yaml.safe_dump(self._data, f, default_flow_style=False)
        except (OSError, yaml.YAMLError) as e:
            print(f"Warning: could not save config.yaml: {e}")

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value
        self.save()

    def __getattr__(self, key):
        if key.startswith("_") or key in ("GROQ_KEY", "GEMINI_KEY", "MISTRAL_KEY", "HF_TOKEN"):
            raise AttributeError(key)
        try:
            return self._data[key]
        except KeyError:
            raise AttributeError(f"Config has no key '{key}'")
