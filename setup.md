# Pixel Assistant — Setup Guide

Everything marked **YOU MUST DO** requires manual action.
Everything marked **auto** works out of the box once deps are installed.

---

## 1. Install Dependencies

```bash
cd "portfolio/Pixel Assistant"
pip install -r requirements.txt
```

### PyAudio (Windows — special install)

PyAudio cannot be installed with plain `pip install` on Windows.
**YOU MUST DO** one of these:

```bash
# Option A — easiest
pip install pipwin
pipwin install pyaudio

# Option B — direct wheel (Python 3.11)
pip install PyAudio

# Option C — conda
conda install pyaudio
```

If you see a Visual C++ error, install
[Microsoft C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) first.

> Voice features (speak, conversation, voice mode) won't work without PyAudio.
> All text/chat features work without it.

---

## 2. API Keys — `.env` file

The `.env` file is at the project root. Edit it directly.

### Groq (required for default operation)

**YOU MUST DO** — already set in your `.env`:

```
GROQ_KEY=gsk_...   ← already filled in ✓
```

Get a free key at: https://console.groq.com/keys

### Gemini (optional — alternative LLM)

```
GEMINI_KEY=         ← fill in if you want to use /set provider gemini
```

Get a free key at: https://aistudio.google.com/app/apikey

### Mistral (optional — alternative LLM)

```
MISTRAL_KEY=        ← fill in if you want to use /set provider mistral
```

Get a free key at: https://console.mistral.ai/

### Hugging Face (optional — image generation fallback)

```
HF_TOKEN=           ← fill in for HF image generation (Pollinations works without it)
```

Get a free token at: https://huggingface.co/settings/tokens

---

## 3. Google Calendar Integration

This is the most involved setup step.

**YOU MUST DO** the following:

1. Go to https://console.cloud.google.com/
2. Create a new project (or select an existing one)
3. **APIs & Services → Library → search "Google Calendar API" → Enable**
4. **APIs & Services → Credentials → + Create Credentials → OAuth 2.0 Client ID**
   - Application type: **Desktop app**
   - Name: anything (e.g. "Pixel Assistant")
5. Click **Download JSON** on the created credential
6. Rename the downloaded file to `credentials.json`
7. Move it to the **project root** (same folder as this setup.md):
   ```
   portfolio/Pixel Assistant/credentials.json
   ```
8. First time you run `/calendar` or `/morning`, a browser tab opens for login.
   After you approve, a token is saved to `src/functionalities/google_token.json`
   and you won't be asked again.

> Without `credentials.json`, all `/calendar`, `/morning`, and `/check` commands
> will return an error message but won't crash anything else.

---

## 4. Running Pixel

### Text mode (default)

```bash
python src/run.py
```

### Voice mode

```bash
python src/run.py --voice-only    # voice I/O only
python src/run.py --text-only     # force text even if voice_enabled=true in config
python src/run.py --whisper       # offline STT using Whisper tiny model
```

### Web UI (local)

```bash
uvicorn src.api.app:app --reload --port 8000
```

Then open http://localhost:8000 in your browser.

### Web UI (Docker)

```bash
docker compose up --build
```

Then open http://localhost:8000.

> Docker does not support voice mode (no audio device passthrough by default).

### Other flags

```bash
python src/run.py --provider gemini   # start with Gemini instead of Groq
python src/run.py --smart             # start with 70B model
python src/run.py --debug             # show routing info on every prompt
```

---

## 5. Optional: Startup Password

To protect the CLI with a password:

```
/password <your-password>
```

The hash is stored in `.env` — the plaintext password is never saved.
To remove it: `/password clear`

> The web UI does not currently enforce the password. It is CLI-only.

---

## 6. Voice Setup Check

Run this to verify all voice deps before launching in voice mode:

```bash
python -m core_files.voice_setup
python -m core_files.voice_setup --install   # auto-install missing deps
python -m core_files.voice_setup --whisper   # also check Whisper deps
```

---

## 7. config.yaml — Tweakable Settings

Located at project root. Edit directly or use `/set <key> <value>` in Pixel.

| Key | Default | Description |
|---|---|---|
| `provider` | `groq` | Active LLM provider |
| `model` | `openai/gpt-oss-20b` | Fast model |
| `smart_model` | `openai/gpt-oss-120b` | Smart model (toggle with `/smart`) |
| `voice_enabled` | `false` | Auto-start voice mode |
| `tts_rate` | `150` | TTS speech rate (words/min) |
| `tts_volume` | `1.0` | TTS volume (0.0–1.0) |
| `max_history` | `20` | Conversation turns kept in context |
| `wake_word` | `hey pixel` | Wake word for voice mode |
| `log_conversations` | `true` | Write all chats to `logs/` |

---

## 8. File Layout (generated at runtime)

These are created automatically — nothing to configure.

| Path | Contents |
|---|---|
| `src/functionalities/chat-history.json` | Conversation history |
| `src/functionalities/notes.txt` | Saved notes |
| `src/functionalities/todos.json` | Todo list |
| `src/functionalities/memories.md` | `/remember` facts injected into context |
| `src/functionalities/journal.md` | Daily journal entries |
| `src/functionalities/teach_history.json` | Topics studied with `/teach` |
| `src/functionalities/update_log.json` | `/update` changelog |
| `src/functionalities/backups/` | Backups before each `/update` |
| `src/functionalities/google_token.json` | Google OAuth token (auto-created on first login) |
| `generated/` | Slides (.pptx) and PDFs generated by `/slides` and `/pdf` |
| `logs/` | Daily conversation logs |

---

## 9. What Works Without Any Extra Setup

With only `GROQ_KEY` set (already done):

- Full chat / conversation history
- `/teach`, `/quiz`, `/translate`, `/define`, `/summarize`
- `/note`, `/todo`, `/journal`, `/remember`, `/memories`
- `/calc`, `/weather`, `/wiki`, `/code`
- `/slides`, `/pdf` (both themes work)
- `/email` drafting
- `/timer`, `/remind`, `/pomodoro`
- `/update check/feature/fix`
- Image generation via Pollinations (no key needed)
- Web UI at localhost:8000

Requires extra setup:
- **Voice** → PyAudio install (Section 3)
- **Google Calendar** → credentials.json (Section 3)
- **Gemini/Mistral** → API key in .env (Section 2)
- **HF image fallback** → HF_TOKEN in .env (Section 2)
