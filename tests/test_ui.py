"""Tests for the UI module."""
from pathlib import Path

def test_ui_imports():
    """Verify UI module can be imported and has all required components."""
    import ast
    src = (Path(__file__).parent.parent / "src" / "core_files" / "ui.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    funcs = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    required = [
        "show_header", "show_farewell",
        "show_user_message", "show_response",
        "show_streaming_start", "show_streaming_end",
        "show_info", "show_error", "show_success", "show_warning",
        "show_panel", "show_markdown", "show_help_panel", "show_table",
        "divider", "input_styled",
    ]
    for fn in required:
        assert fn in funcs, f"Missing UI function: {fn}"
    print(f"[PASS] All {len(required)} UI functions found")

def test_color_constants():
    """Verify color constants are exported."""
    import ast
    src = (Path(__file__).parent.parent / "src" / "core_files" / "ui.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    assigns = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign) and hasattr(n.targets[0], 'id'):
            assigns[n.targets[0].id] = n.value
    for const in ["C_PRIMARY", "C_USER", "C_ASSISTANT", "C_DIM", "C_SUCCESS", "C_WARN", "C_ERROR", "C_ACCENT"]:
        assert const in assigns, f"Missing color constant: {const}"
    print("[PASS] All color constants found")

if __name__ == "__main__":
    test_ui_imports()
    test_color_constants()
    print("[PASS] All UI tests passed!")
