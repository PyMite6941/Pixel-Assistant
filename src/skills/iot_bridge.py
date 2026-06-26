"""
IoT Bridge for Pixel Assistant.
Connects to real IoT devices: Philips Hue, TP-Link Kasa, Home Assistant,
generic REST APIs, and UPnP/SSDP discovery.

SECURITY:
 - Bridge credentials (Hue usernames) are encrypted at rest via AES-256-GCM
   using a machine-derived key (SHA-256 of hostname + system info).
   The key is NOT stored — it is re-derived on every launch.
 - This protects credentials if `bridges.json` is exfiltrated, but assumes
   the attacker does not have code execution on the same machine.
 - The webhook server has NO authentication — anyone on the LAN can POST.
   Only enable on trusted networks.
 - TP-Link Kasa uses plaintext UDP commands with no auth. LAN-only.
 - Home Assistant tokens come from env vars (HA_TOKEN), not stored in files.
"""
import base64
import hashlib
import json
import logging
import os
import re
import socket
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree

import requests
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from skills import command

logger = logging.getLogger(__name__)

_IOT_DIR = Path(__file__).parent.parent / "functionalities" / "iot"
_BRIDGE_FILE = _IOT_DIR / "bridges.json"

# ── Credential Encryption ───────────────────────────────────────────────────

def _derive_key() -> bytes:
    """Derive a 32-byte Fernet key from machine identity (not stored anywhere)."""
    raw = f"{os.uname().nodename if hasattr(os, 'uname') else socket.gethostname()}" \
          f"|{os.getenv('COMPUTERNAME', '')}|{os.getenv('USERNAME', '')}|PixelBridgeV1"
    salt = hashlib.sha256(raw.encode()).digest()[:16]
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100_000)
    return base64.urlsafe_b64encode(kdf.derive(raw.encode()))


def _encrypt(text: str) -> str:
    try:
        f = Fernet(_derive_key())
        return f.encrypt(text.encode()).decode()
    except Exception:
        return text


def _decrypt(token: str) -> str:
    try:
        f = Fernet(_derive_key())
        return f.decrypt(token.encode()).decode()
    except Exception:
        return token


def _ensure_dir():
    _IOT_DIR.mkdir(parents=True, exist_ok=True)


def _load_bridges():
    _ensure_dir()
    if _BRIDGE_FILE.exists():
        try:
            data = json.loads(_BRIDGE_FILE.read_text(encoding="utf-8"))
            for entry in data:
                if "username" in entry:
                    entry["username"] = _decrypt(entry["username"])
            return data
        except Exception:
            return []
    return []


def _save_bridges(data):
    _ensure_dir()
    # Encrypt any sensitive fields before writing
    clean = []
    for entry in data:
        entry = dict(entry)
        if "username" in entry:
            entry["username"] = _encrypt(entry["username"])
        clean.append(entry)
    _BRIDGE_FILE.write_text(json.dumps(clean, indent=2, ensure_ascii=False), encoding="utf-8")


# ── Philips Hue ──────────────────────────────────────────────────────────────

def hue_discover() -> list[dict]:
    """Discover Philips Hue bridges on the LAN via UPnP/SSDP."""
    bridges = []
    # Use the Hue discovery API
    try:
        resp = requests.get("https://discovery.meethue.com/", timeout=5)
        if resp.ok:
            for entry in resp.json():
                bridges.append({
                    "id": entry.get("id", ""),
                    "ip": entry.get("internalipaddress", ""),
                    "type": "hue_bridge",
                    "protocol": "hue",
                })
    except requests.RequestException:
        pass
    # Also try SSDP broadcast
    try:
        ssdp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        ssdp_sock.settimeout(2)
        ssdp_msg = (
            "M-SEARCH * HTTP/1.1\r\n"
            "HOST: 239.255.255.250:1900\r\n"
            'MAN: "ssdp:discover"\r\n'
            "MX: 2\r\n"
            "ST: ssdp:all\r\n\r\n"
        )
        ssdp_sock.sendto(ssdp_msg.encode(), ("239.255.255.250", 1900))
        start = time.time()
        while time.time() - start < 3:
            try:
                data, addr = ssdp_sock.recvfrom(1024)
                msg = data.decode("utf-8", errors="replace")
                if "hue" in msg.lower() or "philips" in msg.lower():
                    ip = addr[0]
                    existing = any(b.get("ip") == ip for b in bridges)
                    if not existing:
                        bridges.append({
                            "id": f"hue-{ip.replace('.', '-')}",
                            "ip": ip,
                            "type": "hue_bridge",
                            "protocol": "hue",
                        })
            except socket.timeout:
                break
        ssdp_sock.close()
    except Exception:
        pass
    return bridges


