# Pixel Assistant

A modular AI assistant for the terminal. Supports multiple LLM providers, voice, timers, notes, todos, calendar, file generation, and self-updating.

---

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run
python src/run.py
```

Or double-click `start.bat` on Windows.

---

## Launch Options

```bash
python src/run.py                    # default (text mode, Groq)
python src/run.py --provider gemini  # use Gemini
python src/run.py --provider mistral # use Mistral
python src/run.py --smart            # use the 70B model
python src/run.py --voice-only       # voice input/output mode
python src/run.py --debug            # show routing info
python src/run.py --whisper          # offline speech-to-text (Whisper tiny)
```

---

## Commands

### General

| Command | Description |
|---|---|
| `/help` | List all commands |
| `/status` | Show current provider, model, and settings |
| `/models` | List available Groq models |
| `/smart` | Toggle 70B smart mode on/off |
| `/clear` | Clear conversation history |
| `/history` | Show last 20 conversation turns |

### Notes

| Command | Description |
|---|---|
| `/note <text>` | Save a note |
| `/notes` | List all notes |
| `/note search <keyword>` | Search notes |
| `/note delete <n>` | Delete note by number |
| `/note delete last` | Delete the most recent note |
| `/note clear` | Delete all notes |

### Todos

| Command | Description |
|---|---|
| `/todo` | List all todos |
| `/todo add <task>` | Add a todo |
| `/todo done <n>` | Mark todo as done |
| `/todo delete <n>` | Delete a todo |
| `/todo clear` | Remove all completed todos |

### Journal & Memory

| Command | Description |
|---|---|
| `/journal <entry>` | Add a journal entry for today |
| `/journal` | View today's journal entries |
| `/remember <fact>` | Save a persistent memory |
| `/memories` | List all memories |
| `/forget <keyword>` | Delete memories matching keyword |

### Timers & Productivity

| Command | Description |
|---|---|
| `/timer <duration>` | Start a countdown timer (e.g. `5min`, `30s`, `2h`) |
| `/remind <duration> <msg>` | Set a reminder (e.g. `/remind 10min call John`) |
| `/pomodoro` | Start a 25/5 Pomodoro session (4 cycles) |
| `/pomodoro <work>/<break>` | Custom Pomodoro (e.g. `/pomodoro 50/10`) |
| `/check` | Show overdue todos + upcoming calendar events |
| `/morning` | Daily briefing: weather, calendar, todos |

### Writing & Language

| Command | Description |
|---|---|
| `/email <description>` | Draft a professional email |
| `/translate <lang> <text>` | Translate text to a language |
| `/summarize [text]` | Summarize text or last response |
| `/define <word>` | Get a structured word definition |
| `/code <task>` | Ask the LLM to write code |
| `/teach <topic>` | Get a structured lesson on any topic |
| `/teach quiz` | Quiz on the last studied topic |
| `/teach topics` | List all studied topics |
| `/teach reset` | Clear study history |

### File Generation

| Command | Description |
|---|---|
| `/slides <topic>` | Generate a PowerPoint presentation |
| `/pdf <topic>` | Generate a PDF document |
| `/themes` | List available themes and current settings |

### Calendar (Google Calendar)

| Command | Description |
|---|---|
| `/calendar` | List events for the next 7 days |
| `/calendar today` | List today's events |
| `/calendar add <description>` | Add an event using natural language |
| `/calendar delete <id>` | Delete an event by ID |
| `/calendar setup` | Show Google Calendar setup instructions |

### System & Tools

| Command | Description |
|---|---|
| `/calc <expr>` | Evaluate a math expression |
| `/weather [city]` | Get current weather (default: auto by IP) |
| `/wiki <topic>` | Look up a Wikipedia summary |
| `/sys` | Show CPU, RAM, and disk usage |
| `/run <python code>` | Execute Python code in a subprocess |
| `/open <path>` | Open a file with its default app |
| `/speak <text>` | Read text aloud via TTS |
| `/clip` | Copy last response to clipboard |
| `/lang auto` | Auto-detect and match the user's language |
| `/lang off` | Disable auto language detection |

### Configuration

| Command | Description |
|---|---|
| `/set provider <groq\|gemini\|mistral>` | Switch LLM provider |
| `/set model <name>` | Set the model name |
| `/set persona <text>` | Set the assistant's persona/system prompt |
| `/set <key> <value>` | Set any config value |

### Self-Update

| Command | Description |
|---|---|
| `/update check` | Ask LLM to audit the codebase for bugs |
| `/update feature <desc>` | Add a new feature via LLM |
| `/update fix <desc>` | Fix a specific issue via LLM |
| `/update log` | Show the last 20 self-update entries |
| `/update rollback` | Revert to the last backup of main.py |

---

## Natural Language Shortcuts

These phrases are recognized without a `/` prefix:

| Say | Action |
|---|---|
| "what time is it" | Current time |
| "what day is it" | Current date |
| "open browser" / "open google" | Opens browser |
| "take a screenshot" | Screenshot |
| "search for X" | Web search |
| "generate an image of X" | Image generation |
| "what's on my calendar" | `/calendar` |
| "switch to groq/gemini/mistral" | Switch provider |

---

## Google Calendar Setup

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a project → **APIs & Services** → Enable **Google Calendar API**
3. **Credentials** → **+ Create Credentials** → **OAuth 2.0 Client ID** (Desktop app)
4. Download the JSON and save it as `credentials.json` in this project root
5. Run `/calendar` — a browser tab opens for one-time login, token is saved automatically

---

## API Keys

Add your keys to `config.yaml` or a `.env` file in the project root:

```yaml
groq_key: "your-groq-key"
gemini_key: "your-gemini-key"
mistral_key: "your-mistral-key"
```

Get keys at:
- Groq: [console.groq.com](https://console.groq.com)
- Gemini: [aistudio.google.com](https://aistudio.google.com)
- Mistral: [console.mistral.ai](https://console.mistral.ai)

---

## Project Structure

```
Pixel Assistant/
├── src/
│   ├── main.py              # Core assistant logic and all commands
│   ├── run.py               # Entry point (CLI args, venv check)
│   ├── skills/
│   │   ├── calendar_gcal.py # Google Calendar integration
│   │   ├── slides.py        # PowerPoint generation
│   │   ├── pdf_gen.py       # PDF generation
│   │   ├── image_gen.py     # Image generation
│   │   ├── video_gen.py     # Video generation
│   │   └── self_update.py   # Self-update / backup logic
│   └── functionalities/
│       ├── chat-history.json
│       ├── notes.txt
│       ├── todos.json
│       ├── memories.md
│       ├── journal.md
│       ├── teach_history.json
│       ├── update_log.json
│       └── backups/         # main.py backups before each self-update
├── credentials.json         # Google OAuth client (you provide)
├── config.yaml              # API keys and settings
├── requirements.txt
└── start.bat                # Windows launcher
```
