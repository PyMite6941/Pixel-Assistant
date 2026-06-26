"""
Weather skill for Pixel Assistant.
Uses wttr.in (free, no API key required).
"""
import urllib.parse
import requests

_HEADERS = {"User-Agent": "curl/7.0"}


def get_weather(city: str = "auto") -> str:
    """Fetch current weather for a city. Returns a one-line string."""
    try:
        r = requests.get(
            f"https://wttr.in/{urllib.parse.quote(city)}?format=3",
            headers=_HEADERS,
            timeout=(4, 10),
        )
        return r.text.strip()
    except requests.RequestException as e:
        return f"Weather unavailable: {e}"
