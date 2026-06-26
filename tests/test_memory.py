"""Tests for RAG memory system."""
import json
import tempfile
from pathlib import Path

# Patch the MEMORY_FILE to a temp path before importing
import skills.memory as mem
mem.MEMORY_FILE = Path(tempfile.mktemp(suffix=".json"))

def _clean():
    if mem.MEMORY_FILE.exists():
        mem.MEMORY_FILE.unlink()

def test_similarity():
    score = mem._similarity("hello", "hello")
    assert score == 1.0, f"Expected 1.0, got {score}"
    score = mem._similarity("hello", "helo")
    assert score > 0.5, f"Expected >0.5, got {score}"
    score = mem._similarity("hello", "world")
    assert score < 0.3, f"Expected <0.3, got {score}"
    print("[PASS] test_similarity")

def test_remember_and_recall():
    _clean()
    result = mem.remember("My name is Alice")
    assert "Remembered" in result or "Updated" in result
    mem.remember("I like pizza with pineapple")
    # Recall should find relevant memories
    results = mem.recall("what is my name", top_k=3)
    assert len(results) >= 1, f"Expected >=1 result, got {len(results)}"
    assert "Alice" in results[0]["fact"], f"Expected Alice, got {results[0]['fact']}"
    print("[PASS] test_remember_and_recall")

def test_forget():
    _clean()
    mem.remember("test data to forget")
    count = mem.forget("test")
    assert count >= 1, f"Expected >=1, got {count}"
    print("[PASS] test_forget")

def test_clear():
    _clean()
    mem.remember("something")
    assert len(mem.all_memories()) >= 1
    mem.clear()
    assert len(mem.all_memories()) == 0
    print("[PASS] test_clear")

if __name__ == "__main__":
    test_similarity()
    test_remember_and_recall()
    test_forget()
    test_clear()
    print("[PASS] All memory tests passed!")
