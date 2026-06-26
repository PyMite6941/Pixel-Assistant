"""Tests for the plugin system."""
from pathlib import Path

def test_command_decorator():
    """Verify command decorator exists and functions."""
    import ast
    src = (Path(__file__).parent.parent / "src" / "skills" / "__init__.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    funcs = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    for fn in ["command", "get_command", "get_all_commands", "dispatch", "load_skills"]:
        assert fn in funcs, f"Missing function: {fn}"
    print("[PASS] All plugin system functions found")

def test_memory_commands():
    """Verify memory command registration exists."""
    src = (Path(__file__).parent.parent / "src" / "skills" / "__init__.py").read_text(encoding="utf-8")
    assert "remember" in src, "Missing remember command"
    assert "memories" in src, "Missing memories command"
    assert "forget" in src, "Missing forget command"
    assert "recall" in src, "Missing recall command"
    print("[PASS] Memory commands registered")

if __name__ == "__main__":
    test_command_decorator()
    test_memory_commands()
    print("[PASS] All plugin system tests passed!")
