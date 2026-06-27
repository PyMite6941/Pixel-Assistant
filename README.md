# Pixel Assistant

A modular AI assistant for the terminal with a Textual-based TUI, IoT bridges, P2P mesh networking, BLE scanning, image generation, and 17 domain panels.

---

## Quick Start

```bash
pip install -r requirements.txt
python src/run.py                # text mode
python src/run.py --tui          # TUI mode (recommended)
python start_tui.bat             # TUI launcher (Windows)
```

---

## TUI Mode

The TUI (Terminal User Interface) provides a sidebar with 17 domain panels:

| Domain | Description |
|--------|-------------|
| Chat | Conversational AI with auto-skill suggestions |
| Skills | Browse all 39+ registered commands |
| Notes | Create, search, delete notes |
| Todos | Task management with add/done/clear |
| Calendar | Google Calendar integration |
| System | CPU, RAM, disk, network stats |
| Agents | Spawn orchestrator/explorer/coder/debugger agents |
| Screen | Screenshot & screen recording (GIF) |
| Meetings | Meeting notes with live transcription & AI summary |
| Files | Generate PDFs, slides, QR codes |
| Images | Browse local AI images, generate with /imagine, use as context |
| Network | Public/local IP, ping, diff, encode/decode, UUID |
| Security | Port audit, encryption/hash tools |
| Language | Translate, define, summarize, teach |
| Memory | Persistent facts, recall, forget |
| IoT | Device registry, MQTT, webhooks, rules engine, sensor simulation |
| P2P | LAN peer discovery, device sync, mesh networking |

**Keyboard shortcuts:**
- `F1` — Help / shortcuts reference
- `F2` — Focus skills sidebar
- `Ctrl+Shift+S` — Screenshot
- `Ctrl+Shift+M` — Start/stop screen recording
- `Ctrl+Shift+V` — Voice toggle (requires PyAudio)
- `F8` — Toggle system tray

---

## IoT & Networked Devices

Discover and control real devices on your LAN:

| Command | Protocol | Description |
|---------|----------|-------------|
| `/hue discover` | Philips Hue | Find Hue bridges via cloud API + SSDP |
| `/hue register <ip>` | REST | Register with bridge (press link button first) |
| `/hue lights` | REST | List all Hue lights |
| `/hue on/off/dim <id>` | REST | Control Hue lights |
| `/kasa discover` | TP-Link Kasa | Scan LAN for Kasa smart devices |
| `/kasa on/off <ip>` | Kasa binary | Control Kasa plugs/switches |
| `/ha status` | Home Assistant | Check HA connection |
| `/ha entities` | REST | List all HA entities |
| `/ha service <d> <s>` | REST | Call HA service |
| `/ssdp` | UPnP/SSDP | Discover UPnP devices on network |
| `/rest get/post <url>` | Generic REST | Control any REST API device |
| `/ble [secs]` | BLE | Scan for Bluetooth Low Energy devices |
| `/iot discover` | TCP | Scan LAN for open IoT ports |
| `/iot mqtt ...` | MQTT | MQTT broker connect/publish/subscribe |
| `/iot webhook ...` | HTTP | Webhook server for device read/write |
| `/iot rule ...` | Rules | IF-THEN automation rules engine |
| `/p2p discover` | UDP | LAN peer discovery for mesh networking |

Credentials are encrypted at rest (AES-256-GCM via machine-derived key).

---

## Image Generation

| Command | Description |
|---------|-------------|
| `/imagine <prompt>` | Generate AI image (Pollinations.ai, no key needed) |
| `/images [keyword]` | Browse local generated images |
| `/imagesource <n\|name>` | Use an image as AI source/context |
| `generate an image of X` | Natural language shortcut |

---

## Screen & Media

| Command | Description |
|---------|-------------|
| `/screenshot` | Capture screen (Ctrl+Shift+S in TUI) |
| `/record start` | Start screen recording (GIF) |
| `/record stop` | Stop recording |
| `/record status` | Show recording state |
| `/record list` | List recordings |

---

## Chat Commands

### General
`/help`, `/status`, `/models`, `/smart`, `/clear`, `/history`

### Notes
`/note <text>`, `/notes`, `/note search <kw>`, `/note delete <n>`

### Todos
`/todo`, `/todo add <task>`, `/todo done <n>`, `/todo delete <n>`, `/todo clear`

### Journal & Memory
`/journal <entry>`, `/remember <fact>`, `/memories`, `/forget <kw>`

