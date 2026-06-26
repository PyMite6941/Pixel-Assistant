"""
IoT Hub for Pixel Assistant.
MQTT, webhooks, device registry, rules engine, and sensor simulation.
MQTT requires paho-mqtt (optional). Everything else is stdlib-only.
"""
import json
import logging
import random
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_IOT_DIR = Path(__file__).parent.parent / "functionalities" / "iot"
_DEVICES_FILE = _IOT_DIR / "devices.json"
_RULES_FILE = _IOT_DIR / "rules.json"

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ensure_dir():
    _IOT_DIR.mkdir(parents=True, exist_ok=True)


def _load_json(path):
    _ensure_dir()
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load %s: %s", path, e)
    return []


def _save_json(path, data):
    _ensure_dir()
    try:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return True
    except OSError as e:
        logger.error("Failed to save %s: %s", path, e)
        return False


def _devices():
    return _load_json(_DEVICES_FILE)


def _save_devices(devices):
    return _save_json(_DEVICES_FILE, devices)


def _rules():
    return _load_json(_RULES_FILE)


def _save_rules(rules):
    return _save_json(_RULES_FILE, rules)


def _get_subnet():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


def _notify(message):
    try:
        if sys.platform == "win32":
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, message, "Pixel Assistant IoT", 0)
        elif sys.platform == "darwin":
            subprocess.run(
                ["osascript", "-e", f'display notification "{message}" with title "Pixel Assistant IoT"'],
                capture_output=True, timeout=5,
            )
        else:
            subprocess.run(["notify-send", "Pixel Assistant IoT", message], capture_output=True, timeout=5)
    except Exception as e:
        logger.warning("Notification failed: %s", e)


def _run_pixel_command(command):
    try:
        from skills import dispatch
        parts = command.strip("/").split(None, 1)
        cmd_name = parts[0]
        cmd_args = parts[1] if len(parts) > 1 else ""
        result = dispatch(cmd_name, cmd_args, None)
        logger.info("Command result: %s", result)
    except Exception as e:
        logger.warning("Command execution failed: %s", e)


# ---------------------------------------------------------------------------
# Device Registry
# ---------------------------------------------------------------------------

def device_register(device_id, name, device_type, protocol, topic="", unit=""):
    devices = _devices()
    for d in devices:
        if d["id"] == device_id:
            return f"Device '{device_id}' already exists."
    devices.append({
        "id": device_id,
        "name": name,
        "type": device_type,
        "protocol": protocol,
        "topic": topic,
        "unit": unit,
        "value": None,
        "last_seen": None,
        "metadata": {},
    })
    if _save_devices(devices):
        return f"Registered device '{device_id}' ({name})."
    return "Failed to register device."


def device_list() -> list[dict]:
    """Return the raw device list (always a list, never a string)."""
    return _devices()


def device_list_display() -> str:
    """Return a human-readable table of all registered devices."""
    devices = _devices()
    if not devices:
        return "No devices registered."
    lines = [f"{'ID':<24} {'Name':<30} {'Type':<10} {'Value':<12} {'Last Seen':<22}"]
    lines.append("-" * 100)
    for d in devices:
        val = f"{d.get('value', '')}{d.get('unit', '')}" if d.get('value') is not None else "-"
        seen = (d.get('last_seen') or "-")[:19]
        lines.append(f"{d['id']:<24} {d['name']:<30} {d.get('type', ''):<10} {val:<12} {seen:<22}")
    return "\n".join(lines)


def device_get(device_id):
    devices = _devices()
    for d in devices:
        if d["id"] == device_id:
            return d
    return None


def device_remove(device_id):
    devices = _devices()
    new_devices = [d for d in devices if d["id"] != device_id]
    if len(new_devices) == len(devices):
        return f"Device '{device_id}' not found."
    if _save_devices(new_devices):
        return f"Removed device '{device_id}'."
    return "Failed to remove device."


