"""
Pixel Assistant — FastAPI web UI.

Run locally:
    uvicorn src.api.app:app --reload --port 8000

Via Docker:
    docker compose up
"""
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

# ── Path setup ────────────────────────────────────────────────────────────────
SRC = Path(__file__).parent.parent
sys.path.insert(0, str(SRC))

from core_files.config import Config
from main import PixelAssistant, NOTES_FILE, _load_history, _save_history

# ── App ───────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app):
    try:
        from skills.p2p import start_discovery
        start_discovery(8000)
    except Exception:
        pass
    yield

app = FastAPI(title="Pixel Assistant", version="1.0", lifespan=lifespan)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Single shared assistant instance (thread-safe for reads; WS serialised per connection)
_config   = Config()
try:
    _assistant = PixelAssistant(provider=_config.provider)
except Exception as _e:
    import logging as _lg
    _lg.getLogger(__name__).error(f"Failed to initialise assistant: {_e}")
    _assistant = None


# ── Models ────────────────────────────────────────────────────────────────────

class NoteIn(BaseModel):
    text: str

class TodoIn(BaseModel):
    task: str

class CalEventIn(BaseModel):
    description: str

class EmailIn(BaseModel):
    description: str

class TeachIn(BaseModel):
    topic: str

class PromptIn(BaseModel):
    text: str
    mode: Optional[str] = "normal"   # "normal" | "bare"


# ── Root ──────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    index = STATIC_DIR / "index.html"
    return HTMLResponse(index.read_text(encoding="utf-8"))


# ── Status ────────────────────────────────────────────────────────────────────

@app.get("/api/status")
async def status():
    model = _config.smart_model if _config.get("smart_mode") else _config.model
    history = _load_history()
    return {
        "provider":  _assistant.provider,
        "model":     model,
        "smart":     bool(_config.get("smart_mode")),
        "turns":     len(history) // 2,
        "voice":     bool(_assistant.voice),
        "debug":     _assistant.debug,
    }


# ── Notes ─────────────────────────────────────────────────────────────────────

def _read_notes():
    if not NOTES_FILE.exists():
        return []
    return [l for l in NOTES_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]

def _write_notes(lines):
    NOTES_FILE.parent.mkdir(exist_ok=True)
    NOTES_FILE.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

@app.get("/api/notes")
async def get_notes():
    lines = _read_notes()
    return [{"id": i + 1, "text": l} for i, l in enumerate(lines)]

@app.post("/api/notes", status_code=201)
async def add_note(body: NoteIn):
    lines = _read_notes()
    lines.append(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] {body.text}")
    _write_notes(lines)
    return {"id": len(lines), "text": lines[-1]}

@app.delete("/api/notes/{note_id}")
async def delete_note(note_id: int):
    lines = _read_notes()
    if note_id < 1 or note_id > len(lines):
        raise HTTPException(404, "Note not found")
    removed = lines.pop(note_id - 1)
    _write_notes(lines)
    return {"deleted": removed}


# ── Todos ─────────────────────────────────────────────────────────────────────

TODO_FILE = SRC / "functionalities" / "todos.json"