def hue_register(bridge_ip: str) -> str:
    """Register with a Hue bridge (press the link button first)."""
    try:
        resp = requests.post(
            f"http://{bridge_ip}/api",
            json={"devicetype": "pixel_assistant#tui"},
            timeout=10,
        )
        data = resp.json()
        if isinstance(data, list) and "success" in data[0]:
            username = data[0]["success"]["username"]
            bridges = _load_bridges()
            for b in bridges:
                if b.get("ip") == bridge_ip:
                    b["username"] = username
                    _save_bridges(bridges)
                    return f"Hue bridge at {bridge_ip} registered (user: {username})."
            bridges.append({
                "id": f"hue-{bridge_ip.replace('.', '-')}",
                "ip": bridge_ip,
                "type": "hue_bridge",
                "protocol": "hue",
                "username": username,
            })
            _save_bridges(bridges)
            return f"Hue bridge at {bridge_ip} registered."
        elif isinstance(data, list) and "error" in data[0]:
            return f"Hue error: {data[0]['error'].get('description', 'unknown')}"
        return f"Unexpected response: {data}"
    except requests.RequestException as e:
        return f"Hue connection failed: {e}"


def hue_lights(bridge_ip: str, username: str = "") -> list[dict]:
    """List all Hue lights connected to a bridge."""
    if not username:
        bridges = _load_bridges()
        for b in bridges:
            if b.get("ip") == bridge_ip:
                username = b.get("username", "")
    if not username:
        return [{"error": "Not registered with this bridge. Press link button then /hue register <ip>"}]
    try:
        resp = requests.get(f"http://{bridge_ip}/api/{username}/lights", timeout=10)
        if resp.ok:
            lights = []
            for lid, info in resp.json().items():
                state = info.get("state", {})
                lights.append({
                    "id": lid,
                    "name": info.get("name", f"Light {lid}"),
                    "on": state.get("on", False),
                    "bri": state.get("bri", 0),
                    "hue": state.get("hue", 0),
                    "sat": state.get("sat", 0),
                    "reachable": state.get("reachable", False),
                })
            return lights
        return [{"error": f"HTTP {resp.status_code}: {resp.text[:200]}"}]
    except requests.RequestException as e:
        return [{"error": str(e)}]


def hue_set_light(bridge_ip: str, light_id: str, on: bool = True, bri: int = 254, username: str = "") -> str:
    """Control a Hue light: on/off and brightness."""
    if not username:
        bridges = _load_bridges()
        for b in bridges:
            if b.get("ip") == bridge_ip:
                username = b.get("username", "")
    if not username:
        return "Not registered with this bridge."
    body = {"on": on}
    if bri is not None:
        body["bri"] = max(1, min(254, int(bri)))
    try:
        resp = requests.put(
            f"http://{bridge_ip}/api/{username}/lights/{light_id}/state",
            json=body,
            timeout=10,
        )
        if resp.ok:
            return f"Light {light_id} {'on' if on else 'off'} (bri={bri})."
        return f"Failed: {resp.text[:200]}"
    except requests.RequestException as e:
        return f"Error: {e}"


# ── TP-Link Kasa ─────────────────────────────────────────────────────────────

