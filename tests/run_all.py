"""Run all tests."""
import sys
from pathlib import Path

# Fix Windows console encoding
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

SRC = Path(__file__).parent.parent / "src"
TESTS = Path(__file__).parent
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(TESTS))

PASS = "[PASS]"
FAIL = "[FAIL]"

tests = [
    ("Platform",       "test_platform"),
    ("UI",             "test_ui"),
    ("Agent",          "test_agent"),
    ("Plugin System",  "test_skills_init"),
    ("Memory",         "test_memory"),
    ("IoT & Network",  "test_iot_network"),
]

passed = 0
failed = 0

for name, module_name in tests:
    print(f"\n{'='*50}")
    print(f"  {name}")
    print(f"{'='*50}")
    try:
        __import__(module_name)
        mod = sys.modules[module_name]
        test_funcs = sorted(f for f in dir(mod) if f.startswith("test_"))
        for tf in test_funcs:
            try:
                getattr(mod, tf)()
                print(f"  {PASS} {tf}")
                passed += 1
            except Exception as e:
                print(f"  {FAIL} {tf}: {e}")
                failed += 1
    except Exception as e:
        print(f"  {FAIL} Import failed: {e}")
        failed += 1

print(f"\n{'='*50}")
print(f"  Results: {passed} passed, {failed} failed")
print(f"{'='*50}")
sys.exit(0 if failed == 0 else 1)
