"""
Pixel Assistant — Security module.

Provides:
  - Port auditing  (netstat + tasklist, risk scoring)
  - Firewall fix   (netsh advfirewall — requires admin for write operations)
  - Encryption     (AES-256/Fernet, XOR, Caesar, Vigenere — text and files)
"""

from __future__ import annotations

import base64
import hashlib
import os
import re
import subprocess
from pathlib import Path


# ── Port risk database ────────────────────────────────────────────────────────

_RISKY_PORTS: dict[int, tuple[str, str, str]] = {
    21:    ("FTP",          "high",   "Cleartext credentials. Block unless actively hosting FTP."),
    23:    ("Telnet",       "high",   "Cleartext protocol. Should never be open."),
    69:    ("TFTP",         "high",   "No authentication. Block immediately."),
    111:   ("RPCBind",      "medium", "Remote procedure call mapper — common scan target."),
    135:   ("MS-RPC",       "medium", "Windows RPC endpoint mapper. Common lateral-movement target."),
    137:   ("NetBIOS-NS",   "medium", "Legacy NetBIOS name service. Safe to block on non-corporate nets."),
    138:   ("NetBIOS-DG",   "medium", "Legacy NetBIOS datagram. Safe to block on non-corporate nets."),
    139:   ("NetBIOS-SS",   "medium", "SMB over NetBIOS. Block if not on a corporate LAN."),
    445:   ("SMB",          "high",   "EternalBlue / WannaCry attack surface. Block inbound if not needed."),
    1433:  ("MSSQL",        "high",   "SQL Server. Should never face the internet."),
    1521:  ("Oracle-DB",    "high",   "Oracle DB. Should never face the internet."),
    3306:  ("MySQL",        "high",   "MySQL. Should never be publicly accessible."),
    3389:  ("RDP",          "high",   "Remote Desktop — high-value attack target. Block unless actively using."),
    4444:  ("Meterpreter",  "high",   "Common reverse-shell port. Block immediately."),
    5432:  ("PostgreSQL",   "high",   "PostgreSQL. Should never face the internet."),
    5900:  ("VNC",          "high",   "VNC remote desktop — often no auth. Block unless needed."),
    5985:  ("WinRM-HTTP",   "medium", "Windows Remote Management. Block if not using remote PowerShell."),
    5986:  ("WinRM-HTTPS",  "medium", "Windows Remote Management over TLS."),
    6379:  ("Redis",        "high",   "Redis has no auth by default. Block immediately."),
    8080:  ("HTTP-alt",     "medium", "Common dev/proxy port. Confirm this is intentional."),
    27017: ("MongoDB",      "high",   "MongoDB. Should never be publicly accessible."),
}

_SYSTEM_SAFE = {
    "svchost.exe", "system", "wininit.exe", "winlogon.exe", "lsass.exe",
    "services.exe", "smss.exe", "csrss.exe", "explorer.exe",
    "dns.exe", "spoolsv.exe", "wlanext.exe",
}


# ── Port audit ────────────────────────────────────────────────────────────────

def audit_ports() -> dict:
    """
    Scan all LISTENING ports on this machine via netstat.
    Returns:
      {
        "ports":  list of port-info dicts,
        "risks":  subset with risk in (high, medium),
        "clean":  count of low/info ports,
        "error":  present only on failure,
      }
    """
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, text=True, timeout=20,
        )
    except Exception as e:
        return {"error": str(e), "ports": [], "risks": [], "clean": 0}

    _pid_cache: dict[str, str] = {}

    def _proc(pid: str) -> str:
        if pid in _pid_cache:
            return _pid_cache[pid]
        try:
            r = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, timeout=5,
            )
            m = re.search(r'"([^"]+\.exe)"', r.stdout, re.IGNORECASE)
            name = m.group(1).lower() if m else "unknown"
        except Exception:
            name = "unknown"
        _pid_cache[pid] = name
        return name

    seen: set[tuple[str, int]] = set()
    ports: list[dict] = []

    for line in result.stdout.splitlines():
        m = re.match(
            r"\s*(TCP|UDP)\s+[\d.:*]+:(\d+)\s+[\d.:*]+\s*(LISTENING|ESTABLISHED|[A-Z_]*)?\s*(\d+)",
            line, re.IGNORECASE,
        )
        if not m:
            continue

        proto = m.group(1).upper()
        port  = int(m.group(2))
        state = (m.group(3) or "").upper()
        pid   = m.group(4)

        if proto == "TCP" and state not in ("LISTENING", ""):
            continue
        if (proto, port) in seen:
            continue
        seen.add((proto, port))

        process = _proc(pid)
        known   = _RISKY_PORTS.get(port)

        if known:
            service, risk, message = known
        else:
            service = None
            if process in _SYSTEM_SAFE:
                risk, message = "info", f"System service ({process})"
            elif process == "unknown":
                risk, message = "unknown", "Process could not be identified"
            else:
                risk, message = "info", f"Open by {process}"

        ports.append({
            "port": port, "proto": proto, "state": state or "LISTENING",
            "pid": pid, "process": process,
            "service": service, "risk": risk, "message": message,
        })

    risks = [p for p in ports if p["risk"] in ("high", "medium", "unknown")]
    clean = len(ports) - len(risks)
    return {"ports": ports, "risks": risks, "clean": clean}