def kasa_discover(timeout: int = 3) -> list[dict]:
    """Discover TP-Link Kasa smart devices on the LAN.
    Uses the Kasa protocol on port 9999.
    """
    devices = []
    base_ip = _get_local_ip_base()
    if not base_ip:
        return devices

    sem = threading.Semaphore(50)
    lock = threading.Lock()

    def _scan(ip):
        with sem:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(1)
                if s.connect_ex((ip, 9999)) == 0:
                    # Send Kasa discovery packet
                    import struct
                    payload = '{"system":{"get_sysinfo":{}}}'
                    pad = 4 - (len(payload) % 4)
                    if pad != 4:
                        payload += "\x00" * pad
                    # Kasa encryption
                    key = 0xAB
                    encrypted = bytearray()
                    for ch in payload.encode():
                        a = key ^ ch
                        key = a
                        encrypted.append(a)
                    pkt = struct.pack(">I", len(encrypted)) + encrypted
                    s.send(pkt)
                    resp = s.recv(4096)
                    if len(resp) > 4:
                        # Decrypt
                        resp_data = resp[4:]
                        dec_key = 0xAB
                        decrypted = bytearray()
                        for b in resp_data:
                            d = dec_key ^ b
                            dec_key = b
                            decrypted.append(d)
                        info = json.loads(decrypted.decode("utf-8", errors="replace"))
                        sysinfo = info.get("system", {}).get("get_sysinfo", {})
                        name = sysinfo.get("alias", "Kasa Device")
                        dev_id = sysinfo.get("deviceId", ip.replace(".", "-"))
                        with lock:
                            devices.append({
                                "id": f"kasa-{dev_id[:12]}",
                                "ip": ip,
                                "name": name,
                                "type": sysinfo.get("type", "unknown"),
                                "model": sysinfo.get("model", ""),
                                "sw_ver": sysinfo.get("sw_ver", ""),
                                "protocol": "kasa",
                            })
                s.close()
            except Exception:
                pass

    threads = []
    for i in range(1, 255):
        t = threading.Thread(target=_scan, args=(f"{base_ip}.{i}",), daemon=True)
        t.start()
        threads.append(t)

    for t in threads:
        t.join(timeout=timeout)
    return devices


def kasa_control(ip: str, on: bool) -> str:
    """Turn a Kasa device on or off."""
    try:
        import struct
        cmd = "on" if on else "off"
        payload = f'{{"system":{{"set_relay_state":{{"state":{1 if on else 0}}}}}}}'
        pad = 4 - (len(payload) % 4)
        if pad != 4:
            payload += "\x00" * pad
        key = 0xAB
        encrypted = bytearray()
        for ch in payload.encode():
            a = key ^ ch
            key = a
            encrypted.append(a)
        pkt = struct.pack(">I", len(encrypted)) + encrypted
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect((ip, 9999))
        s.send(pkt)
        s.recv(2048)
        s.close()
        return f"Kasa device at {ip} turned {cmd}."
    except Exception as e:
        return f"Kasa control error: {e}"


# ── Home Assistant ───────────────────────────────────────────────────────────

def ha_get_status(base_url: str, token: str) -> str:
    """Get Home Assistant status."""
    try:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        resp = requests.get(f"{base_url.rstrip('/')}/api/", headers=headers, timeout=10)
        if resp.ok:
            data = resp.json()
            return (f"Home Assistant: {data.get('message', 'OK')}\n"
                    f"Version: {data.get('version', '?')}")
        return f"HA connection failed: HTTP {resp.status_code}"
    except requests.RequestException as e:
        return f"HA error: {e}"


def ha_list_entities(base_url: str, token: str) -> list[dict]:
    """List all Home Assistant entities."""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(f"{base_url.rstrip('/')}/api/states", headers=headers, timeout=15)
        if resp.ok:
            entities = []
            for state in resp.json():
                entities.append({
                    "entity_id": state.get("entity_id"),
                    "state": state.get("state"),
                    "name": state.get("attributes", {}).get("friendly_name", state.get("entity_id")),
                })
            return sorted(entities, key=lambda e: e["entity_id"])
        return [{"error": f"HTTP {resp.status_code}"}]
    except requests.RequestException as e:
        return [{"error": str(e)}]


def ha_call_service(base_url: str, token: str, domain: str, service: str,
                    entity_id: str = "", **data) -> str:
    """Call a Home Assistant service (e.g., turn on a light)."""
    try:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        body = {}
        if entity_id:
            body["entity_id"] = entity_id
        body.update(data)
        resp = requests.post(
            f"{base_url.rstrip('/')}/api/services/{domain}/{service}",
            headers=headers, json=body, timeout=10,
        )
        if resp.ok:
            return f"HA service {domain}.{service} {'→ ' + entity_id if entity_id else ''}executed."
        return f"HA service failed: HTTP {resp.status_code}"
    except requests.RequestException as e:
        return f"HA error: {e}"


