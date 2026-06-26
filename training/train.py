"""
Build and create the pixel-assistant Ollama model.

Usage:
  python train.py                    # generate examples + build model
  python train.py generate           # only regenerate pixel_training.jsonl
  python train.py build              # only build the Modelfile + run ollama create
  python train.py stats              # show training corpus stats

The model is named: pixel-assistant
Base model: qwen2.5-coder:3b (change BASE_MODEL to switch)
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

TRAINING_DIR = Path(__file__).parent
SRC_DIR      = TRAINING_DIR.parent / "src"
PERSONA_FILE = SRC_DIR / "functionalities" / "context.md"
EXAMPLES_FILE = TRAINING_DIR / "pixel_training.jsonl"
MODELFILE    = TRAINING_DIR / "Modelfile.pixel"
MODEL_NAME   = "pixel-assistant"
BASE_MODEL   = "qwen2.5-coder:3b"


# ── Step 1: Generate training examples ────────────────────────────────────────

def cmd_generate():
    import generate_training
    generate_training.write_jsonl()


# ── Step 2: Load persona ───────────────────────────────────────────────────────

def load_persona() -> str:
    if PERSONA_FILE.exists():
        return PERSONA_FILE.read_text(encoding="utf-8").strip()
    return "You are Pixel, a helpful AI assistant."


# ── Step 3: Build Modelfile ────────────────────────────────────────────────────

def build_modelfile() -> Path:
    persona  = load_persona()
    examples = load_examples()

    lines: list[str] = [
        f"FROM {BASE_MODEL}",
        "",
        'SYSTEM """',
        persona,
        '"""',
        "",
        "PARAMETER temperature 0.3",
        "PARAMETER top_p 0.9",
        "PARAMETER repeat_penalty 1.1",
        "",
    ]

    for ex in examples:
        msgs = ex.get("messages", [])
        for msg in msgs:
            role    = msg["role"]
            content = msg["content"].replace('"""', "'''")  # avoid triple-quote collision
            if role == "user":
                lines.append(f'MESSAGE user """{content}"""')
            elif role == "assistant":
                lines.append(f'MESSAGE assistant """{content}"""')
        lines.append("")

    content = "\n".join(lines)
    MODELFILE.write_text(content, encoding="utf-8")
    print(f"Wrote {MODELFILE.name}  ({MODELFILE.stat().st_size:,} bytes, {len(examples)} examples)")
    return MODELFILE


def load_examples() -> list[dict]:
    if not EXAMPLES_FILE.exists():
        print("pixel_training.jsonl not found — generating...")
        cmd_generate()
    examples = []
    with open(EXAMPLES_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                examples.append(json.loads(line))
    return examples


# ── Step 4: Run ollama create ──────────────────────────────────────────────────

def cmd_build():
    if not EXAMPLES_FILE.exists():
        cmd_generate()

    modelfile = build_modelfile()

    print(f"\nCreating Ollama model '{MODEL_NAME}' from {BASE_MODEL}...")
    result = subprocess.run(
        ["ollama", "create", MODEL_NAME, "-f", str(modelfile)],
        capture_output=False,
    )
    if result.returncode == 0:
        print(f"\nModel '{MODEL_NAME}' created successfully.")
        print(f"Test it with:  ollama run {MODEL_NAME}")
        print(f"Use in Pixel:  /set model {MODEL_NAME}  (or set OLLAMA_MODEL in config)")
    else:
        print(f"\nollama create failed (exit {result.returncode}).")
        print("Make sure Ollama is installed and running: https://ollama.com/download")


# ── Stats ──────────────────────────────────────────────────────────────────────

def cmd_stats():
    examples = load_examples()
    total_chars = sum(
        len(m["content"])
        for ex in examples
        for m in ex.get("messages", [])
    )
    user_turns = sum(
        1 for ex in examples
        for m in ex.get("messages", []) if m["role"] == "user"
    )
    persona_chars = len(load_persona())

    print(f"Training corpus:")
    print(f"  Examples        : {len(examples)}")
    print(f"  User turns      : {user_turns}")
    print(f"  Total chars     : {total_chars:,}")
    print(f"  Persona chars   : {persona_chars:,}")
    print(f"  JSONL file      : {EXAMPLES_FILE.name}")
    print(f"  Modelfile       : {MODELFILE.name if MODELFILE.exists() else '(not built yet)'}")
    print(f"  Target model    : {MODEL_NAME}")
    print(f"  Base model      : {BASE_MODEL}")


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"

    if cmd == "generate":
        cmd_generate()
    elif cmd == "build":
        cmd_build()
    elif cmd == "stats":
        cmd_stats()
    else:  # "all" or no arg
        cmd_generate()
        cmd_build()
        cmd_stats()
