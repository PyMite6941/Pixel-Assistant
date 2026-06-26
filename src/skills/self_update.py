"""
Pixel Assistant — Self-update engine (PixelCode-parity).

Modes:
  debug    — scan source files for real bugs; generate + apply surgical fixes
  upgrade  — pick unchecked feature from PLANNED.md; implement it
  full     — debug pass then upgrade pass (like PixelCode /update full)

Legacy commands (kept):
  check    — scan and report bugs only, no auto-fix
  feature  — generate + apply a new command
  fix      — generate + apply a targeted bug fix
  log      — show update changelog
  rollback — restore last backup of main.py
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

SRC_DIR    = Path(__file__).parent.parent
MAIN_PY    = SRC_DIR / "main.py"
BACKUP_DIR = SRC_DIR / "functionalities" / "backups"
CHANGELOG  = SRC_DIR / "functionalities" / "update_log.json"
PLANNED_MD = SRC_DIR / "functionalities" / "PLANNED.md"

# Files to scan in order (mirrors PixelCode OWN_FILES)
OWN_FILES = [
    "main.py",
    "security.py",
    "search.py",
    "skills/self_update.py",
    "skills/calendar_gcal.py",
    "skills/slides.py",
    "skills/pdf_gen.py",
    "skills/image_gen.py",
    "skills/video_gen.py",
    "skills/language.py",
    "core_files/config.py",
    "core_files/auth.py",
    "core_files/logger.py",
    "core_files/voice.py",
    "core_files/platform.py",
    "api/app.py",
]

_BUG_CRITERIA = """\
Real bugs only — not style, not refactoring. Specifically look for:
  • Unhandled exceptions at real I/O boundaries (file open, requests, subprocess)
  • Silent failures: except Exception: pass swallowing real errors
  • Logic errors: off-by-one, wrong conditionals, unreachable branches
  • f-string / format string type mismatches
  • Mutable default arguments: def f(x=[]) pattern
  • Missing encoding="utf-8" on open() calls that handle user text
  • Hardcoded paths or credentials that should come from config
  • Import errors that crash at runtime (missing try/except around optional deps)
  • Functions that return misleading values on failure instead of raising
  • Threading hazards: shared mutable state without locks
"""

_PLANNED_SEED = """\
# Pixel Assistant — Planned Features

## Unchecked (to implement)
- [ ] /news — top headlines from a free RSS/JSON news API
- [ ] /convert <value> <from> <to> — unit converter (length, weight, temp, currency)
- [ ] /qr <text> — generate a QR code image (requires qrcode package)
- [ ] /regex <pattern> <text> — test a regex and show matches + capture groups
- [ ] /ip — show public IP address and rough geolocation
- [ ] /ping <host> — ping a host and show round-trip latency
- [ ] /diff <file1> <file2> — show unified diff between two files
- [ ] /encode <fmt> <text> — base64 / hex / rot13 / url encode
- [ ] /decode <fmt> <text> — base64 / hex / rot13 / url decode
- [ ] /uuid — generate a random UUID v4
- [ ] /lorem [n] — generate n words of lorem ipsum placeholder text
- [ ] /flip [coin|N] — flip a coin or roll an N-sided die
- [ ] /ascii <text> — render text as large ASCII art

