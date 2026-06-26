"""Tests for the agent system."""
from pathlib import Path

def test_agent_personas():
    """Verify all agent personas are defined."""
    import ast
    src = (Path(__file__).parent.parent / "src" / "skills" / "agent.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    assigns = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign) and hasattr(n.targets[0], 'id'):
            assigns[n.targets[0].id] = n.value
    assert "AGENT_PERSONAS" in assigns, "Missing AGENT_PERSONAS"
    print("[PASS] AGENT_PERSONAS found")

def test_agent_functions():
    """Verify key functions and classes exist."""
    import ast
    src = (Path(__file__).parent.parent / "src" / "skills" / "agent.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    funcs = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    for fn in ["detect_agent_type", "auto_route", "_save_agent_log", "_save_active_agents"]:
        assert fn in funcs, f"Missing function: {fn}"
    classes = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}
    assert "Agent" in classes, "Missing Agent class"
    assert "AgentResult" in classes, "Missing AgentResult class"
    print("[PASS] Agent class and functions found")

if __name__ == "__main__":
    test_agent_personas()
    test_agent_functions()
    print("[PASS] All agent tests passed!")