def device_update_value(device_id, value):
    devices = _devices()
    for d in devices:
        if d["id"] == device_id:
            d["value"] = value
            d["last_seen"] = datetime.now(timezone.utc).isoformat()
            _save_devices(devices)
            _evaluate_rules_for(device_id)
            return True
    return False


def device_discover():
    discovered = []
    subnet = _get_subnet()
    if not subnet:
        return "Could not determine local subnet for discovery."
    ports = [1883, 8883, 5683, 80, 8080, 443, 22, 23]
    base = ".".join(subnet.split(".")[:3])
    sem = threading.Semaphore(100)
    lock = threading.Lock()

    def _scan(host, port):
        with sem:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(0.5)
                if s.connect_ex((host, port)) == 0:
                    now = datetime.now(timezone.utc).isoformat()
                    entry = {
                        "id": f"{host.replace('.', '-')}-{port}",
                        "name": f"{host}:{port}",
                        "type": "unknown",
                        "protocol": "tcp",
                        "topic": "",
                        "unit": "",
                        "value": None,
                        "last_seen": now,
                        "metadata": {"host": host, "port": port},
                    }
                    with lock:
                        discovered.append(entry)
                s.close()
            except Exception:
                pass

    threads = []
    for i in range(1, 255):
        host = f"{base}.{i}"
        for port in ports:
            t = threading.Thread(target=_scan, args=(host, port), daemon=True)
            t.start()
            threads.append(t)

    for t in threads:
        t.join(timeout=10)

    if discovered:
        existing = _devices()
        existing_ids = {d["id"] for d in existing}
        for d in discovered:
            if d["id"] not in existing_ids:
                existing.append(d)
                existing_ids.add(d["id"])
        _save_devices(existing)

    return f"Discovered {len(discovered)} device(s)." if discovered else "No devices found on network."


# ---------------------------------------------------------------------------
# MQTT Client (optional — requires paho-mqtt)
# ---------------------------------------------------------------------------

_mqtt_client = None
_mqtt_connected = False
_mqtt_subscriptions = {}
_mqtt_message_log = []


def _check_mqtt():
    try:
        import paho.mqtt.client as mqtt
        return mqtt
    except ImportError:
        return None


