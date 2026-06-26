"""
Free image generation for Pixel Assistant.

Provider chain (all free):
  1. Pollinations.ai  — zero setup, no API key, instant results
  2. Hugging Face API — free tier with HF_TOKEN (FLUX.1-schnell / SD XL)

Get a free HF token at: https://huggingface.co/settings/tokens
Add it to .env as: HF_TOKEN=hf_...
"""
import os
import time
import urllib.parse
from pathlib import Path

import requests

OUTPUT_DIR = Path(__file__).parent.parent.parent / "generated"
_HEADERS = {"User-Agent": "Mozilla/5.0"}


def generate_image(prompt: str, width: int = 1024, height: int = 1024) -> Path:
    """Generate an image. Returns the saved file path."""
    OUTPUT_DIR.mkdir(exist_ok=True)

    # ── 1. Pollinations.ai (no key required) ─────────────────────────────
    try:
        return _pollinations(prompt, width, height)
    except Exception as e:
        pass

    # ── 2. Hugging Face Inference API (free with token) ───────────────────
    hf_token = os.getenv("HF_TOKEN", "").strip()
    if hf_token:
        try:
            return _hf_image(prompt, hf_token)
        except Exception as e:
            raise RuntimeError(f"All image providers failed. Last error: {e}")

    raise RuntimeError(
        "Image generation failed.\n"
        "Add a free HF_TOKEN to .env from https://huggingface.co/settings/tokens"
    )


def _pollinations(prompt: str, width: int, height: int) -> Path:
    seed = int(time.time())
    encoded = urllib.parse.quote(prompt)
    url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width={width}&height={height}&nologo=true&seed={seed}&enhance=true"
    )
    resp = requests.get(url, headers=_HEADERS, timeout=120)
    resp.raise_for_status()
    # Verify we actually got image bytes, not an HTML error page
    if b"<!DOCTYPE" in resp.content[:100]:
        raise RuntimeError("Pollinations returned HTML, not an image.")
    out = OUTPUT_DIR / f"image_{seed}.png"
    out.write_bytes(resp.content)
    return out


def _hf_image(prompt: str, token: str) -> Path:
    """Use FLUX.1-schnell via HF Inference API (fast + high quality)."""
    url = "https://api-inference.huggingface.co/models/black-forest-labs/FLUX.1-schnell"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    for attempt in range(4):
        resp = requests.post(url, headers=headers, json={"inputs": prompt}, timeout=90)
        if resp.status_code == 200:
            out = OUTPUT_DIR / f"image_{int(time.time())}.png"
            out.write_bytes(resp.content)
            return out
        if resp.status_code == 503:
            # Model is loading — wait and retry
            try:
                wait = resp.json().get("estimated_time", 20)
            except Exception:
                wait = 20
            time.sleep(min(float(wait), 30))
        else:
            raise RuntimeError(f"HF API {resp.status_code}: {resp.text[:200]}")

    raise RuntimeError("HF image model timed out while loading.")