### Timers
`/timer <dur>`, `/remind <dur> <msg>`, `/pomodoro`, `/check`, `/morning`

### Language
`/translate <lang> <text>`, `/define <word>`, `/summarize`, `/teach <topic>`, `/code <task>`

### File Generation
`/slides <topic>`, `/pdf <topic>`, `/themes`

### Calendar
`/calendar`, `/calendar today`, `/calendar add <desc>`, `/calendar delete <id>`

### System
`/calc`, `/weather`, `/wiki`, `/sys`, `/run`, `/open`, `/speak`, `/clip`

### Configuration
`/set provider <groq|gemini|mistral>`, `/set model <name>`, `/set persona <text>`

### Agents
`/agent <task>` — spawns orchestrator agent to solve complex tasks

### Self-Update
`/update check`, `/update feature <desc>`, `/update fix <desc>`, `/update log`

---

## API Keys

Add to `.env` in project root:

```
GROQ_KEY=your-groq-key         # required (default provider)
GEMINI_KEY=your-gemini-key     # optional
MISTRAL_KEY=your-mistral-key   # optional
HF_TOKEN=your-hf-token         # optional (HuggingFace image fallback)
HA_URL=http://ha.local:8123    # optional (Home Assistant)
HA_TOKEN=your-ha-token         # optional
```

---

## Project Structure

```
Pixel Assistant/
├── src/
│   ├── main.py                  # Core assistant logic
│   ├── run.py                   # Entry point (CLI args)
│   ├── core_files/
│   │   ├── tui_app.py           # Textual TUI (17 panels)
│   │   ├── ui.py                # Text-mode UI
│   │   ├── voice.py             # Voice I/O
│   │   ├── tray.py              # System tray
│   │   ├── auth.py              # Password protection
│   │   ├── config.py            # Configuration
│   │   └── platform.py          # Cross-platform utilities
│   ├── skills/
│   │   ├── __init__.py          # Plugin system with @command decorator
│   │   ├── agent.py             # Multi-agent orchestration
│   │   ├── iot.py               # IoT hub: MQTT, webhooks, rules, sensors
│   │   ├── iot_bridge.py        # Real device bridges (Hue, Kasa, HA, SSDP, REST)
│   │   ├── ble_scanner.py       # BLE device scanning
│   │   ├── p2p.py               # P2P mesh networking
│   │   ├── image_gen.py         # Pollinations.ai + HuggingFace image gen
│   │   ├── image_browser.py     # Local image management
│   │   ├── screen_capture.py    # Screenshot + GIF recording
│   │   ├── meeting_notes.py     # Meeting transcription + AI summary
│   │   ├── model_manager.py     # Provider rate limits & switching
│   │   ├── memory.py            # RAG memory system
│   │   ├── calendar_gcal.py     # Google Calendar
│   │   ├── slides.py            # PowerPoint generation
│   │   ├── pdf_gen.py           # PDF generation
│   │   ├── net_tools.py         # Public IP, ping
│   │   ├── language.py          # Translation, definitions
│   │   ├── system_control.py    # System info
│   │   ├── text_tools.py        # Encode/decode, uuid, ascii art
│   │   ├── weather.py           # Weather lookup
│   │   ├── video_gen.py         # Video generation
│   │   └── self_update.py       # LLM-powered self-modification
│   ├── api/
│   │   └── app.py               # FastAPI web server
│   └── agents/
│       ├── basic.md             # Basic agent prompt
│       └── vibe-coder.md        # Vibe coder agent prompt
├── tests/
│   ├── run_all.py               # Test runner
│   ├── test_iot_network.py      # 14 IoT/P2P/BLE/bridge tests
│   ├── test_agent.py
│   ├── test_memory.py
│   ├── test_platform.py
│   ├── test_skills_init.py
│   └── test_ui.py
├── requirements.txt
├── config.yaml
├── start.bat                    # Text-mode launcher
├── start_tui.bat                # TUI launcher
└── start_web.bat                # Web UI launcher
```

---

## Testing

```bash
python tests/run_all.py
```
26 tests across 6 modules covering agent system, memory, IoT, P2P, BLE, bridges, platform, UI, and plugin system.

---

## Security

- Bridge credentials (Hue usernames) are encrypted at rest via AES-256-GCM with a machine-derived key
- Home Assistant tokens come from environment variables, never stored in files
- Webhook server has no authentication — only enable on trusted networks
- P2P uses plain UDP with no encryption — LAN-only, do not route to internet
- TP-Link Kasa uses unencrypted binary protocol — LAN-only
