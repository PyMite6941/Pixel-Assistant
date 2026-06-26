"""
Network tools for Pixel Assistant.
Public IP lookup and ping functionality.
"""
import subprocess
import sys

import requests


def get_public_ip() -> str:
    """Return the public IP address of this machine."""
    try:
        r = requests.get("https://api.ipify.org?format=json", timeout=10)
        data = r.json()
        return f"Your public IP: {data.get('ip', 'unknown')}"
    except requests.RequestException as e:
        return f"Could not determine IP: {e}"


def ping_host(host: str, count: int = 4) -> str:
    """Ping a host and return the output. Cross-platform."""
    if not host:
        return "No host specified."
    param = "-n" if sys.platform == "win32" else "-c"
    try:
        result = subprocess.run(
            ["ping", param, str(count), host],
            capture_output=True, text=True, timeout=15,
        )
        out = result.stdout.strip() or result.stderr.strip()
        return out[:500]
    except subprocess.TimeoutExpired:
        return "Ping timed out after 15 seconds."
    except (OSError, subprocess.SubprocessError) as e:
        return f"Ping error: {e}"
