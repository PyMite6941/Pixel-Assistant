# Pixel Assistant — Setup Guide

Everything marked **YOU MUST DO** requires manual action.
Everything marked **auto** works out of the box once deps are installed.

---

## 1. Install Dependencies

```bash
cd "portfolio/Pixel Assistant"
pip install -r requirements.txt
```

Key packages:
| Package | Required? | For |
|---------|-----------|-----|
| `cryptography` | Yes | Credential encryption (AES-256-GCM) |
| `textual` | Yes | TUI mode |
| `groq` | Yes | Default LLM provider |
| `requests` | Yes | HTTP, IoT bridges, Home Assistant |
| `paho-mqtt` | No | MQTT broker operations |
| `bleak` | No | BLE device scanning |
| `pyaudio` | No | Voice I/O |

### PyAudio (Windows — special install)

PyAudio cannot be installed with plain `pip install` on Windows.
**YOU MUST DO** one of these:

```bash
pip install pipwin
pipwin install pyaudio
```

or if using Python 3.11:
```bash
pip install PyAudio
```

or via conda:
```bash
conda install pyaudio
```

> Voice features (speak, conversation, voice mode) won't work without PyAudio.
> All text/chat/TUI features work without it.

---

## 2. API Keys — `.env` file

The `.env` file is at the project root. Edit it directly.

### Groq (required for default operation)

**YOU MUST DO** — set your key:

```
GROQ_KEY=gsk_your_key_here
```

Get a free key at: https://console.groq.com/keys

### Gemini (optional — alternative LLM)

```
GEMINI_KEY=your_key_here
```

Get a free key at: https://aistudio.google.com/app/apikey

### Mistral (optional — alternative LLM)

```
MISTRAL_KEY=your_key_here
```

Get a free key at: https://console.mistral.ai/

### Hugging Face (optional — image generation fallback)

```
HF_TOKEN=your_token_here
```

### Home Assistant (optional — IoT bridge)

```
HA_URL=http://homeassistant.local:8123
HA_TOKEN=your_long_lived_token
```

---

## 3. Google Calendar Integration

1. Go to https://console.cloud.google.com/
2. Create a project → **APIs & Services** → **Library** → Enable **Google Calendar API**
3. **Credentials** → **+ Create Credentials** → **OAuth 2.0 Client ID** (Desktop app)
4. Download JSON → rename to `credentials.json` → place in project root
5. First run of `/calendar` opens a browser tab for one-time login

---

## 4. Running Pixel

### TUI mode (recommended)

```bash
python src/run.py --tui
```

Or double-click `start_tui.bat` on Windows.

### Text mode

```bash
python src/run.py
```

### Web UI

```bash
uvicorn src.api.app:app --reload --port 8000
```

Or `docker compose up --build` then open http://localhost:8000.

### Other flags

```bash
python src/run.py --provider gemini   # start with Gemini
python src/run.py --smart             # start with 70B model
python src/run.py --debug             # routing info on every prompt
python src/run.py --voice-only        # voice I/O only
python src/run.py --whisper           # offline speech-to-text
```

---

## 5. TUI Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `F1` | Toggle help screen |
| `F2` | Focus skills sidebar |
| `Ctrl+Shift+S` | Screenshot |
| `Ctrl+Shift+M` | Start/stop screen recording |
| `Ctrl+Shift+V` | Toggle voice mode |
| `F8` | Toggle system tray |
| Arrow keys | Navigate sidebar |
| Enter | Select domain |

---

## 6. IoT Device Discovery

No additional setup needed for LAN device discovery — works out of the box.

| Protocol | Setup Needed |
|----------|-------------|
| Philips Hue | Press link button on bridge, then `/hue register <ip>` |
| TP-Link Kasa | None (LAN discovery) |
| Home Assistant | Set `HA_URL` and `HA_TOKEN` in `.env` |
| BLE | `pip install bleak` |
| MQTT | `pip install paho-mqtt` |

Credentials are encrypted at rest with a machine-derived key.

---

## 7. Optional: Startup Password

```
/password <your-password>
```

Hash stored in `.env`, plaintext never saved.
To remove: `/password clear`

---

## 8. Voice Setup Check

```bash
python -m core_files.voice_setup
python -m core_files.voice_setup --install   # auto-install missing deps
python -m core_files.voice_setup --whisper   # also check Whisper deps
```

---

## 9. Testing

```bash
python tests/run_all.py
```

26 tests across:
- Agent system
- Memory (RAG)
- IoT device registry (list/register/remove/value)
- P2P discovery (status/discover_once)
- IoT bridge (encryption roundtrip, sync, lookups)
- BLE scanner (help, module parse)
- Platform utilities
- UI constants
- Plugin system

---

## 10. What Works Without Any Extra Setup

With only `GROQ_KEY` set:

- Full chat / TUI with 17 domain panels
- All 39+ slash commands
- IoT bridges (Hue, Kasa, SSDP, generic REST)
- P2P mesh networking
- Image generation (Pollinations.ai, no key needed)
- Image browsing and context sourcing
- Screenshot / screen recording
- Meeting notes with transcription (PyAudio optional)
- `/slides`, `/pdf`, `/email`, `/code`
- `/timer`, `/remind`, `/pomodoro`
- `/translate`, `/define`, `/summarize`, `/teach`
- `/calc`, `/weather`, `/wiki`, `/sys`
- `/note`, `/todo`, `/journal`, `/remember`
- Model switching with rate limit display
- Self-update via LLM
- System tray (requires `pystray`)