## Checked (implemented)
- [x] /calc — math calculator
- [x] /weather — current weather via wttr.in
- [x] /timer — countdown timer
- [x] /remind — reminder after a duration
- [x] /note — quick notes
- [x] /todo — persistent task list
- [x] /translate — language translation
- [x] /define — word definition
- [x] /summarize — summarize text or last reply
- [x] /wiki — Wikipedia summary
- [x] /code — AI code generation
- [x] /journal — daily journal entries
- [x] /pomodoro — Pomodoro timer
- [x] /teach — structured lessons + quiz
- [x] /security audit — open port scanner + risk scoring
- [x] /security fix — firewall block for risky ports
- [x] /encrypt — AES-256, XOR, Caesar, Vigenère, file encryption
- [x] /stego — LSB image steganography
- [x] /hash — text hashing (sha256, sha512, etc.)
"""


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _backup(path: Path = MAIN_PY) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest  = BACKUP_DIR / f"{path.stem}_{stamp}.py"
    shutil.copy2(path, dest)
    return dest


def _syntax_ok(code: str) -> tuple[bool, str]:
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w",
                                     encoding="utf-8", delete=False) as f:
        f.write(code)
        tmp = Path(f.name)
    try:
        r = subprocess.run(
            [sys.executable, "-m", "py_compile", str(tmp)],
            capture_output=True, text=True,
        )
        ok  = r.returncode == 0
        err = (r.stderr or "").replace(str(tmp), "<generated>")
        return ok, err
    finally:
        tmp.unlink(missing_ok=True)


def _parse_llm_blocks(text: str) -> dict[str, str]:
    pattern = re.compile(
        r"===(\w+)===\s*\n(.*?)(?====\w+===|===END===|\Z)", re.DOTALL
    )
    return {m.group(1).upper(): m.group(2).strip() for m in pattern.finditer(text)}


def _log_update(kind: str, description: str, status: str, backup: str = ""):
    CHANGELOG.parent.mkdir(exist_ok=True)
    log = []
    if CHANGELOG.exists():
        try:
            log = json.loads(CHANGELOG.read_text(encoding="utf-8"))
        except Exception:
            pass
    log.append({
        "date":        datetime.now().strftime("%Y-%m-%d %H:%M"),
        "kind":        kind,
        "description": description,
        "status":      status,
        "backup":      backup,
    })
    CHANGELOG.write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")


def _read_route_section() -> str:
    src   = MAIN_PY.read_text(encoding="utf-8")
    start = src.find("def _check_meta(")
    end   = src.find("\n    def ", start + 1)
    return src[start:end].strip() if start != -1 else src[:3000]


def _read_method_signatures() -> str:
    src   = MAIN_PY.read_text(encoding="utf-8")
    lines = [l.rstrip() for l in src.splitlines() if re.match(r"    def ", l)]
    return "\n".join(lines)


def _file_list() -> str:
    lines = []
    for rel in OWN_FILES:
        p = SRC_DIR / rel
        if p.exists():
            lines.append(f"  {rel}  ({p.stat().st_size:,} bytes)")
        else:
            lines.append(f"  {rel}  [MISSING]")
    return "\n".join(lines)


def _ensure_planned_md():
    if not PLANNED_MD.exists():
        PLANNED_MD.parent.mkdir(exist_ok=True)
        PLANNED_MD.write_text(_PLANNED_SEED, encoding="utf-8")


def _mark_planned_done(feature_text: str):
    """Mark a planned feature line as [x] in PLANNED.md."""
    if not PLANNED_MD.exists():
        return
    text = PLANNED_MD.read_text(encoding="utf-8")
    # Find the line containing the feature description and mark it done
    lines = text.splitlines()
    new_lines = []
    for line in lines:
        if line.startswith("- [ ]") and feature_text.lower()[:30] in line.lower():
            new_lines.append(line.replace("- [ ]", "- [x]", 1))
        else:
            new_lines.append(line)
    PLANNED_MD.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


# ── Debug mode ─────────────────────────────────────────────────────────────────

def run_debug_pass(llm_fn, confirm_fn) -> str:
    """
    Phase 1: Scan each file for real bugs (mirrors PixelCode build_debug_goal).
    Phase 2: Generate surgical ===OLD=== / ===NEW=== patches for each bug.
    Phase 3: Apply confirmed patches, verify syntax, log results.
    """
    files_scanned = 0
    all_issues: list[dict] = []  # {file, rel, bug_desc, old_str, new_str}

    print("Scanning source files for bugs...")

    for rel in OWN_FILES:
        p = SRC_DIR / rel
        if not p.exists():
            continue
        files_scanned += 1
        content = p.read_text(encoding="utf-8", errors="replace")

        scan_prompt = (
            f"You are auditing a Python source file for real bugs.\n\n"
            f"Bug criteria:\n{_BUG_CRITERIA}\n"
            f"File: {rel}\n"
            f"```python\n{content}\n```\n\n"
            f"For each real bug found, reply in this EXACT format:\n\n"
            f"===BUG===\n"
            f"Line: <approximate line number or range>\n"
            f"Issue: <one sentence — what is wrong and why it matters>\n"
            f"===OLD===\n"
            f"<exact code block to replace — must be unique in the file, include enough context>\n"
            f"===NEW===\n"
            f"<corrected replacement — same indentation>\n"
            f"===END===\n\n"
            f"Multiple bugs: repeat the ===BUG=== ... ===END=== block for each.\n"
            f"If there are NO real bugs, reply exactly: NO ISSUES\n"
            f"Do NOT report style issues, missing features, or optional improvements."
        )

        result = llm_fn([{"role": "user", "content": scan_prompt}])

        if result.strip().upper().startswith("NO ISSUES"):
            continue

        # Parse all BUG blocks
        bug_pat = re.compile(
            r"===BUG===\s*\n(.*?)===OLD===\s*\n(.*?)===NEW===\s*\n(.*?)===END===",
            re.DOTALL,
        )
        for m in bug_pat.finditer(result):
            meta  = m.group(1).strip()
            old_s = m.group(2).strip()
            new_s = m.group(3).strip()
            if old_s and new_s and old_s != new_s:
                all_issues.append({
                    "file": p, "rel": rel,
                    "meta": meta, "old": old_s, "new": new_s,
                })

    if not all_issues:
        _log_update("debug", "full debug scan", "no bugs found")
        return (
            f"── Self-Debug Results ────────────────────\n"
            f"Files scanned : {files_scanned}\n"
            f"Bugs found    : 0\n"
            f"──────────────────────────────────────────\n"
            f"No issues found."
        )

    # Show preview of all proposed fixes
    preview_lines = [f"\n{len(all_issues)} bug(s) found:\n"]
    for i, issue in enumerate(all_issues, 1):
        preview_lines.append(
            f"\n[{i}] {issue['rel']}\n"
            f"    {issue['meta'].splitlines()[0] if issue['meta'] else ''}\n"
            f"    OLD: {issue['old'][:80].replace(chr(10), ' ')}...\n"
            f"    NEW: {issue['new'][:80].replace(chr(10), ' ')}..."
        )

    confirmed = confirm_fn("".join(preview_lines) + "\n\nApply all fixes? [y/N] ")
    if not confirmed:
        _log_update("debug", f"scan found {len(all_issues)} bugs", "cancelled")
        return "Debug pass cancelled."

    # Apply fixes
    bugs_fixed = 0
    files_changed: list[str] = []
    backup = _backup()

    for issue in all_issues:
        p: Path = issue["file"]
        src = p.read_text(encoding="utf-8")

        if issue["old"] not in src:
            continue  # already fixed or context mismatch

        new_src = src.replace(issue["old"], issue["new"], 1)
        ok, err = _syntax_ok(new_src)
        if not ok:
            continue  # skip bad patch

        p.write_text(new_src, encoding="utf-8")
        bugs_fixed += 1
        if issue["rel"] not in files_changed:
            files_changed.append(issue["rel"])

    _log_update("debug", f"fixed {bugs_fixed}/{len(all_issues)} bugs", "applied", str(backup))

    lines = [
        "── Self-Debug Results ────────────────────",
        f"Files scanned  : {files_scanned}",
        f"Bugs found     : {len(all_issues)}",
        f"Bugs fixed     : {bugs_fixed}",
        f"Files changed  : {', '.join(files_changed) or 'none'}",
        f"Backup saved   : {backup.name}",
        "──────────────────────────────────────────",
    ]
    if bugs_fixed < len(all_issues):
        skipped = len(all_issues) - bugs_fixed
        lines.append(f"({skipped} patch(es) skipped — context mismatch or syntax error)")
    return "\n".join(lines)


# ── Upgrade mode ───────────────────────────────────────────────────────────────

def run_upgrade_pass(llm_fn, confirm_fn) -> str:
    """
    Phase 1: Read PLANNED.md for unchecked features.
    Phase 2: Pick the best implementable feature.
    Phase 3: Generate routing + method using ===ROUTE=== format.
    Phase 4: Apply with confirmation.
    (mirrors PixelCode build_upgrade_goal)
    """
    _ensure_planned_md()
    planned_text = PLANNED_MD.read_text(encoding="utf-8")

    # Extract unchecked features
    unchecked = [
        line.strip()[5:].strip()
        for line in planned_text.splitlines()
        if line.strip().startswith("- [ ]")
    ]

    if not unchecked:
        return "All planned features are already implemented. Add new entries to PLANNED.md."

    route_section = _read_route_section()
    method_sigs   = _read_method_signatures()

    unchecked_list = "\n".join(f"  {i+1}. {f}" for i, f in enumerate(unchecked[:10]))

    prompt = (
        f"You are upgrading Pixel Assistant (a Python CLI AI assistant).\n\n"
        f"Source directory: {SRC_DIR}\n\n"
        f"Unchecked planned features:\n{unchecked_list}\n\n"
        f"Existing command routing pattern (from _check_meta):\n"
        f"```python\n{route_section[:2500]}\n```\n\n"
        f"Existing method signatures:\n```\n{method_sigs}\n```\n\n"
        f"Step 1: Select the SINGLE best feature to implement now. Criteria:\n"
        f"  • Highest value to a daily user\n"
        f"  • Achievable with stdlib + packages already imported (requests, pathlib, etc.)\n"
        f"  • Does NOT require heavy new dependencies\n"
        f"  • Fits the existing architecture pattern (if-block in _check_meta + method)\n\n"
        f"Step 2: Implement it. Reply ONLY in this format:\n\n"
        f"===FEATURE===\n"
        f"<name of the feature — one line, e.g. '/convert unit converter'>\n"
        f"===ROUTE===\n"
        f"# if-block(s) to add inside _check_meta before 'return None'\n"
        f"===METHOD===\n"
        f"# full handler method(s), 4-space class-level indent\n"
        f"===HELP===\n"
        f"# one line: /command <args>    description\n"
        f"===END===\n\n"
        f"Rules:\n"
        f"  - Routing indented 8 spaces (inside _check_meta inside class)\n"
        f"  - Methods indented 4 spaces (class methods)\n"
        f"  - Local imports only (inside the method body)\n"
        f"  - No stubs — write working code\n"
        f"  - Do NOT duplicate existing commands"
    )

    print("Researching and selecting feature to implement...")
    raw = llm_fn([{"role": "user", "content": prompt}])

    # Extract feature name
    feat_match = re.search(r"===FEATURE===\s*\n(.+?)(?:\n|===)", raw, re.DOTALL)
    feature_name = feat_match.group(1).strip() if feat_match else "unknown feature"

    result = _apply_blocks(raw, feature_name, "upgrade", confirm_fn)

    if "Applied" in result:
        _mark_planned_done(feature_name)
        result += f"\n\nMarked '{feature_name}' as done in PLANNED.md."

    lines = [
        "── Upgrade Results ───────────────────────",
        f"Feature selected : {feature_name}",
        result,
        "──────────────────────────────────────────",
    ]
    return "\n".join(lines)


# ── Full mode ──────────────────────────────────────────────────────────────────

def run_full_pass(llm_fn, confirm_fn) -> str:
    """Debug pass then upgrade pass (mirrors PixelCode /update full)."""
    parts = ["━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
             "PHASE 1 — SELF-DEBUG",
             "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"]
    parts.append(run_debug_pass(llm_fn, confirm_fn))

    parts += ["", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
              "PHASE 2 — SELF-UPGRADE",
              "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"]
    parts.append(run_upgrade_pass(llm_fn, confirm_fn))
    return "\n".join(parts)


# ── Legacy: check (report only) ───────────────────────────────────────────────

def check_code(llm_fn) -> str:
    """Scan all source files and report bugs — no auto-fix (legacy /update check)."""
    files = [SRC_DIR / rel for rel in OWN_FILES if (SRC_DIR / rel).exists()]
    all_findings: list[str] = []

    for f in files:
        rel  = f.relative_to(SRC_DIR)
        text = f.read_text(encoding="utf-8", errors="replace")
        prompt = (
            f"Review this Python file for real bugs only.\n"
            f"Criteria:\n{_BUG_CRITERIA}\n"
            f"Format: numbered list. Each item: line hint, description, one-line fix.\n"
            f"If nothing is wrong, reply exactly: NO ISSUES\n\n"
            f"# File: {rel}\n{text}"
        )
        result = llm_fn([{"role": "user", "content": prompt}])
        if result.strip().upper() != "NO ISSUES":
            all_findings.append(f"── {rel} ──\n{result.strip()}")

    if not all_findings:
        return "No issues found across all source files."
    return "\n\n".join(all_findings)


# ── Legacy: feature / fix generation ──────────────────────────────────────────

def generate_feature(description: str, llm_fn, confirm_fn) -> str:
    route_section = _read_route_section()
    method_sigs   = _read_method_signatures()

    prompt = (
        f"You are extending Pixel Assistant (a Python CLI AI assistant).\n\n"
        f"Existing command routing pattern (from _check_meta):\n"
        f"```python\n{route_section[:2000]}\n```\n\n"
        f"Existing method signatures:\n```\n{method_sigs}\n```\n\n"
        f"Add this new feature: {description}\n\n"
        f"Reply ONLY using this exact format — nothing before ===ROUTE=== or after ===END===:\n\n"
        f"===ROUTE===\n"
        f"# if-block(s) to add inside _check_meta before 'return None'\n"
        f"===METHOD===\n"
        f"# full handler method(s) — 4-space class-level indent\n"
        f"===HELP===\n"
        f"# one line: /command <args>    description\n"
        f"===END===\n\n"
        f"Rules:\n"
        f"- Routing: 8-space indent\n"
        f"- Methods: 4-space indent\n"
        f"- Local imports only (inside methods)\n"
        f"- No stubs — working code only\n"
        f"- Do not duplicate existing commands"
    )

    raw = llm_fn([{"role": "user", "content": prompt}])
    return _apply_blocks(raw, description, "feature", confirm_fn)


def generate_fix(description: str, llm_fn, confirm_fn) -> str:
    src = MAIN_PY.read_text(encoding="utf-8")
    prompt = (
        f"You are fixing a bug in Pixel Assistant.\n\n"
        f"Bug described by user: {description}\n\n"
        f"Full source of main.py:\n```python\n{src}\n```\n\n"
        f"Reply ONLY using this format:\n\n"
        f"===ROUTE===\n"
        f"# corrected if-block(s), or: # no routing changes\n"
        f"===METHOD===\n"
        f"# corrected method(s) in full, or: # no method changes\n"
        f"===HELP===\n"
        f"# no help changes\n"
        f"===END===\n\n"
        f"For fixes, ROUTE and METHOD blocks replace the existing code matched by name/pattern."
    )

    raw = llm_fn([{"role": "user", "content": prompt}])
    return _apply_blocks(raw, description, "fix", confirm_fn, is_fix=True)


# ── Block application (shared) ─────────────────────────────────────────────────

def _apply_blocks(
    llm_output: str,
    description: str,
    kind: str,
    confirm_fn,
    is_fix: bool = False,
) -> str:
    blocks = _parse_llm_blocks(llm_output)
    route  = blocks.get("ROUTE", "").strip()
    method = blocks.get("METHOD", "").strip()
    help_  = blocks.get("HELP",   "").strip()

    if not route and not method:
        return (
            "Could not parse structured output from the LLM.\n"
            "Raw response:\n" + llm_output[:800]
        )

    preview_parts = []
    if route and not route.startswith("# no"):
        preview_parts.append(f"── Routing to add in _check_meta ──\n{route}")
    if method and not method.startswith("# no"):
        preview_parts.append(f"── Method(s) to add ──\n{method}")
    if help_ and not help_.startswith("# no"):
        preview_parts.append(f"── Help line ──\n{help_}")
    preview = "\n\n".join(preview_parts) or "(nothing parseable)"

    confirmed = confirm_fn(f"\n{preview}\n\nApply this to main.py? [y/N] ")
    if not confirmed:
        _log_update(kind, description, "cancelled")
        return "Update cancelled."

    src    = MAIN_PY.read_text(encoding="utf-8")
    backup = _backup()
    new_src = src

    if is_fix:
        new_src = _apply_fix_blocks(new_src, route, method)
    else:
        new_src = _apply_new_blocks(new_src, route, method, help_)

    ok, err = _syntax_ok(new_src)
    if not ok:
        _log_update(kind, description, f"syntax error: {err}", str(backup))
        return (
            f"Syntax error in generated code — main.py NOT modified.\n"
            f"Backup kept: {backup.name}\n\n{err}"
        )

    MAIN_PY.write_text(new_src, encoding="utf-8")
    _log_update(kind, description, "applied", str(backup))
    return (
        f"Applied. Backup saved as {backup.name}.\n"
        f"Restart Pixel (or re-import) to activate the changes."
    )


def _normalise_method(method: str) -> str:
    lines  = method.splitlines()
    indents = [len(l) - len(l.lstrip()) for l in lines if l.strip()]
    base   = min(indents) if indents else 0
    norm   = []
    for line in lines:
        stripped = line.lstrip()
        if not stripped:
            norm.append("")
        else:
            relative = len(line) - len(line.lstrip()) - base
            norm.append("    " + " " * relative + stripped)
    return "\n".join(norm)


def _apply_new_blocks(src: str, route: str, method: str, help_line: str) -> str:
    if route and not route.startswith("# no"):
        indent_route = "\n".join(
            "        " + l if l.strip() else "" for l in route.splitlines()
        )
        src = re.sub(
            r"(        return None\n\n    # ── Notes)",
            indent_route + "\n\n" + r"\1",
            src, count=1,
        )

    if method and not method.startswith("# no"):
        norm_method = _normalise_method(method)
        src = re.sub(
            r"(    def _cmd_prompt\(self)",
            norm_method + "\n\n    def _cmd_prompt(self",
            src, count=1,
        )

    if help_line and not help_line.startswith("# no"):
        text  = help_line.strip().replace("\\", "\\\\")
        entry = f'            "  {text}\\\\n"\n'
        src = re.sub(
            r'(            "  exit / quit[^"]+"\n)',
            entry + r"\1",
            src, count=1,
        )

    return src


def _apply_fix_blocks(src: str, route: str, method: str) -> str:
    if method and not method.startswith("# no"):
        for m in re.finditer(r"def (\w+)\(self", method):
            name = m.group(1)
            new_method_pat = re.compile(
                rf"(    def {re.escape(name)}\(self.*?)(?=\n    def |\Z)", re.DOTALL
            )
            existing_pat = re.compile(
                rf"(    def {re.escape(name)}\(self.*?)(?=\n    def |\Z)", re.DOTALL
            )
            norm_block = _normalise_method(method)
            new_match  = new_method_pat.search(norm_block)
            if new_match:
                replacement = new_match.group(1)
                src = existing_pat.sub(lambda _: replacement, src, count=1)
    return src


# ── Skill generation ───────────────────────────────────────────────────────────

SKILL_TEMPLATE = """\
\"\"\"
{description} — Pixel Assistant skill.
Auto-generated by /update skill.
\"\"\"
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent.parent.parent / "generated"


