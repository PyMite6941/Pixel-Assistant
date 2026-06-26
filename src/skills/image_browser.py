"""
Local AI image browser and manager for Pixel Assistant.
Browse, search, view metadata, and use generated images as AI sources.
"""
import json
import time
from datetime import datetime
from pathlib import Path

from skills import command

GENERATED_DIR = Path(__file__).parent.parent.parent / "generated"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}


def _get_images() -> list[Path]:
    if not GENERATED_DIR.exists():
        return []
    images = []
    for ext in IMAGE_EXTS:
        images.extend(GENERATED_DIR.glob(f"*{ext}"))
    images.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return images


def _format_size(bytes: int) -> str:
    if bytes < 1024:
        return f"{bytes}B"
    elif bytes < 1024 * 1024:
        return f"{bytes / 1024:.1f}KB"
    return f"{bytes / (1024 * 1024):.1f}MB"


@command(name="images", aliases=["gallery", "imgls"],
         help_text="Browse local AI images: /images [search] [--all]")
def cmd_images(args: str, assistant) -> str:
    parts = args.strip().split()
    show_all = "--all" in parts
    query = " ".join(p for p in parts if not p.startswith("--"))

    images = _get_images()
    if not images:
        return "No AI-generated images found in generated/ directory."

    if query:
        images = [p for p in images if query.lower() in p.stem.lower()]

    if not images:
        return f"No images matching '{query}'."

    limit = len(images) if show_all else 20
    images = images[:limit]

    total = len(_get_images())
    lines = [
        f"── Local AI Images ───────────────────────",
        f"  Total: {total} image(s)  |  Showing: {len(images)}",
        f"",
    ]
    for i, img in enumerate(images, 1):
        mtime = datetime.fromtimestamp(img.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        size = _format_size(img.stat().st_size)
        lines.append(f"  {i:>3}. {img.name:45s} {size:>8}  {mtime}")

    lines.extend([
        "",
        "Commands:",
        "  /images <keyword>     — filter by keyword",
        "  /images --all         — show all images",
        "  /imagesource <n>      — use image as AI source/context",
        "  /imagine <prompt>     — generate a new AI image",
        "────────────────────────────────────────────",
    ])
    return "\n".join(lines)


@command(name="imagesource", aliases=["imgsrc", "imgcontext"],
         help_text="Use a local image as an AI source: /imagesource <number|filename>")
def cmd_imagesource(args: str, assistant) -> str:
    if not args.strip():
        images = _get_images()
        if not images:
            return "No images available. Use /images to list them."
        lines = ["Select an image to use as source:\n"]
        for i, img in enumerate(images[:20], 1):
            lines.append(f"  {i}. {img.name}")
        lines.append("\nUsage: /imagesource <number> or /imagesource <filename>")
        return "\n".join(lines)

    images = _get_images()
    if not images:
        return "No images found in generated/."

    target = None
    # Try by number
    if args.strip().isdigit():
        idx = int(args.strip()) - 1
        if 0 <= idx < len(images):
            target = images[idx]
    # Try by filename
    if target is None:
        matches = [p for p in images if args.strip().lower() in p.name.lower()]
        if matches:
            target = matches[0]

    if target is None:
        return f"No image found matching '{args}'."

    # Build a source context string describing the image
    mtime = datetime.fromtimestamp(target.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    size = _format_size(target.stat().st_size)
    info = (
        f"[Local Image Source: {target.name}]\n"
        f"  Path: {target}\n"
        f"  Size: {size}\n"
        f"  Created: {mtime}\n"
        f"  Description: AI-generated image from '{target.stem}'"
    )

    # Store in assistant context if possible
    try:
        context_file = Path(assistant.__class__.__module__ if hasattr(assistant, '__class__') else "")
        # Add to conversation history as a system note
        if hasattr(assistant, "history") and isinstance(assistant.history, list):
            assistant.history.append({
                "role": "system",
                "content": f"[Image source loaded: {target.name} at {target}]",
            })
    except Exception:
        pass

    return (
        f"── Image Source Loaded ─────────────────────\n"
        f"{info}\n"
        f"  The image is now available in context as a source.\n"
        f"  Agents can reference it with [READ: {target.relative_to(Path.cwd())}]\n"
        f"────────────────────────────────────────────\n"
        f"Ask me questions about this image, or use it as inspiration for new generations."
    )


@command(name="imagine", aliases=["genimg", "draw"],
         help_text="Generate an AI image: /imagine <description> [--size WxH]")
def cmd_imagine(args: str, assistant) -> str:
    parts = args.strip().split("--size")
    prompt = parts[0].strip()
    size_str = parts[1].strip() if len(parts) > 1 else ""

    if not prompt:
        return "Usage: /imagine <description> [--size 1024x1024]\nExample: /imagine a cute cat wearing a spacesuit"

    width, height = 1024, 1024
    if size_str and "x" in size_str:
        try:
            w, h = size_str.lower().split("x")
            width = int(w.strip())
            height = int(h.strip())
        except (ValueError, IndexError):
            pass

    try:
        from skills.image_gen import generate_image
        result_path = generate_image(prompt, width, height)
        rel = result_path.relative_to(GENERATED_DIR.parent) if GENERATED_DIR.parent in result_path.parents else result_path
        return (
            f"── Image Generated ───────────────────────\n"
            f"  Prompt: {prompt[:80]}\n"
            f"  Size:   {width}x{height}\n"
            f"  File:   {result_path.name} ({_format_size(result_path.stat().st_size)})\n"
            f"  Path:   {rel}\n"
            f"──────────────────────────────────────────\n"
            f"Use /imagesource {result_path.stem} to use this as AI context."
        )
    except Exception as e:
        return f"Image generation failed: {e}"