def format_audit_report(audit: dict) -> str:
    """Turn an audit() result into a human-readable report string."""
    if "error" in audit and not audit.get("ports"):
        return f"Audit failed: {audit['error']}"

    _ICONS = {"high": "[red]HIGH  [/red]", "medium": "[yellow]MED   [/yellow]",
               "unknown": "[magenta]???   [/magenta]",
               "low": "[green]LOW   [/green]", "info": "[dim]INFO  [/dim]"}

    lines = [f"[bold]Open ports: {len(audit['ports'])}  |  Risks: {len(audit['risks'])}[/bold]\n"]

    # Sort: high → medium → unknown → info
    order = {"high": 0, "medium": 1, "unknown": 2, "low": 3, "info": 4}
    sorted_ports = sorted(audit["ports"], key=lambda p: (order.get(p["risk"], 5), p["port"]))

    for p in sorted_ports:
        icon  = _ICONS.get(p["risk"], "      ")
        svc   = f"  ({p['service']})" if p["service"] else ""
        proc  = p["process"]
        lines.append(f"{icon} :{p['port']}/{p['proto']}{svc}  [{proc}]  — {p['message']}")

    if audit["risks"]:
        lines.append(f"\n[bold red]{len(audit['risks'])} issue(s) found.[/bold red] "
                     "Run [cyan]/security fix[/cyan] to apply firewall blocks.")
    else:
        lines.append("\n[green]No high/medium risks detected.[/green]")

    return "\n".join(lines)


# ── Firewall management ───────────────────────────────────────────────────────

def _firewall_rule_exists(port: int, proto: str) -> bool:
    rule_name = f"PixelSec_Block_{port}"
    try:
        r = subprocess.run(
            ["netsh", "advfirewall", "firewall", "show", "rule", f"name={rule_name}"],
            capture_output=True, text=True, timeout=5,
        )
        return "No rules match" not in r.stdout
    except Exception:
        return False


def _firewall_block(port: int, proto: str = "tcp") -> tuple[bool, str]:
    """Add an inbound block rule. Requires administrator privileges."""
    if _firewall_rule_exists(port, proto):
        return True, f"Rule already exists for port {port}"

    rule_name = f"PixelSec_Block_{port}"
    cmd = [
        "netsh", "advfirewall", "firewall", "add", "rule",
        f"name={rule_name}",
        "dir=in", "action=block",
        f"protocol={proto.lower()}",
        f"localport={port}",
        "enable=yes",
        "profile=any",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            return True, f"Blocked inbound {proto.upper()}:{port}"
        err = r.stderr.strip() or r.stdout.strip()
        if "access" in err.lower() or r.returncode == 1:
            return False, "Access denied — re-run as Administrator"
        return False, f"netsh error (code {r.returncode}): {err}"
    except Exception as e:
        return False, str(e)


def fix_security(audit: dict) -> list[str]:
    """Block all high/medium/unknown risk ports. Returns one result line per port."""
    results = []
    if not audit.get("risks"):
        return ["No risks to fix."]
    for entry in audit["risks"]:
        ok, msg = _firewall_block(entry["port"], entry["proto"])
        flag = "[green]✓[/green]" if ok else "[red]✗[/red]"
        results.append(f"{flag} Port {entry['port']}/{entry['proto']} — {msg}")
    return results


def fix_port(port: int, proto: str = "tcp") -> str:
    ok, msg = _firewall_block(port, proto)
    return ("[green]✓[/green] " if ok else "[red]✗[/red] ") + msg


# ── Encryption ────────────────────────────────────────────────────────────────

def _fernet_key_from_password(password: str, salt: bytes) -> bytes:
    """Derive a URL-safe 32-byte Fernet key from a password + salt."""
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100_000)
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))


def encrypt_aes(text: str, password: str) -> str:
    """AES-256 via Fernet (AES-128-CBC + HMAC-SHA256). Falls back to XOR if cryptography not installed."""
    try:
        from cryptography.fernet import Fernet
        salt  = os.urandom(16)
        key   = _fernet_key_from_password(password, salt)
        token = Fernet(key).encrypt(text.encode())
        return base64.urlsafe_b64encode(salt + token).decode()
    except ImportError:
        return "[xor-fallback] " + _xor_encrypt(text, password)


