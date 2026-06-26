"""Tests for cross-platform utilities."""
from pathlib import Path

def test_platform_imports():
    """Verify platform module has valid syntax."""
    import ast
    src = (Path(__file__).parent.parent / "src" / "core_files" / "platform.py").read_text(encoding="utf-8")
    ast.parse(src)
    assert True
    print("[PASS] platform.py parses OK")

def test_platform_functions():
    """Test the required functions exist."""
    import ast
    src = (Path(__file__).parent.parent / "src" / "core_files" / "platform.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    funcs = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    for fn in ["open_file", "play_beep", "copy_clipboard"]:
        assert fn in funcs, f"Missing function: {fn}"
    print(f"[PASS] All {len(funcs)} functions found")

if __name__ == "__main__":
    test_platform_imports()
    test_platform_functions()
    print("[PASS] All platform tests passed!")