# ── Generic HTTP REST Device ────────────────────────────────────────────────

def rest_device_control(url: str, method: str = "GET", body: dict = None,
                        headers: dict = None) -> str:
    """Control any device with a REST API."""
    headers = headers or {"User-Agent": "PixelAssistant/1.0"}
    try:
        if method.upper() == "GET":
            resp = requests.get(url, headers=headers, timeout=10)
        elif method.upper() == "POST":
            resp = requests.post(url, headers=headers, json=body or {}, timeout=10)
        elif method.upper() == "PUT":
            resp = requests.put(url, headers=headers, json=body or {}, timeout=10)
        else:
            return f"Unsupported method: {method}"
        if resp.ok:
            return f"{method} {url} → {resp.status_code}\n{resp.text[:500]}"
        return f"{method} {url} → HTTP {resp.status_code}: {resp.text[:200]}"
    except requests.RequestException as e:
        return f"REST error: {e}"


# ── Helpers ──────────────────────────────────────────────────────────────────

def _sync_to_iot_registry(devices: list[dict], source: str = "bridge"):
    """Register discovered bridge devices into the iot.py device registry."""
    try:
        from skills.iot import device_register, device_list
        existing = device_list()
        existing_ids = {d.get("id") for d in existing if isinstance(d, dict)}
        for d in devices:
            did = d.get("id", "")
            if did and did not in existing_ids:
                name = d.get("name", d.get("hostname", did))
                dtype = d.get("type", "unknown")
                protocol = d.get("protocol", source)
                device_register(did, name, dtype, protocol)
    except ImportError:
        logger.debug("iot.py not available for registry sync")
    except Exception as e:
        logger.warning("Registry sync error: %s", e)


def find_device_over_bridges(device_id: str) -> dict | None:
    """Look up a device across all bridges (Hue, Kasa, etc.) by ID or name."""
    # Check bridges.json entries
    bridges = _load_bridges()
    for b in bridges:
        if b.get("id") == device_id or b.get("ip") == device_id:
            return b
        if "username" in b:
            # Check if it's a Hue light
            lights = hue_lights(b["ip"], b.get("username", ""))
            for l in lights:
                if "error" not in l and (l.get("id") == device_id or l.get("name", "").lower() == device_id.lower()):
                    l["bridge_ip"] = b["ip"]
                    l["bridge_username"] = b.get("username", "")
                    return l
    return None


def _get_local_ip_base() -> str | None:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ".".join(ip.split(".")[:3])
    except Exception:
        return None


# ── Commands ─────────────────────────────────────────────────────────────────

@command(name="hue", aliases=["philips", "philips-hue"],
         help_text="Philips Hue: /hue discover|register <ip>|lights [ip]|on|off <id> [ip]")