def _read_todos():
    if not TODO_FILE.exists():
        return []
    try:
        return json.loads(TODO_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []

def _write_todos(todos):
    TODO_FILE.parent.mkdir(exist_ok=True)
    TODO_FILE.write_text(json.dumps(todos, indent=2, ensure_ascii=False), encoding="utf-8")

@app.get("/api/todos")
async def get_todos():
    return _read_todos()

@app.post("/api/todos", status_code=201)
async def add_todo(body: TodoIn):
    todos = _read_todos()
    item = {"task": body.task, "done": False, "added": datetime.now().strftime("%Y-%m-%d")}
    todos.append(item)
    _write_todos(todos)
    return {"id": len(todos), **item}

@app.patch("/api/todos/{todo_id}/done")
async def mark_done(todo_id: int):
    todos = _read_todos()
    if todo_id < 1 or todo_id > len(todos):
        raise HTTPException(404, "Todo not found")
    todos[todo_id - 1]["done"] = True
    _write_todos(todos)
    return todos[todo_id - 1]

@app.delete("/api/todos/{todo_id}")
async def delete_todo(todo_id: int):
    todos = _read_todos()
    if todo_id < 1 or todo_id > len(todos):
        raise HTTPException(404, "Todo not found")
    removed = todos.pop(todo_id - 1)
    _write_todos(todos)
    return {"deleted": removed["task"]}


# ── Calendar ──────────────────────────────────────────────────────────────────

@app.get("/api/calendar")
async def get_calendar(days: int = 7):
    try:
        from skills.calendar_gcal import list_events
        events = list_events(days=days)
        return [
            {
                "id":       e.get("id", "")[:12],
                "summary":  e.get("summary", "(no title)"),
                "start":    e.get("start", {}).get("dateTime") or e.get("start", {}).get("date"),
                "location": e.get("location", ""),
                "link":     e.get("htmlLink", ""),
            }
            for e in events
        ]
    except FileNotFoundError as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/api/calendar", status_code=201)
async def add_calendar_event(body: CalEventIn):
    result = _assistant._cmd_cal_add(body.description)
    return {"result": result}


# ── Email ─────────────────────────────────────────────────────────────────────

@app.post("/api/email")
async def draft_email(body: EmailIn):
    prompt = (
        f"Draft a professional email based on this request:\n{body.description}\n\n"
        "Reply ONLY with the email:\nSubject: <subject>\n\n<body>"
    )
    result = _assistant._ask_llm([{"role": "user", "content": prompt}])
    _assistant._printed = False
    return {"draft": result}


# ── Teach ─────────────────────────────────────────────────────────────────────

@app.post("/api/teach")
async def teach(body: TeachIn):
    # Returns raw markdown lesson text
    prompt = (
        f"You are a clear, engaging teacher. Teach me about: {body.topic}\n\n"
        "Structure your lesson with these headings:\n"
        f"## What is {body.topic}?\n## Core Concepts\n## Example\n## Common Mistakes\n"
        "## Keywords to explore next\n\nUse markdown. Be concise but complete."
    )
    result = _assistant._ask_llm([{"role": "user", "content": prompt}])
    _assistant._printed = False
    return {"topic": body.topic, "lesson": result}


# ── History ───────────────────────────────────────────────────────────────────

@app.get("/api/history")
async def get_history():
    return _load_history()

@app.delete("/api/history")
async def clear_history():
    _save_history([])
    _assistant.history.clear()
    return {"cleared": True}


# ── Settings API ──────────────────────────────────────────────────

@app.get("/api/settings")
async def get_settings():
    """Return all config settings."""
    return {k: _config.get(k) for k in [
        "provider", "model", "smart_model", "smart_mode",
        "max_history", "log_conversations", "debug",
        "slide_theme", "pdf_theme", "wake_word",
    ]}

@app.put("/api/settings")
async def update_settings(body: dict):
    """Update a config key/value."""
    for key, value in body.items():
        _config.set(key, value)
        if hasattr(_assistant, key):
            setattr(_assistant, key, value)
    return {"ok": True}

# ── Agent status ──────────────────────────────────────────────────

@app.get("/api/agents")
async def get_agents():
    """Return active agent info."""
    try:
        from skills.agent import _load_active_agents
        return _load_active_agents()
    except Exception:
        return []

# ── WebSocket chat ────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_chat(ws: WebSocket):
    await ws.accept()
    loop = asyncio.get_event_loop()

    # Per-connection assistant so token_callback doesn't bleed across sessions
    conn_assistant = PixelAssistant(provider=_config.provider)

    def _sanitize(text: str) -> str:
        return text.replace("\x00", "").strip()

    async def _send_token(token: str):
        await ws.send_json({"type": "token", "content": token})

    def _sync_token(token: str):
        asyncio.run_coroutine_threadsafe(_send_token(token), loop)

    conn_assistant.token_callback = _sync_token

    try:
        while True:
            data = await ws.receive_json()
            msg_type = data.get("type", "message")

            if msg_type == "ping":
                await ws.send_json({"type": "pong"})
                continue

            text = _sanitize(data.get("content", ""))
            if not text:
                continue

            await ws.send_json({"type": "start"})

            # Run blocking handle_prompt in thread pool so WS stays responsive
            response = await loop.run_in_executor(
                None, conn_assistant.handle_prompt, text
            )

            # For non-streaming responses (commands), send as a single message
            if not conn_assistant._printed:
                await ws.send_json({"type": "response", "content": response})
            else:
                # Streaming already pushed tokens; send full text for history
                await ws.send_json({"type": "done", "content": response})

            conn_assistant._printed = False

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await ws.send_json({"type": "error", "content": str(e)})
        except Exception:
            pass


# ── P2P API ────────────────────────────────────────────────────────────────────

@app.get("/api/peers")
async def get_peers():
    try:
        from skills.p2p import get_peers as _gp
        raw = _gp()
        result = []
        for p in raw:
            result.append({
                "id": f"{p.get('hostname','?')}|{p.get('ip','?')}|{p.get('port',8000)}",
                "hostname": p.get("hostname", "?"),
                "ip": p.get("ip", "?"),
                "port": p.get("port", 8000),
                "status": "connected" if p.get("connected", False) else "discovered",
                "uptime": p.get("uptime", 0),
                "version": p.get("version", ""),
                "device_count": p.get("device_count", 0),
                "agent_count": p.get("agent_count", 0),
                "last_seen": p.get("last_seen", ""),
            })
        return result
    except Exception as e:
        return []

@app.post("/api/p2p/connect")
async def p2p_connect(body: dict):
    try:
        from skills.p2p import connect_peer as _cp
        peer_id = body.get("peer_id", "")
        # Parse peer_id: "hostname|ip|port" or "ip" or "host:port"
        host, port = peer_id, 8000
        if "|" in peer_id:
            parts = peer_id.split("|")
            if len(parts) >= 2:
                host = parts[1] if parts[1] else parts[0]
                port = int(parts[2]) if len(parts) > 2 and parts[2] else 8000
        elif ":" in peer_id:
            parts = peer_id.split(":")
            host = parts[0]
            port = int(parts[1]) if len(parts) > 1 else 8000
        ok = _cp(host, port)
        return {"ok": ok}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.post("/api/p2p/disconnect")
async def p2p_disconnect(body: dict):
    try:
        from skills.p2p import disconnect_peer as _dp
        peer_id = body.get("peer_id", "")
        # Parse peer_id
        host = peer_id
        if "|" in peer_id:
            parts = peer_id.split("|")
            host = parts[1] if parts[1] else parts[0]
        elif ":" in peer_id:
            host = peer_id.split(":")[0]
        ok = _dp(host)
        return {"ok": ok}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ── IoT API ────────────────────────────────────────────────────────────────────

@app.get("/api/iot/devices")
async def iot_devices():
    try:
        from skills.iot import device_list
        devices = device_list()
        return devices if isinstance(devices, list) else []
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/api/iot/rules")
async def iot_rules():
    try:
        from skills.iot import rule_list
        return rule_list()
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/api/sys")
async def system_status():
    try:
        from skills.system_control import sys_info, sys_cpu, sys_memory, sys_disk, sys_network, sys_battery
        info = sys_info()
        info["cpu"] = sys_cpu()
        info["memory"] = sys_memory()
        info["disk"] = sys_disk()
        info["network"] = sys_network()
        try:
            info["battery"] = sys_battery()
        except Exception:
            info["battery"] = {"percent": None, "power_plugged": None}
        return info
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/api/processes")
async def system_processes(limit: int = 20):
    try:
        from skills.system_control import process_list
        return process_list(sort_by="cpu", limit=limit)
    except Exception as e:
        raise HTTPException(500, str(e))