def decrypt_aes(ciphertext: str, password: str) -> str:
    if ciphertext.startswith("[xor-fallback] "):
        return _xor_decrypt(ciphertext[15:], password)
    try:
        from cryptography.fernet import Fernet, InvalidToken
        raw   = base64.urlsafe_b64decode(ciphertext.encode())
        salt, token = raw[:16], raw[16:]
        key   = _fernet_key_from_password(password, salt)
        return Fernet(key).decrypt(token).decode()
    except ImportError:
        return "cryptography not installed — pip install cryptography"
    except Exception:
        return "Decryption failed — wrong password or corrupted data."


def _xor_encrypt(text: str, key: str) -> str:
    kb = key.encode()
    return base64.urlsafe_b64encode(
        bytes(b ^ kb[i % len(kb)] for i, b in enumerate(text.encode()))
    ).decode()


def _xor_decrypt(ciphertext: str, key: str) -> str:
    try:
        data = base64.urlsafe_b64decode(ciphertext.encode())
        kb = key.encode()
        return bytes(b ^ kb[i % len(kb)] for i, b in enumerate(data)).decode()
    except Exception:
        return "Decryption failed — wrong key or corrupted data."


def encrypt_xor(text: str, key: str) -> str:
    if not key:
        return "XOR requires a key."
    return _xor_encrypt(text, key)


def decrypt_xor(ciphertext: str, key: str) -> str:
    if not key:
        return "XOR requires a key."
    return _xor_decrypt(ciphertext, key)


def encrypt_caesar(text: str, shift: int = 13) -> str:
    out = []
    for c in text:
        if c.isalpha():
            base = ord("A") if c.isupper() else ord("a")
            out.append(chr((ord(c) - base + shift) % 26 + base))
        else:
            out.append(c)
    return "".join(out)


def decrypt_caesar(text: str, shift: int = 13) -> str:
    return encrypt_caesar(text, -shift % 26)


def encrypt_vigenere(text: str, key: str) -> str:
    if not key or not key.isalpha():
        return "Vigenere key must contain only letters."
    key = key.lower()
    out = []
    ki  = 0
    for c in text:
        if c.isalpha():
            shift = ord(key[ki % len(key)]) - ord("a")
            base  = ord("A") if c.isupper() else ord("a")
            out.append(chr((ord(c) - base + shift) % 26 + base))
            ki += 1
        else:
            out.append(c)
    return "".join(out)


def decrypt_vigenere(text: str, key: str) -> str:
    if not key or not key.isalpha():
        return "Vigenere key must contain only letters."
    key = key.lower()
    out = []
    ki  = 0
    for c in text:
        if c.isalpha():
            shift = ord(key[ki % len(key)]) - ord("a")
            base  = ord("A") if c.isupper() else ord("a")
            out.append(chr((ord(c) - base - shift) % 26 + base))
            ki += 1
        else:
            out.append(c)
    return "".join(out)


# ── File encryption ───────────────────────────────────────────────────────────

def encrypt_file(path: str, password: str) -> str:
    p = Path(path)
    if not p.exists():
        return f"File not found: {path}"
    data = p.read_bytes()
    try:
        from cryptography.fernet import Fernet
        salt  = os.urandom(16)
        key   = _fernet_key_from_password(password, salt)
        token = Fernet(key).encrypt(data)
        out   = p.with_name(p.name + ".enc")
        out.write_bytes(salt + token)
        return f"Encrypted  →  {out}  (original kept — delete it manually when ready)"
    except ImportError:
        kb  = password.encode()
        enc = bytes(b ^ kb[i % len(kb)] for i, b in enumerate(data))
        out = p.with_name(p.name + ".enc")
        out.write_bytes(enc)
        return f"XOR-encrypted  →  {out}  (install cryptography for AES-256)"


def decrypt_file(path: str, password: str) -> str:
    p = Path(path)
    if not p.exists():
        return f"File not found: {path}"
    data = p.read_bytes()
    try:
        from cryptography.fernet import Fernet, InvalidToken
        salt, token = data[:16], data[16:]
        key = _fernet_key_from_password(password, salt)
        plaintext = Fernet(key).decrypt(token)
        out_name = p.name[:-4] if p.name.endswith(".enc") else p.name + ".dec"
        out = p.parent / out_name
        out.write_bytes(plaintext)
        return f"Decrypted  →  {out}"
    except ImportError:
        kb  = password.encode()
        dec = bytes(b ^ kb[i % len(kb)] for i, b in enumerate(data))
        out_name = p.name[:-4] if p.name.endswith(".enc") else p.name + ".dec"
        out = p.parent / out_name
        out.write_bytes(dec)
        return f"XOR-decrypted  →  {out}"
    except Exception:
        return "Decryption failed — wrong password or corrupted file."