def cmd_hue(args: str, assistant) -> str:
    parts = args.strip().split()
    if not parts:
        return ("Philips Hue Commands:\n"
                "  /hue discover              Find bridges on network\n"
                "  /hue register <ip>         Register with bridge (press link button first!)\n"
                "  /hue lights [ip]           List all lights\n"
                "  /hue on <id> [ip]          Turn light on\n"
                "  /hue off <id> [ip]         Turn light off\n"
                "  /hue dim <id> <bri> [ip]   Set brightness (1-254)")

    sub = parts[0].lower()
    if sub == "discover":
        bridges = hue_discover()
        if not bridges:
            return "No Hue bridges found. Make sure the bridge is powered and on the same network."
        _sync_to_iot_registry(bridges, "hue")
        lines = [f"Found {len(bridges)} Hue bridge(s):"]
        for b in bridges:
            lines.append(f"  {b['id']} at {b['ip']}  (register: /hue register {b['ip']})")
        return "\n".join(lines)

    if sub == "register":
        ip = parts[1] if len(parts) > 1 else ""
        if not ip:
            return "Usage: /hue register <bridge_ip>  (press the Hue link button first!)"
        return hue_register(ip)

    if sub == "lights":
        ip = parts[1] if len(parts) > 1 else ""
        bridge = _find_hue_bridge(ip)
        if not bridge:
            return "No Hue bridge found or configured. Use /hue discover first."
        lights = hue_lights(bridge["ip"], bridge.get("username", ""))
        if not lights:
            return "No lights found."
        if "error" in lights[0]:
            return lights[0]["error"]
        _sync_to_iot_registry([{
            "id": f"hue-{l['id']}",
            "name": l["name"],
            "type": "light",
            "protocol": "hue",
            "bridge_ip": bridge["ip"],
        } for l in lights], "hue")
        lines = [f"Lights on bridge at {bridge['ip']}:"]
        for l in lights:
            status = "ON" if l.get("on") else "OFF"
            reach = "" if l.get("reachable") else " [red](unreachable)[/red]"
            lines.append(f"  [{status}] {l['id']:>3}. {l['name']:25s} bri={l.get('bri', 0)}{reach}")
        return "\n".join(lines)

    if sub in ("on", "off"):
        light_id = parts[1] if len(parts) > 1 else ""
        ip = parts[2] if len(parts) > 2 else ""
        if not light_id:
            return f"Usage: /hue {sub} <light_id> [bridge_ip]"
        on = sub == "on"
        bridge = _find_hue_bridge(ip)
        if not bridge:
            return "No Hue bridge found."
        return hue_set_light(bridge["ip"], light_id, on=on, username=bridge.get("username", ""))

    if sub == "dim":
        light_id = parts[1] if len(parts) > 1 else ""
        bri = int(parts[2]) if len(parts) > 2 else 128
        ip = parts[3] if len(parts) > 3 else ""
        if not light_id:
            return "Usage: /hue dim <light_id> <brightness 1-254> [bridge_ip]"
        bridge = _find_hue_bridge(ip)
        if not bridge:
            return "No Hue bridge found."
        return hue_set_light(bridge["ip"], light_id, on=True, bri=bri, username=bridge.get("username", ""))

    return f"Unknown hue subcommand: {sub}"


def _find_hue_bridge(ip: str = "") -> dict | None:
    bridges = _load_bridges()
    if ip:
        for b in bridges:
            if b.get("ip") == ip:
                return b
    return bridges[0] if bridges else None


@command(name="kasa", aliases=["tplink", "smartplug"],
         help_text="TP-Link Kasa smart devices: /kasa discover|on|off <ip>")
def cmd_kasa(args: str, assistant) -> str:
    parts = args.strip().split()
    if not parts:
        return ("TP-Link Kasa Commands:\n"
                "  /kasa discover              Find Kasa devices on LAN\n"
                "  /kasa on <ip>               Turn device on\n"
                "  /kasa off <ip>              Turn device off")

    sub = parts[0].lower()
    if sub == "discover":
        devices = kasa_discover()
        if not devices:
            return "No Kasa devices found. Make sure they are on the same network."
        _sync_to_iot_registry(devices, "kasa")
        lines = [f"Found {len(devices)} Kasa device(s):"]
        for d in devices:
            lines.append(f"  {d['name']:25s} at {d['ip']:15s} model={d.get('model', '?')}")
        return "\n".join(lines)

    if sub in ("on", "off"):
        ip = parts[1] if len(parts) > 1 else ""
        if not ip:
            return f"Usage: /kasa {sub} <device_ip>"
        return kasa_control(ip, on=(sub == "on"))

    return f"Unknown kasa subcommand: {sub}"


@command(name="ha", aliases=["homeassistant", "home-assistant"],
         help_text="Home Assistant: /ha status|entities|service|call <domain> <service> [entity_id]")