def mqtt_connect(broker="localhost", port=1883, client_id="pixel_assistant"):
    global _mqtt_client, _mqtt_connected

    mqtt = _check_mqtt()
    if mqtt is None:
        return "MQTT unavailable: paho-mqtt is not installed. Run: pip install paho-mqtt"
    if _mqtt_connected:
        return "Already connected to MQTT broker."

    try:
        client = mqtt.Client(client_id=client_id)

        def _on_connect(c, userdata, flags, rc):
            global _mqtt_connected
            _mqtt_connected = rc == 0
            for topic in list(_mqtt_subscriptions.keys()):
                c.subscribe(topic)
            logger.info("MQTT connected (rc=%d)", rc)

        def _on_message(c, userdata, msg):
            _mqtt_message_log.append({
                "topic": msg.topic,
                "payload": msg.payload.decode("utf-8", errors="replace"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            if msg.topic in _mqtt_subscriptions:
                cb = _mqtt_subscriptions[msg.topic]
                if cb:
                    try:
                        cb(msg.topic, msg.payload.decode("utf-8", errors="replace"))
                    except Exception as e:
                        logger.error("MQTT callback error: %s", e)

        client.on_connect = _on_connect
        client.on_message = _on_message
        client.connect(broker, port, keepalive=60)
        client.loop_start()
        _mqtt_client = client
        return f"Connected to MQTT broker at {broker}:{port}."
    except Exception as e:
        return f"MQTT connection failed: {e}"


def mqtt_disconnect():
    global _mqtt_client, _mqtt_connected
    if _mqtt_client is None:
        return "Not connected to any MQTT broker."
    try:
        _mqtt_client.loop_stop()
        _mqtt_client.disconnect()
        _mqtt_client = None
        _mqtt_connected = False
        _mqtt_subscriptions.clear()
        return "Disconnected from MQTT broker."
    except Exception as e:
        return f"MQTT disconnect failed: {e}"


def mqtt_publish(topic, message):
    if _mqtt_client is None:
        return "Not connected to MQTT broker."
    try:
        result = _mqtt_client.publish(topic, message)
        return f"Published to '{topic}' (rc={result.rc})."
    except Exception as e:
        return f"MQTT publish failed: {e}"


def mqtt_subscribe(topic, callback=None):
    if topic in _mqtt_subscriptions:
        return f"Already subscribed to '{topic}'."
    _mqtt_subscriptions[topic] = callback
    if _mqtt_connected and _mqtt_client:
        _mqtt_client.subscribe(topic)
    return f"Subscribed to '{topic}'."


def mqtt_status():
    mqtt = _check_mqtt()
    lines = [f"MQTT Available: {'Yes' if mqtt else 'No (install paho-mqtt)'}"]
    lines.append(f"Connected: {_mqtt_connected}")
    lines.append(f"Active Subscriptions: {', '.join(_mqtt_subscriptions.keys()) or 'None'}")
    lines.append(f"Messages Captured: {len(_mqtt_message_log)}")
    return "\n".join(lines)


def mqtt_listen(duration=10):
    if _mqtt_client is None:
        return "Not connected to MQTT broker."
    before = len(_mqtt_message_log)
    time.sleep(duration)
    new = _mqtt_message_log[before:]
    if not new:
        return f"No messages received in {duration}s."
    lines = [f"Messages received in last {duration}s:"]
    for m in new:
        lines.append(f"  [{m['timestamp'][:19]}] {m['topic']}: {m['payload'][:200]}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Webhook Server (stdlib http.server)
# ---------------------------------------------------------------------------

_WEBHOOK_SERVER = None
_WEBHOOK_THREAD = None
_WEBHOOK_PORT = 8080


class _WebhookHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parts = self.path.strip("/").split("/")
        if len(parts) >= 2 and parts[0] == "webhook":
            device = device_get(parts[1])
            if device:
                self._send_json(HTTPStatus.OK, device)
            else:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "device not found"})
        else:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length > 0 else b"{}"
        parts = self.path.strip("/").split("/")
        if len(parts) >= 2 and parts[0] == "webhook":
            did = parts[1]
            try:
                data = json.loads(body.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid JSON"})
                return
            value = data.get("value")
            if value is not None:
                device_update_value(did, value)
                self._send_json(HTTPStatus.OK, {"status": "ok", "device": did, "value": value})
            else:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "missing value field"})
        else:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def _send_json(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, format, *args):
        logger.debug("Webhook: %s", format % args)


def webhook_start(port=8080):
    global _WEBHOOK_SERVER, _WEBHOOK_THREAD, _WEBHOOK_PORT
    if _WEBHOOK_SERVER is not None:
        return f"Webhook server already running on port {_WEBHOOK_PORT}."
    _WEBHOOK_PORT = port
    try:
        _WEBHOOK_SERVER = HTTPServer(("0.0.0.0", port), _WebhookHandler)
        _WEBHOOK_THREAD = threading.Thread(target=_WEBHOOK_SERVER.serve_forever, daemon=True)
        _WEBHOOK_THREAD.start()
        return (f"Webhook server started on port {port}. "
                f"POST /webhook/<device_id> to update, GET to read.\n"
                "[yellow]SECURITY: No authentication. Anyone on the LAN can POST. "
                "Only use on trusted networks.[/yellow]")
    except OSError as e:
        _WEBHOOK_SERVER = None
        return f"Failed to start webhook server: {e}"


def webhook_stop():
    global _WEBHOOK_SERVER, _WEBHOOK_THREAD
    if _WEBHOOK_SERVER is None:
        return "Webhook server is not running."
    try:
        _WEBHOOK_SERVER.shutdown()
        _WEBHOOK_SERVER.server_close()
        _WEBHOOK_SERVER = None
        _WEBHOOK_THREAD = None
        return "Webhook server stopped."
    except Exception as e:
        return f"Failed to stop webhook server: {e}"


def webhook_status():
    if _WEBHOOK_SERVER is not None:
        return f"Webhook server running on port {_WEBHOOK_PORT}."
    return "Webhook server is not running."


# ---------------------------------------------------------------------------
# Rules Engine
# ---------------------------------------------------------------------------

def rule_add(name, trigger_device, condition, threshold, action_type, action_message):
    rules = _rules()
    rule_id = f"rule-{len(rules) + 1}"
    rules.append({
        "id": rule_id,
        "name": name,
        "trigger": {
            "type": "value",
            "device": trigger_device,
            "condition": condition,
            "threshold": threshold,
        },
        "action": {
            "type": action_type,
            "message": action_message,
        },
        "enabled": True,
    })
    if _save_rules(rules):
        return f"Rule '{rule_id}' created: {name}"
    return "Failed to create rule."


def rule_list():
    rules = _rules()
    if not rules:
        return "No rules defined."
    lines = [f"{'ID':<12} {'Name':<35} {'Device':<22} {'Condition':<14} {'Action':<20} {'Enabled':<8}"]
    lines.append("-" * 115)
    for r in rules:
        t = r.get("trigger", {})
        a = r.get("action", {})
        cond = f"{t.get('condition', '')} {t.get('threshold', '')}"
        action = f"{a.get('type', '')}: {str(a.get('message', ''))[:22]}"
        enabled = "Yes" if r.get("enabled", True) else "No"
        lines.append(f"{r['id']:<12} {r['name']:<35} {t.get('device', ''):<22} {cond:<14} {action:<20} {enabled:<8}")
    return "\n".join(lines)


def rule_remove(rule_id):
    rules = _rules()
    new_rules = [r for r in rules if r["id"] != rule_id]
    if len(new_rules) == len(rules):
        return f"Rule '{rule_id}' not found."
    if _save_rules(new_rules):
        return f"Removed rule '{rule_id}'."
    return "Failed to remove rule."


def rule_toggle(rule_id):
    rules = _rules()
    for r in rules:
        if r["id"] == rule_id:
            r["enabled"] = not r.get("enabled", True)
            _save_rules(rules)
            status = "enabled" if r["enabled"] else "disabled"
            return f"Rule '{rule_id}' {status}."
    return f"Rule '{rule_id}' not found."


def _check_condition(value, condition, threshold):
    try:
        if condition == ">":
            return value > threshold
        elif condition == "<":
            return value < threshold
        elif condition == ">=":
            return value >= threshold
        elif condition == "<=":
            return value <= threshold
        elif condition == "==":
            return value == threshold
        elif condition == "!=":
            return value != threshold
    except (TypeError, ValueError):
        return False
    return False


def _evaluate_rules_for(device_id):
    device = device_get(device_id)
    if device is None or device.get("value") is None:
        return
    rules = _rules()
    for r in rules:
        if not r.get("enabled", True):
            continue
        t = r.get("trigger", {})
        if t.get("device") != device_id:
            continue
        if _check_condition(device["value"], t.get("condition"), t.get("threshold")):
            _execute_action(r, device)


def rule_evaluate():
    rules = _rules()
    devices = {d["id"]: d for d in _devices()}
    triggered = []
    for r in rules:
        if not r.get("enabled", True):
            continue
        t = r.get("trigger", {})
        if t.get("type") != "value":
            continue
        device = devices.get(t.get("device"))
        if device is None or device.get("value") is None:
            continue
        if _check_condition(device["value"], t.get("condition"), t.get("threshold")):
            triggered.append(r)
            _execute_action(r, device)

    if not triggered:
        return "No rules triggered."
    result = [f"Triggered {len(triggered)} rule(s):"]
    for r in triggered:
        result.append(f"  - {r['name']} ({r['id']})")
    return "\n".join(result)


def _execute_action(rule, device):
    action = rule.get("action", {})
    action_type = action.get("type")
    message = action.get("message", "")
    message = message.replace("{device}", device.get("name", device["id"]))
    message = message.replace("{value}", str(device.get("value", "")))
    message = message.replace("{unit}", device.get("unit", ""))

    if action_type == "notify":
        _notify(message)
    elif action_type == "command":
        _run_pixel_command(message)
    elif action_type == "mqtt_publish":
        mqtt_publish(device.get("topic", "iot/alerts"), message)
    elif action_type == "webhook":
        http_get(message)
    logger.info("Rule action executed: %s -> %s", action_type, message)


# ---------------------------------------------------------------------------
# HTTP Triggers (stdlib only)
# ---------------------------------------------------------------------------

def http_get(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PixelAssistant/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read().decode("utf-8", errors="replace")[:500]
    except (urllib.error.URLError, OSError) as e:
        return f"HTTP GET failed: {e}"


def http_post(url, data):
    try:
        payload = json.dumps(data).encode()
        req = urllib.request.Request(url, data=payload, headers={
            "Content-Type": "application/json",
            "User-Agent": "PixelAssistant/1.0",
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read().decode("utf-8", errors="replace")[:500]
    except (urllib.error.URLError, OSError) as e:
        return f"HTTP POST failed: {e}"


# ---------------------------------------------------------------------------
# Sensor Simulation
# ---------------------------------------------------------------------------

_sim_threads = {}
_sim_running = False
_sim_lock = threading.Lock()


def sensor_simulate(device_id, min_val=0, max_val=100, interval=5):
    global _sim_running

    device = device_get(device_id)
    if device is None:
        return f"Device '{device_id}' not found. Register it first."
    with _sim_lock:
        if device_id in _sim_threads:
            return f"Simulation already running for '{device_id}'."
        _sim_running = True

        def _run():
            while True:
                with _sim_lock:
                    if device_id not in _sim_threads:
                        break
                value = round(random.uniform(min_val, max_val), 1)
                device_update_value(device_id, value)
                time.sleep(interval)

        t = threading.Thread(target=_run, daemon=True)
        _sim_threads[device_id] = t
        t.start()
    return f"Simulation started for '{device_id}' ({min_val}-{max_val}, every {interval}s)."


def sensor_stop(device_id):
    with _sim_lock:
        if device_id in _sim_threads:
            del _sim_threads[device_id]
            return f"Simulation stopped for '{device_id}'."
    return f"No simulation running for '{device_id}'."


def sensor_stop_all():
    global _sim_running
    with _sim_lock:
        _sim_running = False
        _sim_threads.clear()
    return "All simulations stopped."


# ---------------------------------------------------------------------------
# Command Registration
# Called from skills/__init__.py after module import to avoid circular imports.
# ---------------------------------------------------------------------------

_registered = False


def register_commands():
    global _registered
    if _registered:
        return
    _registered = True

    from skills import _COMMANDS, _ALIAS_MAP

    commands = [
        ("iot", cmd_iot, [],
         "IoT hub: /iot devices|register|remove|mqtt|webhook|rules|sensor|discover"),
        ("iot-devices", cmd_iot_devices, ["iot-list"],
         "List all registered IoT devices"),
        ("iot-register", cmd_iot_register, ["iot-add"],
         "Register a new IoT device. Usage: /iot-register <id> <name> <type> <protocol> [topic] [unit]"),
        ("iot-remove", cmd_iot_remove, ["iot-delete"],
         "Remove an IoT device. Usage: /iot-remove <device_id>"),
        ("iot-mqtt", cmd_iot_mqtt, [],
         "MQTT operations: connect|disconnect|publish|subscribe|status|listen"),
        ("iot-webhook", cmd_iot_webhook, [],
         "Webhook server: start|stop|status"),
        ("iot-rule", cmd_iot_rule, ["iot-rules"],
         "Rules engine: add|list|remove|toggle|evaluate"),
        ("iot-sensor", cmd_iot_sensor, ["iot-simulate"],
         "Sensor simulation: start|stop|stopall"),
    ]

    for name, handler, aliases, help_text in commands:
        _COMMANDS[name] = {
            "handler": handler,
            "help": help_text,
            "aliases": aliases,
            "name": name,
        }
        for alias in aliases:
            _ALIAS_MAP[alias] = name


# ---------------------------------------------------------------------------
# Command Handlers
# ---------------------------------------------------------------------------

def cmd_iot(args: str, assistant) -> str:
    parts = args.strip().split(None, 1)
    sub = parts[0].lower() if parts else ""
    subargs = parts[1] if len(parts) > 1 else ""

    dispatch_map = {
        "devices": cmd_iot_devices,
        "list": cmd_iot_devices,
        "register": cmd_iot_register,
        "add": cmd_iot_register,
        "remove": cmd_iot_remove,
        "delete": cmd_iot_remove,
        "mqtt": cmd_iot_mqtt,
        "webhook": cmd_iot_webhook,
        "rule": cmd_iot_rule,
        "rules": cmd_iot_rule,
        "sensor": cmd_iot_sensor,
        "simulate": cmd_iot_sensor,
        "discover": lambda a, _: device_discover(),
        "scan": lambda a, _: device_discover(),
    }

    handler = dispatch_map.get(sub)
    if handler:
        return handler(subargs, assistant)

    return ("IoT Hub — Commands:\n"
            "  /iot devices              List all devices\n"
            "  /iot register ...         Register a device\n"
            "  /iot remove <id>          Remove a device\n"
            "  /iot discover             Scan network for devices\n"
            "  /iot mqtt ...             MQTT operations\n"
            "  /iot webhook ...          Webhook server\n"
            "  /iot rule ...             Rules engine\n"
            "  /iot sensor ...           Sensor simulation\n"
            "Or use individual: /iot-devices, /iot-register, /iot-mqtt, etc.")


def cmd_iot_devices(args, assistant):
    return device_list_display()


def cmd_iot_register(args, assistant):
    parts = args.strip().split()
    if len(parts) < 4:
        return ("Usage: /iot-register <id> <name> <type> <protocol> [topic] [unit]\n"
                "  id:       unique device identifier (e.g., living-room-temp)\n"
                "  name:     human-readable name (e.g., Living Room Temperature)\n"
                "  type:     sensor|actuator|switch|hub|unknown\n"
                "  protocol: mqtt|http|zwave|zigbee|bluetooth|tcp|custom\n"
                "  topic:    MQTT topic (optional)\n"
                "  unit:     measurement unit (optional, e.g., °C, %)\n"
                "Example: /iot-register temp1 \"Living Room Temp\" sensor mqtt home/temp1 °C")
    device_id = parts[0]
    name = parts[1]
    device_type = parts[2].lower()
    protocol = parts[3].lower()
    topic = parts[4] if len(parts) > 4 else ""
    unit = " ".join(parts[5:]) if len(parts) > 5 else ""
    return device_register(device_id, name, device_type, protocol, topic, unit)


def cmd_iot_remove(args, assistant):
    device_id = args.strip()
    if not device_id:
        return "Usage: /iot-remove <device_id>"
    return device_remove(device_id)


def cmd_iot_mqtt(args, assistant):
    parts = args.strip().split(None, 1)
    sub = parts[0].lower() if parts else ""
    subargs = parts[1].strip() if len(parts) > 1 else ""

    if sub == "connect":
        cp = subargs.split()
        broker = cp[0] if cp else "localhost"
        port = int(cp[1]) if len(cp) > 1 else 1883
        return mqtt_connect(broker, port)
    elif sub == "disconnect":
        return mqtt_disconnect()
    elif sub == "publish":
        pub = subargs.split(None, 1)
        if len(pub) < 2:
            return "Usage: /iot mqtt publish <topic> <message>"
        return mqtt_publish(pub[0], pub[1])
    elif sub == "subscribe":
        sub_topic = subargs.split(None, 1)[0] if subargs else ""
        if not sub_topic:
            return "Usage: /iot mqtt subscribe <topic>"
        return mqtt_subscribe(sub_topic)
    elif sub == "status":
        return mqtt_status()
    elif sub == "listen":
        dur = int(subargs) if subargs.isdigit() else 10
        return mqtt_listen(dur)
    else:
        return ("MQTT Commands:\n"
                "  /iot mqtt connect [broker] [port]   Connect to broker\n"
                "  /iot mqtt disconnect                Disconnect\n"
                "  /iot mqtt publish <topic> <msg>     Publish message\n"
                "  /iot mqtt subscribe <topic>         Subscribe to topic\n"
                "  /iot mqtt status                    Show connection status\n"
                "  /iot mqtt listen [seconds]          Wait for messages")


def cmd_iot_webhook(args, assistant):
    parts = args.strip().split(None, 1)
    sub = parts[0].lower() if parts else ""
    subargs = parts[1].strip() if len(parts) > 1 else ""

    if sub == "start":
        port = int(subargs) if subargs.isdigit() else 8080
        return webhook_start(port)
    elif sub == "stop":
        return webhook_stop()
    elif sub == "status":
        return webhook_status()
    else:
        return ("Webhook Commands:\n"
                "  /iot webhook start [port]    Start webhook server\n"
                "  /iot webhook stop            Stop webhook server\n"
                "  /iot webhook status          Show server status")


def cmd_iot_rule(args, assistant):
    parts = args.strip().split(None, 1)
    sub = parts[0].lower() if parts else ""
    subargs = parts[1].strip() if len(parts) > 1 else ""

    if sub == "add":
        rp = subargs.split(None, 5)
        if len(rp) < 6:
            return ("Usage: /iot rule add <name> <device_id> <condition> <threshold> <action_type> <message>\n"
                    "  condition:   > < >= <= == !=\n"
                    "  action_type: notify|command|mqtt_publish|webhook\n"
                    "Example: /iot rule add \"High Temp Alert\" living-room-temp > 30 notify \"Temperature too high!\"")
        name, device_id, condition = rp[0], rp[1], rp[2]
        try:
            threshold = float(rp[3])
        except ValueError:
            return "Threshold must be a number."
        action_type = rp[4].lower()
        action_message = rp[5]
        return rule_add(name, device_id, condition, threshold, action_type, action_message)
    elif sub == "list":
        return rule_list()
    elif sub == "remove":
        if not subargs:
            return "Usage: /iot rule remove <rule_id>"
        return rule_remove(subargs)
    elif sub == "toggle":
        if not subargs:
            return "Usage: /iot rule toggle <rule_id>"
        return rule_toggle(subargs)
    elif sub == "evaluate":
        return rule_evaluate()
    else:
        return ("Rules Commands:\n"
                "  /iot rule add ...                Add a new rule\n"
                "  /iot rule list                   List all rules\n"
                "  /iot rule remove <id>            Remove a rule\n"
                "  /iot rule toggle <id>            Enable/disable a rule\n"
                "  /iot rule evaluate               Evaluate all rules")


def cmd_iot_sensor(args, assistant):
    parts = args.strip().split()
    if not parts:
        return ("Sensor Simulation Commands:\n"
                "  /iot sensor start <device_id> [min] [max] [interval]\n"
                "  /iot sensor stop <device_id>\n"
                "  /iot sensor stopall\n"
                "Example: /iot sensor start living-room-temp 15 35 3")

    sub = parts[0].lower()
    if sub == "start":
        if len(parts) < 2:
            return "Usage: /iot sensor start <device_id> [min] [max] [interval]"
        device_id = parts[1]
        min_val = float(parts[2]) if len(parts) > 2 else 0
        max_val = float(parts[3]) if len(parts) > 3 else 100
        interval = float(parts[4]) if len(parts) > 4 else 5
        return sensor_simulate(device_id, min_val, max_val, interval)
    elif sub == "stop":
        if len(parts) < 2:
            return "Usage: /iot sensor stop <device_id>"
        return sensor_stop(parts[1])
    elif sub == "stopall":
        return sensor_stop_all()
    else:
        return f"Unknown sensor command: {sub}"