def {func_name}({params}) -> {return_type}:
    \"\"\"{docstring}\"\"\"
    OUTPUT_DIR.mkdir(exist_ok=True)
    {body}
"""


def generate_skill(description: str, llm_fn, confirm_fn) -> str:
    """
    Generate a new standalone skill module in src/skills/ and register it in main.py.

    Works in three phases:
      1. LLM designs the skill (file name, function signature, logic)
      2. Creates the skill file with syntax check
      3. Registers routing + import in main.py
    """
    import ast

    # Read existing skill files as reference
    skill_dir = SRC_DIR / "skills"
    existing_skills = [p.stem for p in skill_dir.glob("*.py") if p.stem != "__init__"]
    existing_list = "\n".join(f"  - {s}" for s in existing_skills)

    # Read current routing section for context
    route_section = _read_route_section()
    method_sigs = _read_method_signatures()

    prompt = (
        f"You are generating a new skill module for Pixel Assistant (Python CLI AI assistant).\n\n"
        f"User request: {description}\n\n"
        f"Existing skills:\n{existing_list}\n\n"
        f"All skills live in src/skills/ and follow this pattern:\n"
        f"- Each skill is a standalone .py file with a single public function\n"
        f"- It uses OUTPUT_DIR = Path(__file__).parent.parent.parent / 'generated' for file output\n"
        f"- It avoids heavy new dependencies (prefer requests, stdlib)\n"
        f"- It handles errors gracefully with try/except\n\n"
        f"Current routing in main.py:\n```python\n{route_section[:2000]}\n```\n\n"
        f"Current method signatures:\n```\n{method_sigs}\n```\n\n"
        f"Reply ONLY using these EXACT section header names — nothing before or after:\n\n"
        f"===SKILL_NAME===\n"
        f"<snake_case_name>  (e.g. weather_api — becomes src/skills/weather_api.py)\n"
        f"===FUNCTION===\n"
        f"# Complete Python code for the skill file (include all imports and the public function)\n"
        f"===ROUTE===\n"
        f"# if-block(s) to add inside _check_meta before 'return None' (8-space indent)\n"
        f"===METHOD===\n"
        f"# full handler method for main.py to call the skill (4-space class indent)\n"
        f"===IMPORT===\n"
        f"# import line to add at top of main.py, e.g.: from skills.my_skill import my_function\n"
        f"===HELP===\n"
        f"# one help line: /command <args>    description\n"
        f"===END===\n\n"
        f"Rules:\n"
        f"  1. The section header MUST be exactly ===SKILL_NAME===, not anything else\n"
        f"  2. SKILL_NAME value is just the snake_case filename (no .py, no path)\n"
        f"  3. FUNCTION gets written verbatim to src/skills/<SKILL_NAME>.py\n"
        f"  4. ROUTE uses 8-space indent (inside _check_meta inside class)\n"
        f"  5. METHOD uses 4-space indent (class method in main.py)\n"
        f"  6. All imports in METHOD and ROUTE must be local (inside the method body)\n"
        f"  7. No stubs — write working, production-quality code\n"
        f"  8. Use OUTPUT_DIR for saving generated files\n"
        f"  9. If the skill needs an API key, document it in the module docstring"
    )

    print(f"Generating skill: {description}...")
    result = llm_fn([{"role": "user", "content": prompt}])

    blocks = _parse_llm_blocks(result)

    # Flexible block name matching — LLMs often rename blocks
    def _block(name: str) -> str:
        for key, val in blocks.items():
            if key.replace("_", "").replace("-", "") == name.replace("_", "").replace("-", ""):
                return val
        return blocks.get(name, "")

    skill_name = _block("SKILL_NAME") or _block("NAME") or ""
    func_code = _block("FUNCTION") or _block("CODE") or ""
    route = _block("ROUTE") or ""
    method = _block("METHOD") or _block("HANDLER") or ""
    import_line = _block("IMPORT") or ""
    help_line = _block("HELP") or ""

    # If still no name, try the first block key as the name
    if not skill_name and blocks:
        first_key = next(iter(blocks))
        if first_key not in ("ROUTE", "METHOD", "FUNCTION", "IMPORT", "HELP", "END"):
            skill_name = first_key.lower().replace("_", "")
            if not func_code:
                func_code = blocks[first_key]

    # Strip markdown code fences from generated code
    def _strip_fences(text: str) -> str:
        text = re.sub(r'^```\w*\n?', '', text, flags=re.MULTILINE)
        text = re.sub(r'\n?```\s*$', '', text, flags=re.MULTILINE)
        return text.strip()

    func_code = _strip_fences(func_code)
    route = _strip_fences(route)
    method = _strip_fences(method)
    import_line = _strip_fences(import_line)

    if not skill_name or not func_code:
        return (
            "Could not parse structured output from the LLM.\n"
            f"Raw response:\n{result[:800]}"
        )

    skill_path = SRC_DIR / "skills" / f"{skill_name}.py"

    # Build the skill file content
    skill_content = _strip_fences(func_code)
    if not skill_content.startswith('"""'):
        skill_content = (
            f'"""\n{description} — Pixel Assistant skill.\n'
            f'Auto-generated by /update skill.\n"""\n\n'
            f"from pathlib import Path\n\n"
            f"OUTPUT_DIR = Path(__file__).parent.parent.parent / \"generated\"\n\n"
        ) + skill_content

    # Preview what will happen
    preview_lines = [f"── New skill module: skills/{skill_name}.py ──"]
    preview_lines.append(skill_content[:500])
    if route and not route.startswith("# no"):
        preview_lines.append(f"── Routing to add ──")
        preview_lines.append(route)
    if method and not method.startswith("# no"):
        preview_lines.append(f"── Method to add ──")
        preview_lines.append(method)
    if import_line:
        preview_lines.append(f"── Import to add ──")
        preview_lines.append(import_line)

    preview_text = "\n".join(preview_lines) + "\n\nCreate this skill? [y/N] "
    confirmed = confirm_fn(preview_text)
    if not confirmed:
        _log_update("skill", description, "cancelled")
        return "Skill generation cancelled."

    # Create backup of main.py
    backup = _backup()

    # Syntax check the skill file
    ok, err = _syntax_ok(skill_content)
    if not ok:
        _log_update("skill", description, f"syntax error: {err}", str(backup))
        return (
            f"Syntax error in generated skill code — file NOT created.\n"
            f"Backup kept: {backup.name}\n\n{err}"
        )

    # Write skill file
    skill_path.parent.mkdir(exist_ok=True)
    skill_path.write_text(skill_content, encoding="utf-8")
    print(f"  Created: skills/{skill_name}.py")

    # Apply routing + method + import to main.py
    src = MAIN_PY.read_text(encoding="utf-8")
    new_src = src

    if import_line and not import_line.startswith("#"):
        # Add import at the top of main.py (after the docstring and stdlib imports)
        import_to_add = import_line.strip()
        if import_to_add not in src:
            new_src = re.sub(
                r"(from core_files.logger import log_conversation, setup_logger)",
                import_to_add + "\n" + r"\1",
                new_src, count=1,
            )

    if route and not route.startswith("# no"):
        indent_route = "\n".join(
            "        " + l if l.strip() else "" for l in route.splitlines()
        )
        new_src = re.sub(
            r"(        return None\n\n    # ── Notes)",
            indent_route + "\n\n" + r"\1",
            new_src, count=1,
        )

    if method and not method.startswith("# no"):
        # Strip any class boilerplate the LLM might include
        method_clean = re.sub(r'^class\s+\w+.*(?:\n|$)', '', method, flags=re.MULTILINE)
        method_clean = re.sub(r'^\s+\.\.\.\s*$', '', method_clean, flags=re.MULTILINE)
        # Fix: LLMs often write self.<func>() but the function is imported standalone
        import_name = import_line.strip().split()[-1] if import_line.strip() and " import " in import_line else ""
        if import_name:
            method_clean = re.sub(rf'self\.{re.escape(import_name)}\s*\(', f'{import_name}(', method_clean)
        norm_method = _normalise_method(method_clean)
        # Only add if it has actual method definitions
        if re.search(r'def\s+\w+', norm_method):
            new_src = re.sub(
                r"(    def _cmd_prompt\(self)",
                norm_method + "\n\n    def _cmd_prompt(self",
                new_src, count=1,
            )

    if help_line and not help_line.startswith("# no"):
        text = help_line.strip().replace("\\", "\\\\")
        entry = f'            "  {text}\\\\n"\n'
        new_src = re.sub(
            r'(            "  exit / quit[^"]+"\n)',
            entry + r"\1",
            new_src, count=1,
        )

    # Syntax check main.py after modifications
    ok, err = _syntax_ok(new_src)
    if not ok:
        # Rollback: remove the skill file we just created
        skill_path.unlink(missing_ok=True)
        _log_update("skill", description, f"syntax error in main.py: {err}", str(backup))
        return (
            f"Syntax error after applying changes to main.py — rolled back.\n"
            f"Backup kept: {backup.name}\n\n{err}"
        )

    MAIN_PY.write_text(new_src, encoding="utf-8")
    _log_update("skill", description, "applied", str(backup))

    return (
        f"── Skill Generated ──────────────────────────\n"
        f"  Module : skills/{skill_name}.py\n"
        f"  Backup : {backup.name}\n"
        f"  Status : applied\n"
        f"──────────────────────────────────────────────\n"
        f"Restart Pixel to activate the new skill."
    )


# ── Log + rollback ─────────────────────────────────────────────────────────────

def show_log() -> str:
    if not CHANGELOG.exists():
        return "No updates recorded yet."
    log = json.loads(CHANGELOG.read_text(encoding="utf-8"))
    if not log:
        return "Update log is empty."
    lines = ["Update history:\n"]
    for i, entry in enumerate(reversed(log[-20:]), 1):
        mark = "✓" if entry["status"] == "applied" else (
               "–" if entry["status"] == "no bugs found" else "✗"
        )
        lines.append(
            f"  {i:>2}. [{entry['date']}] {mark} "
            f"[{entry['kind']}] {entry['description']}"
        )
    return "\n".join(lines)


def rollback() -> str:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backups = sorted(BACKUP_DIR.glob("main_*.py"))
    if not backups:
        return "No backups found."
    latest = backups[-1]
    shutil.copy2(latest, MAIN_PY)
    return f"Restored main.py from backup: {latest.name}\nRestart Pixel to apply."
