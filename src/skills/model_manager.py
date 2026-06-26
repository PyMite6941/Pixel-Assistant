"""
Model manager for Pixel Assistant.
Query multiple providers for available models, usage limits, and reset times.
Switch providers interactively.
"""
import os
import time
from datetime import datetime
from pathlib import Path

import requests

from skills import command

SRC_DIR = Path(__file__).parent.parent


def _get_config():
    """Load current config values."""
    from core_files.config import Config
    return Config()


def _check_groq_limits() -> dict:
    """Check Groq API rate limits via a lightweight models list call."""
    cfg = _get_config()
    key = cfg.GROQ_KEY or os.getenv("GROQ_KEY", "")
    if not key:
        return {"status": "no_key", "models": [], "limits": {}}

    try:
        headers = {"Authorization": f"Bearer {key}"}
        resp = requests.get(
            "https://api.groq.com/openai/v1/models",
            headers=headers,
            timeout=10,
        )
        limits = {}
        for h in resp.headers:
            hl = h.lower()
            if hl.startswith("x-ratelimit"):
                limits[hl] = resp.headers[h]

        models = []
        if resp.ok:
            data = resp.json()
            models = sorted(
                m["id"] for m in data.get("data", [])
                if not m["id"].endswith("-preview")
            )

        return {
            "status": "ok" if resp.ok else f"http_{resp.status_code}",
            "models": models,
            "limits": limits,
            "remaining_requests": limits.get("x-ratelimit-remaining-requests", "?"),
            "remaining_tokens": limits.get("x-ratelimit-remaining-tokens", "?"),
            "reset_requests": limits.get("x-ratelimit-reset-requests", "?"),
            "reset_tokens": limits.get("x-ratelimit-reset-tokens", "?"),
        }
    except requests.RequestException as e:
        return {"status": f"error: {e}", "models": [], "limits": {}}


def _check_gemini_limits() -> dict:
    """Check Gemini API usage by listing models."""
    cfg = _get_config()
    key = cfg.GEMINI_KEY or os.getenv("GEMINI_KEY", "")
    if not key:
        return {"status": "no_key", "models": [], "limits": {}}

    try:
        headers = {"Content-Type": "application/json"}
        resp = requests.get(
            f"https://generativelanguage.googleapis.com/v1beta/models?key={key}",
            headers=headers,
            timeout=10,
        )
        models = []
        quota = {}
        if resp.ok:
            data = resp.json()
            for m in data.get("models", []):
                name = m.get("name", "").replace("models/", "")
                if "gemini" in name:
                    models.append(name)
                    supported = m.get("supportedGenerationMethods", [])
                    quota[name] = supported

        return {
            "status": "ok" if resp.ok else f"http_{resp.status_code}",
            "models": sorted(models),
            "limits": quota,
            "remaining_requests": "See Google AI Studio quota page",
            "remaining_tokens": "See Google AI Studio quota page",
            "reset_requests": "Monthly reset",
            "reset_tokens": "Monthly reset",
        }
    except requests.RequestException as e:
        return {"status": f"error: {e}", "models": [], "limits": {}}


def _check_mistral_limits() -> dict:
    """Check Mistral API status."""
    cfg = _get_config()
    key = cfg.MISTRAL_KEY or os.getenv("MISTRAL_KEY", "")
    if not key:
        return {"status": "no_key", "models": [], "limits": {}}

    try:
        headers = {"Authorization": f"Bearer {key}"}
        resp = requests.get(
            "https://api.mistral.ai/v1/models",
            headers=headers,
            timeout=10,
        )
        models = []
        if resp.ok:
            data = resp.json()
            models = sorted(m["id"] for m in data.get("data", []))

        return {
            "status": "ok" if resp.ok else f"http_{resp.status_code}",
            "models": models,
            "limits": dict(resp.headers) if resp.headers else {},
            "remaining_requests": resp.headers.get("x-ratelimit-remaining", "N/A (see Mistral dashboard)"),
            "remaining_tokens": resp.headers.get("x-ratelimit-remaining-tokens", "N/A"),
            "reset_requests": resp.headers.get("x-ratelimit-reset", "N/A"),
            "reset_tokens": "N/A",
        }
    except requests.RequestException as e:
        return {"status": f"error: {e}", "models": [], "limits": {}}


def _check_openai_limits() -> dict:
    """Check OpenAI-compatible endpoint limits."""
    cfg = _get_config()
    base = os.getenv("OPENAI_BASE_URL", cfg.get("openai_base", "")) or ""
    key = os.getenv("OPENAI_KEY", cfg.get("openai_key", "")) or ""
    if not key or not base:
        return {"status": "not_configured", "models": [], "limits": {}}

    try:
        headers = {"Authorization": f"Bearer {key}"}
        resp = requests.get(
            f"{base.rstrip('/')}/models",
            headers=headers,
            timeout=10,
        )
        models = []
        if resp.ok:
            data = resp.json()
            models = sorted(m["id"] for m in data.get("data", []))

        return {
            "status": "ok" if resp.ok else f"http_{resp.status_code}",
            "models": models[:10],
            "limits": {},
            "remaining_requests": "See provider dashboard",
            "remaining_tokens": "See provider dashboard",
            "reset_requests": "Varies",
            "reset_tokens": "Varies",
        }
    except requests.RequestException as e:
        return {"status": f"error: {e}", "models": [], "limits": {}}


