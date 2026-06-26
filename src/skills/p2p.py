"""
Peer-to-peer discovery and mesh networking for Pixel Assistant.
UDP multicast presence + direct HTTP handshake for peer connections.
"""
import json
import logging
import socket
import struct
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

MULTICAST_GROUP = "239.255.0.100"
MULTICAST_PORT = 12345
DISCOVERY_INTERVAL = 5
PEER_TIMEOUT = 30

_P2P_DIR = Path(__file__).parent.parent / "functionalities" / "p2p"
_PEERS_FILE = _P2P_DIR / "peers.json"

_peers = []
_lock = threading.Lock()
_discovery_sock = None
_discovery_thread = None
_discovery_active = False
_local_port = 8000
_start_time = time.time()

_VERSION = "1.0.0"


def _ensure_dir():
    _P2P_DIR.mkdir(parents=True, exist_ok=True)


def _load_peers():
    _ensure_dir()
    if _PEERS_FILE.exists():
        try:
            return json.loads(_PEERS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load peers: %s", e)
    return []


def _save_peers():
    _ensure_dir()
    try:
        _PEERS_FILE.write_text(
            json.dumps(_peers, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
    except OSError as e:
        logger.error("Failed to save peers: %s", e)


def _get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _get_device_count():
    try:
        from skills.iot import device_list as _dl
        raw = _dl()
        if isinstance(raw, list):
            return len(raw)
    except Exception:
        pass
    return 0


def _get_agent_count():
    try:
        from skills.agent import list_agents as _la
        agents = _la()
        if isinstance(agents, list):
            return len(agents)
    except Exception:
        pass
    return 0


def _update_peer(hostname, ip, port, version, device_count, agent_count, uptime):
    now = datetime.now(timezone.utc).isoformat()
    with _lock:
        for p in _peers:
            if p["hostname"] == hostname and p["ip"] == ip and p["port"] == port:
                p["version"] = version
                p["device_count"] = device_count
                p["agent_count"] = agent_count
                p["uptime"] = uptime
                p["last_seen"] = now
                _save_peers()
                return
        entry = {
            "hostname": hostname,
            "ip": ip,
            "port": port,
            "version": version,
            "device_count": device_count,
            "agent_count": agent_count,
            "uptime": uptime,
            "last_seen": now,
            "connected": False,
        }
        _peers.append(entry)
        _save_peers()


def _clean_stale_peers():
    now = datetime.now(timezone.utc)
    with _lock:
        before = len(_peers)
        keep = []
        for p in _peers:
            try:
                last = datetime.fromisoformat(p["last_seen"])
                if (now - last).total_seconds() < PEER_TIMEOUT:
                    keep.append(p)
            except (ValueError, TypeError):
                keep.append(p)
        _peers[:] = keep
        if len(keep) != before:
            _save_peers()


def _send_heartbeat():
    ip = _get_local_ip()
    payload = json.dumps({
        "type": "pixel_presence",
        "hostname": socket.gethostname(),
        "port": _local_port,
        "version": _VERSION,
        "device_count": _get_device_count(),
        "agent_count": _get_agent_count(),
        "uptime_seconds": int(time.time() - _start_time),
    }).encode()

    ttl = struct.pack("b", 1)
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)
        sock.settimeout(1)
        sock.sendto(payload, (MULTICAST_GROUP, MULTICAST_PORT))
        sock.close()
    except OSError as e:
        logger.warning("Heartbeat send failed: %s", e)


def _discovery_listener():
    global _discovery_sock
    while _discovery_active:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("", MULTICAST_PORT))

            mreq = struct.pack("4sl", socket.inet_aton(MULTICAST_GROUP), socket.INADDR_ANY)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            sock.settimeout(2)
            _discovery_sock = sock

            while _discovery_active:
                try:
                    data, addr = sock.recvfrom(4096)
                except socket.timeout:
                    continue
                except OSError:
                    break

                try:
                    msg = json.loads(data.decode("utf-8", errors="replace"))
                except json.JSONDecodeError:
                    continue

                if msg.get("type") != "pixel_presence":
                    continue

                hostname = msg.get("hostname", "unknown")
                port = msg.get("port", 8000)
                version = msg.get("version", "0.0.0")
                device_count = msg.get("device_count", 0)
                agent_count = msg.get("agent_count", 0)
                uptime = msg.get("uptime_seconds", 0)

                remote_ip = addr[0]
                if remote_ip == _get_local_ip():
                    continue

                _update_peer(hostname, remote_ip, port, version, device_count, agent_count, uptime)

            sock.close()
            _discovery_sock = None
        except OSError as e:
            if _discovery_active:
                logger.warning("Discovery listener error: %s", e)
                if _discovery_sock:
                    try:
                        _discovery_sock.close()
                    except OSError:
                        pass
                    _discovery_sock = None
                time.sleep(3)


def start_discovery(port=8000):
    global _discovery_active, _discovery_thread, _local_port
    if _discovery_active:
        logger.info("Discovery already running")
        return
    _local_port = port
    _discovery_active = True

    global _peers
    _peers = _load_peers()

    _discovery_thread = threading.Thread(target=_discovery_listener, daemon=True)
    _discovery_thread.start()

    def _heartbeat_loop():
        while _discovery_active:
            _send_heartbeat()
            _clean_stale_peers()
            for _ in range(DISCOVERY_INTERVAL):
                if not _discovery_active:
                    break
                time.sleep(1)

    t = threading.Thread(target=_heartbeat_loop, daemon=True)
    t.start()

    logger.info("P2P discovery started on port %d", port)


def stop_discovery():
    global _discovery_active, _discovery_sock, _discovery_thread
    _discovery_active = False
    if _discovery_sock:
        try:
            _discovery_sock.close()
        except OSError:
            pass
        _discovery_sock = None
    _discovery_thread = None
    logger.info("P2P discovery stopped")


def get_peers():
    _clean_stale_peers()
    with _lock:
        return list(_peers)


def get_status():
    if _discovery_active:
        return (f"Active (UDP {MULTICAST_GROUP}:{MULTICAST_PORT})\n"
                "[yellow]SECURITY: P2P uses plain UDP with no encryption or authentication. "
                "LAN-only. Do not route to the internet.[/yellow]")
    return "Inactive"


def discover_once(timeout: int = 3) -> str:
    """Send one discovery broadcast and collect responses."""
    count_before = len(get_peers())
    _send_heartbeat()
    time.sleep(timeout)
    _clean_stale_peers()
    count_after = len(get_peers())
    new_peers = count_after - count_before
    return f"Discovery complete. Found {count_after} peer(s) total ({new_peers} new)."


def connect_peer(host, port=8000):
    hostname = socket.gethostname()
    local_ip = _get_local_ip()
    if host == local_ip and port == _local_port:
        logger.warning("Cannot connect to self")
        return False

    try:
        r = requests.get(
            f"http://{host}:{port}/api/p2p/handshake",
            timeout=5,
            headers={"User-Agent": "PixelAssistant/1.0"},
        )
        if r.status_code != 200:
            logger.warning("Handshake failed with %s:%d (status %d)", host, port, r.status_code)
            return False

        remote = r.json()
        peer_hostname = remote.get("hostname", host)
        with _lock:
            for p in _peers:
                if p["hostname"] == peer_hostname and p["ip"] == host and p["port"] == port:
                    p["connected"] = True
                    p["last_seen"] = datetime.now(timezone.utc).isoformat()
                    _save_peers()
                    return True

            entry = {
                "hostname": peer_hostname,
                "ip": host,
                "port": port,
                "version": remote.get("version", _VERSION),
                "device_count": remote.get("device_count", 0),
                "agent_count": remote.get("agent_count", 0),
                "uptime": remote.get("uptime_seconds", 0),
                "last_seen": datetime.now(timezone.utc).isoformat(),
                "connected": True,
            }
            _peers.append(entry)
            _save_peers()
        logger.info("Connected to peer %s:%d (%s)", host, port, peer_hostname)
        return True
    except requests.RequestException as e:
        logger.warning("Failed to connect to %s:%d: %s", host, port, e)
        return False


def disconnect_peer(host):
    with _lock:
        for p in _peers:
            if p["ip"] == host and p.get("connected", False):
                p["connected"] = False
                p["last_seen"] = datetime.now(timezone.utc).isoformat()
                _save_peers()
                logger.info("Disconnected from peer %s (%s)", host, p["hostname"])
                return True
    logger.warning("No connected peer found at %s", host)
    return False


def sync_devices(peer_host):
    with _lock:
        peer = None
        for p in _peers:
            if p["ip"] == peer_host or p["hostname"] == peer_host:
                if p.get("connected", False):
                    peer = p
                    break
    if peer is None:
        logger.warning("No connected peer found for %s", peer_host)
        return []

    try:
        r = requests.get(
            f"http://{peer['ip']}:{peer['port']}/api/devices",
            timeout=5,
            headers={"User-Agent": "PixelAssistant/1.0"},
        )
        if r.status_code != 200:
            logger.warning("Failed to fetch devices from %s", peer_host)
            return []
        remote_devices = r.json()
        if not isinstance(remote_devices, list):
            return []

        try:
            from skills.iot import device_register, device_list as _dl
            local = _dl()
            local_ids = set()
            if isinstance(local, list):
                local_ids = {d.get("id") for d in local if isinstance(d, dict)}
            elif isinstance(local, str):
                logger.info("Local devices (text): %s", local[:200])

            merged = []
            for d in remote_devices:
                did = d.get("id", "")
                if did and did not in local_ids:
                    dev_type = d.get("type", "unknown")
                    protocol = d.get("protocol", "http")
                    name = d.get("name", did)
                    device_register(did, name, dev_type, protocol)
                    merged.append(d)

            return merged
        except Exception as e:
            logger.warning("Device sync merge failed: %s", e)
            return remote_devices
    except requests.RequestException as e:
        logger.warning("Device sync request failed: %s", e)
        return []


_registered = False


def register_commands():
    global _registered
    if _registered:
        return
    _registered = True

    from skills import _COMMANDS, _ALIAS_MAP

    commands = [
        ("p2p", cmd_p2p, ["peers", "network"],
         "List discovered peers on the LAN"),
        ("p2p-connect", cmd_p2p_connect, ["peer-connect"],
         "Connect to a peer by host:port. Usage: /p2p-connect <host> [port]"),
        ("p2p-disconnect", cmd_p2p_disconnect, ["peer-disconnect"],
         "Disconnect from a peer. Usage: /p2p-disconnect <host>"),
        ("p2p-sync", cmd_p2p_sync, [],
         "Sync IoT devices with all connected peers"),
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


def cmd_p2p(args, assistant):
    peers = get_peers()
    if not peers:
        return "No peers discovered on the LAN. Use /p2p-connect <host> to connect manually."

    lines = [f"{'Hostname':<24} {'IP':<18} {'Port':<8} {'Devices':<10} {'Agents':<10} {'Uptime':<12} {'Status':<12} {'Last Seen':<22}"]
    lines.append("-" * 116)
    now = datetime.now(timezone.utc)
    for p in peers:
        hostname = p.get("hostname", "?")
        ip = p.get("ip", "?")
        port = p.get("port", 8000)
        dc = p.get("device_count", 0)
        ac = p.get("agent_count", 0)
        upt = _fmt_seconds(p.get("uptime", 0))
        status = "Connected" if p.get("connected", False) else "Discovered"
        last = ""
        try:
            ls = datetime.fromisoformat(p["last_seen"])
            diff = int((now - ls).total_seconds())
            last = f"{diff}s ago"
        except (ValueError, TypeError, KeyError):
            last = p.get("last_seen", "?")[:19]
        lines.append(f"{hostname:<24} {ip:<18} {port:<8} {dc:<10} {ac:<10} {upt:<12} {status:<12} {last:<22}")
    return "\n".join(lines)


def cmd_p2p_connect(args, assistant):
    parts = args.strip().split()
    if not parts:
        return "Usage: /p2p-connect <host> [port]\nExample: /p2p-connect 192.168.1.42 8000"
    host = parts[0]
    port = int(parts[1]) if len(parts) > 1 else 8000
    ok = connect_peer(host, port)
    return f"Connected to {host}:{port}." if ok else f"Failed to connect to {host}:{port}."


def cmd_p2p_disconnect(args, assistant):
    host = args.strip()
    if not host:
        return "Usage: /p2p-disconnect <host>"
    ok = disconnect_peer(host)
    return f"Disconnected from {host}." if ok else f"No connected peer found at {host}."


def cmd_p2p_sync(args, assistant):
    peers = get_peers()
    connected = [p for p in peers if p.get("connected", False)]
    if not connected:
        return "No connected peers. Use /p2p-connect to connect first."
    total = 0
    for p in connected:
        devices = sync_devices(p["hostname"])
        total += len(devices)
    return f"Synced {total} device(s) from {len(connected)} peer(s)."


def _fmt_seconds(secs):
    try:
        secs = int(secs)
    except (ValueError, TypeError):
        return "?"
    days, rem = divmod(secs, 86400)
    hours, rem = divmod(rem, 3600)
    mins, secs = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if mins:
        parts.append(f"{mins}m")
    parts.append(f"{secs}s")
    return " ".join(parts)


# Don't auto-start — call start_discovery() explicitly from app.py lifespan
