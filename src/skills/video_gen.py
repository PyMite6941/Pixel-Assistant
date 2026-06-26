"""
Free video generation for Pixel Assistant.

Provider chain (all free):
  1. Hugging Face Inference API — free tier with HF_TOKEN
       Model: ali-vilab/text-to-video-ms-1.7b  (short clips, ~3-4 seconds)
  2. Pollinations.ai video endpoint — no key, experimental

Get a free HF token at: https://huggingface.co/settings/tokens
Add it to .env as: HF_TOKEN=hf_...

Note: free video generation is slow (30-120 seconds).
"""
import os
import time
from pathlib import Path

import requests

OUTPUT_DIR = Path(__file__).parent.parent.parent / "generated"

# HF models to try in order (fastest/most reliable first)
_HF_VIDEO_MODELS = [
    "ali-vilab/text-to-video-ms-1.7b",
    "damo-vilab/text-to-video-ms-1.7b",
]


def generate_video(prompt: str) -> Path:
    """Generate a short video clip. Returns the saved file path."""
    OUTPUT_DIR.mkdir(exist_ok=True)

    # ── 1. Pollinations.ai video (no key, experimental) ──────────────────
    try:
        return _pollinations_video(prompt)
    except Exception:
        pass

    # ── 2. Hugging Face Inference API ─────────────────────────────────────
    hf_token = os.getenv("HF_TOKEN", "").strip()
    if not hf_token:
        raise RuntimeError(
            "Video generation requires HF_TOKEN.\n"
            "Get a free token at https://huggingface.co/settings/tokens\n"
            "Then add it to .env: HF_TOKEN=hf_..."
        )

    last_err = None
    for model in _HF_VIDEO_MODELS:
        try:
            return _hf_video(prompt, hf_token, model)
        except Exception as e:
            last_err = e

    raise RuntimeError(f"All video providers failed. Last error: {last_err}")


def _pollinations_video(prompt: str) -> Path:
    import urllib.parse
    encoded = urllib.parse.quote(prompt)
    url = f"https://video.pollinations.ai/prompt/{encoded}"
    resp = requests.get(url, timeout=180)
    resp.raise_for_status()
    if b"<!DOCTYPE" in resp.content[:100] or len(resp.content) < 1000:
        raise RuntimeError("Pollinations video unavailable or returned HTML.")
    out = OUTPUT_DIR / f"video_{int(time.time())}.mp4"
    out.write_bytes(resp.content)
    return out


def _hf_video(prompt: str, token: str, model: str) -> Path:
    url = f"https://api-inference.huggingface.co/models/{model}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    for attempt in range(5):
        resp = requests.post(url, headers=headers, json={"inputs": prompt}, timeout=180)
        if resp.status_code == 200:
            out = OUTPUT_DIR / f"video_{int(time.time())}.mp4"
            out.write_bytes(resp.content)
            return out
        if resp.status_code == 503:
            try:
                wait = resp.json().get("estimated_time", 30)
            except Exception:
                wait = 30
            time.sleep(min(float(wait), 60))
        else:
            raise RuntimeError(f"HF API {resp.status_code}: {resp.text[:200]}")

    raise RuntimeError(f"Model {model} timed out while loading.")