def hash_text(text: str, algorithm: str = "sha256") -> str:
    algo = algorithm.lower().replace("-", "")
    try:
        h = hashlib.new(algo, text.encode())
        return f"{algorithm.upper()}: {h.hexdigest()}"
    except ValueError:
        supported = "md5  sha1  sha224  sha256  sha384  sha512  blake2b  blake2s"
        return f"Unknown algorithm '{algorithm}'. Supported: {supported}"


# ── Steganography ─────────────────────────────────────────────────────────────

def stego_hide(image_path: str, message: str, password: str = "", output_path: str = "") -> str:
    """
    Hide a message in an image using LSB steganography.
    Stores a 4-byte length header followed by the message payload in the
    least-significant bit of each R, G, B channel.  If a password is given
    the message is AES-256 encrypted before embedding.
    """
    try:
        from PIL import Image
    except ImportError:
        return "Pillow not installed. Run: pip install Pillow"

    p = Path(image_path)
    if not p.exists():
        return f"Image not found: {image_path}"

    payload: bytes = (
        encrypt_aes(message, password).encode()
        if password
        else message.encode("utf-8")
    )

    # 4-byte big-endian length prefix so the extractor knows where to stop
    data = len(payload).to_bytes(4, "big") + payload

    img = Image.open(p).convert("RGB")
    pixels = list(img.getdata())

    max_bytes = (len(pixels) * 3) // 8
    if len(data) > max_bytes:
        return (
            f"Image too small for this message.\n"
            f"  Capacity : {max_bytes} bytes\n"
            f"  Required : {len(data)} bytes\n"
            f"Use a larger image."
        )

    # Expand data to a flat list of bits (MSB first)
    bits: list[int] = []
    for byte in data:
        for shift in range(7, -1, -1):
            bits.append((byte >> shift) & 1)

    new_pixels: list[tuple[int, int, int]] = []
    idx = 0
    for r, g, b in pixels:
        if idx < len(bits):
            r = (r & ~1) | bits[idx]; idx += 1
        if idx < len(bits):
            g = (g & ~1) | bits[idx]; idx += 1
        if idx < len(bits):
            b = (b & ~1) | bits[idx]; idx += 1
        new_pixels.append((r, g, b))

    out_path = Path(output_path) if output_path else p.with_name(p.stem + "_stego" + p.suffix)
    new_img = Image.new("RGB", img.size)
    new_img.putdata(new_pixels)
    new_img.save(str(out_path))

    enc_note = "  [AES-256 encrypted]" if password else ""
    return f"Message hidden in {out_path.name}  ({len(payload)} bytes{enc_note})"


def stego_reveal(image_path: str, password: str = "") -> str:
    """Extract a message hidden by stego_hide."""
    try:
        from PIL import Image
    except ImportError:
        return "Pillow not installed. Run: pip install Pillow"

    p = Path(image_path)
    if not p.exists():
        return f"Image not found: {image_path}"

    img = Image.open(p).convert("RGB")
    pixels = list(img.getdata())

    # Collect all LSBs: R, G, B of every pixel
    bits: list[int] = []
    for r, g, b in pixels:
        bits += [r & 1, g & 1, b & 1]

    def _to_bytes(bit_list: list[int]) -> bytes:
        out = bytearray()
        for i in range(0, len(bit_list) - 7, 8):
            byte = 0
            for j in range(8):
                byte = (byte << 1) | bit_list[i + j]
            out.append(byte)
        return bytes(out)

    if len(bits) < 32:
        return "Image too small to contain a hidden message."

    msg_len = int.from_bytes(_to_bytes(bits[:32]), "big")

    if msg_len == 0 or (32 + msg_len * 8) > len(bits):
        return "No hidden message detected (length header invalid or zero)."

    payload_bytes = _to_bytes(bits[32: 32 + msg_len * 8])

    if password:
        try:
            return decrypt_aes(payload_bytes.decode("utf-8"), password)
        except Exception:
            return "Decryption failed — wrong password or message was not encrypted."

    try:
        return payload_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return (
            "Message extracted but could not be decoded as text — "
            "it may be encrypted.\n"
            "Try: /stego reveal <path> <password>"
        )


def stego_capacity(image_path: str) -> str:
    """Report how many bytes can be hidden in an image."""
    try:
        from PIL import Image
    except ImportError:
        return "Pillow not installed. Run: pip install Pillow"
    p = Path(image_path)
    if not p.exists():
        return f"Image not found: {image_path}"
    img = Image.open(p).convert("RGB")
    w, h = img.size
    capacity = (w * h * 3) // 8 - 4  # subtract 4-byte header
    return f"{p.name}  ({w}×{h})  →  max {capacity} bytes hideable"