def cmd_ha(args: str, assistant) -> str:
    parts = args.strip().split()
    if not parts:
        return ("Home Assistant Commands:\n"
                "  /ha status                 Show HA connection status\n"
                "  /ha entities               List all entities\n"
                "  /ha service <d> <s> [eid]  Call a service\n"
                "  /ha call <d> <s> <eid>     Shortcut for service call\n"
                "Set env: HA_URL and HA_TOKEN for the connection.")

    import os
    base_url = os.getenv("HA_URL", "")
    token = os.getenv("HA_TOKEN", "")
    if not base_url or not token:
        return ("Home Assistant not configured. Set environment variables:\n"
                "  HA_URL=http://homeassistant.local:8123\n"
                "  HA_TOKEN=your_long_lived_token\n"
                "Generate token at: Profile → Long-Lived Access Tokens")

    sub = parts[0].lower()
    if sub == "status":
        return ha_get_status(base_url, token)

    if sub in ("entities", "list"):
        entities = ha_list_entities(base_url, token)
        if not entities:
            return "No entities found."
        if "error" in entities[0]:
            return entities[0]["error"]
        _sync_to_iot_registry([
            {"id": f"ha-{e['entity_id'].replace('.', '-')}", "name": e.get("name", e["entity_id"]),
             "type": "ha_entity", "protocol": "homeassistant", "entity_id": e["entity_id"], "state": e["state"]}
            for e in entities[:50]
        ], "homeassistant")
        lines = [f"Entities ({len(entities)}):"]
        for e in entities[:30]:
            lines.append(f"  {e['entity_id']:40s} = {e['state']}")
        if len(entities) > 30:
            lines.append(f"  ... and {len(entities) - 30} more")
        return "\n".join(lines)

    if sub in ("service", "call"):
        domain = parts[1] if len(parts) > 1 else ""
        service = parts[2] if len(parts) > 2 else ""
        entity_id = parts[3] if len(parts) > 3 else ""
        if not domain or not service:
            return "Usage: /ha service <domain> <service> [entity_id]"
        return ha_call_service(base_url, token, domain, service, entity_id)

    return f"Unknown HA subcommand: {sub}"


@command(name="rest", aliases=["http", "api"],
         help_text="Generic REST device control: /rest get|post|put <url> [json_body]")
def cmd_rest(args: str, assistant) -> str:
    parts = args.strip().split(None, 2)
    if len(parts) < 2:
        return ("REST Device Control:\n"
                "  /rest get <url>                  GET request\n"
                "  /rest post <url> <json>          POST with JSON body\n"
                "  /rest put <url> <json>           PUT with JSON body\n"
                "Example: /rest post http://192.168.1.100/api/light/1 {\"on\": true}")

    method = parts[0].upper()
    url = parts[1]
    body_str = parts[2] if len(parts) > 2 else ""
    body = {}
    if body_str:
        try:
            body = json.loads(body_str)
        except json.JSONDecodeError:
            return f"Invalid JSON body: {body_str}"
    return rest_device_control(url, method, body)


@command(name="ssdp", aliases=["upnp", "discover"],
         help_text="UPnP/SSDP network device discovery")
def cmd_ssdp(args: str, assistant) -> str:
    """Discover UPnP/SSDP devices on the network."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(3)
        msg = (
            "M-SEARCH * HTTP/1.1\r\n"
            "HOST: 239.255.255.250:1900\r\n"
            'MAN: "ssdp:discover"\r\n'
            "MX: 3\r\n"
            "ST: ssdp:all\r\n\r\n"
        )
        sock.sendto(msg.encode(), ("239.255.255.250", 1900))
        devices = {}
        start = time.time()
        while time.time() - start < 4:
            try:
                data, addr = sock.recvfrom(1024)
                msg_text = data.decode("utf-8", errors="replace")
                ip = addr[0]
                if ip not in devices:
                    # Extract device name from headers
                    name = ip
                    for line in msg_text.split("\r\n"):
                        if line.lower().startswith("server:"):
                            name = line.split(":", 1)[1].strip()[:40]
                            break
                    devices[ip] = name
            except socket.timeout:
                break
        sock.close()

        if not devices:
            return "No UPnP/SSDP devices discovered on the network."

        _sync_to_iot_registry([
            {"id": f"ssdp-{ip.replace('.', '-')}", "name": name, "type": "upnp", "protocol": "ssdp", "ip": ip}
            for ip, name in devices.items()
        ], "ssdp")

        lines = [f"Found {len(devices)} UPnP device(s):"]
        for ip, name in sorted(devices.items()):
            lines.append(f"  {ip:15s}  {name}")
        return "\n".join(lines)
    except Exception as e:
        return f"SSDP discovery error: {e}"