def _check_ollama_limits() -> dict:
    """Check local Ollama instance."""
    cfg = _get_config()
    url = os.getenv("OLLAMA_URL", cfg.get("ollama_url", "http://localhost:11434"))
    try:
        resp = requests.get(f"{url.rstrip('/')}/api/tags", timeout=5)
        models = []
        if resp.ok:
            data = resp.json()
            models = sorted(m["name"] for m in data.get("models", []))

        return {
            "status": "ok" if resp.ok else f"http_{resp.status_code}",
            "models": models,
            "limits": {},
            "remaining_requests": "Local — no limit",
            "remaining_tokens": "Local — no limit",
            "reset_requests": "N/A",
            "reset_tokens": "N/A",
        }
    except (requests.RequestException, OSError):
        return {"status": "offline", "models": [], "limits": {}}


def _format_limits(info: dict) -> str:
    """Format limit info into readable string."""
    rem_req = info.get("remaining_requests", "?")
    rem_tok = info.get("remaining_tokens", "?")
    reset_req = info.get("reset_requests", "?")
    reset_tok = info.get("reset_tokens", "?")
    return (
        f"  Requests remaining : {rem_req}\n"
        f"  Tokens remaining   : {rem_tok}\n"
        f"  Requests reset in  : {reset_req}\n"
        f"  Tokens reset in    : {reset_tok}"
    )


@command(name="model", aliases=["models", "provider", "api"],
         help_text="Show all providers, models, usage limits and reset times. /model switch <name> to change.")
def cmd_model(args: str, assistant) -> str:
    parts = args.strip().lower().split()
    
    # Handle /model switch <provider>
    if parts and parts[0] == "switch" and len(parts) > 1:
        provider = parts[1]
        if provider not in ("groq", "gemini", "mistral", "openai", "ollama"):
            return f"Unknown provider: {provider}. Choose: groq, gemini, mistral, openai, ollama"
        assistant.provider = provider
        assistant.config.set("provider", provider)
        assistant._init_clients()
        return f"Switched to {provider}. Re-initialized clients."

    # Show limits (may take a few seconds)
    from core_files.ui import show_info
    if assistant.debug:
        show_info("Checking provider limits...")

    groq = _check_groq_limits()
    gemini = _check_gemini_limits()
    mistral = _check_mistral_limits()
    openai = _check_openai_limits()
    ollama = _check_ollama_limits()

    current = assistant.provider
    current_model = assistant.config.get("smart_model") if assistant.config.get("smart_mode") else assistant.config.model

    lines = [
        "═══ Provider Status ════════════════════════════════════",
        f"  Current : {current.upper()}  ({current_model})",
        f"  Smart   : {'ON' if assistant.config.get('smart_mode') else 'OFF'}",
        "",
    ]

    # ── Groq ──
    g_status = groq.get("status", "error")
    g_icon = "" if g_status == "ok" else ""
    lines.append(f"  {g_icon}[bold cyan]GROQ[/bold cyan]  ({g_status})")
    lines.append(_format_limits(groq))
    g_models = groq.get("models", [])
    if g_models:
        lines.append(f"  Models ({len(g_models)} available):")
        for m in g_models[:8]:
            marker = " [green]<-- active[/green]" if current == "groq" and m == current_model else ""
            lines.append(f"    - {m}{marker}")
        if len(g_models) > 8:
            lines.append(f"    ... and {len(g_models) - 8} more")
    lines.append("")

    # ── Gemini ──
    ge_status = gemini.get("status", "error")
    ge_icon = "" if ge_status == "ok" else ""
    lines.append(f"  {ge_icon}[bold yellow]GEMINI[/bold yellow]  ({ge_status})")
    lines.append(_format_limits(gemini))
    ge_models = gemini.get("models", [])
    if ge_models:
        lines.append(f"  Models ({len(ge_models)} available):")
        for m in ge_models[:5]:
            marker = " [green]<-- active[/green]" if current == "gemini" and m == current_model else ""
            lines.append(f"    - {m}{marker}")
    lines.append("")

    # ── Mistral ──
    m_status = mistral.get("status", "error")
    m_icon = "" if m_status == "ok" else ""
    lines.append(f"  {m_icon}[bold magenta]MISTRAL[/bold magenta]  ({m_status})")
    lines.append(_format_limits(mistral))
    m_models = mistral.get("models", [])
    if m_models:
        lines.append(f"  Models ({len(m_models)} available):")
        for m in m_models[:5]:
            marker = " [green]<-- active[/green]" if current == "mistral" and m == current_model else ""
            lines.append(f"    - {m}{marker}")
    lines.append("")

    # ── OpenAI-compatible ──
    o_status = openai.get("status", "not_configured")
    o_icon = "" if o_status == "ok" else ""
    lines.append(f"  {o_icon}[bold blue]OPENAI[/bold blue]  ({o_status})")
    lines.append(_format_limits(openai))
    o_models = openai.get("models", [])
    if o_models:
        for m in o_models[:3]:
            lines.append(f"    - {m}")
    lines.append("")

    # ── Ollama (local) ──
    ol_status = ollama.get("status", "offline")
    ol_icon = "" if ol_status == "ok" else ""
    lines.append(f"  {ol_icon}[bold green]OLLAMA[/bold green] (local)  ({ol_status})")
    lines.append(_format_limits(ollama))
    ol_models = ollama.get("models", [])
    if ol_models:
        for m in ol_models[:3]:
            lines.append(f"    - {m}")
    lines.append("")

    # ── Switch instructions ──
    lines.extend([
        "─── Switch Provider ───────────────────────────────────",
        "  /model switch groq        Switch to Groq",
        "  /model switch gemini      Switch to Gemini",
        "  /model switch mistral     Switch to Mistral",
        "  /model switch openai      Switch to OpenAI-compatible",
        "  /model switch ollama      Switch to local Ollama",
        "  /set model <name>         Switch model within current provider",
        "────────────────────────────────────────────────────────",
    ])

    return "\n".join(lines)
