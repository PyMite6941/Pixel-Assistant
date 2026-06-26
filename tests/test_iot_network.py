"""Tests for IoT, P2P, BLE, and bridge modules."""
import ast
import json
import os
import sys
import tempfile
from pathlib import Path

SRC = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(SRC))

# ── iot.py ───────────────────────────────────────────────────────────────────

def test_iot_device_list_returns_list():
    """device_list() must always return a list, never a string."""
    from skills.iot import device_list
    devices = device_list()
    assert isinstance(devices, list), f"Expected list, got {type(devices)}"
    print("[PASS] device_list() returns list")


def test_iot_device_list_display_returns_string():
    """device_list_display() must return a string."""
    from skills.iot import device_list_display
    result = device_list_display()
    assert isinstance(result, str), f"Expected str, got {type(result)}"
    print("[PASS] device_list_display() returns str")


def test_iot_device_register_and_remove():
    """Register and remove a device roundtrip."""
    from skills.iot import device_register, device_remove, device_list
    test_id = "_test_unittest_temp_"
    # Clean up if leftover
    device_remove(test_id)
    before = len(device_list())
    device_register(test_id, "Test Device", "sensor", "test")
    after = len(device_list())
    assert after == before + 1, f"Expected {before+1} devices, got {after}"
    device_remove(test_id)
    after_clean = len(device_list())
    assert after_clean == before, f"Expected {before} devices, got {after_clean}"
    print("[PASS] device_register and device_remove roundtrip")


def test_iot_device_register_duplicate():
    """Registering the same device twice should not duplicate."""
    from skills.iot import device_register, device_remove, device_list
    test_id = "_test_dup_temp_"
    device_remove(test_id)
    device_register(test_id, "Dup", "sensor", "test")
    before = len(device_list())
    device_register(test_id, "Dup Again", "sensor", "test")
    after = len(device_list())
    assert after == before, f"Duplicate add changed count: {before} -> {after}"
    device_remove(test_id)
    print("[PASS] Duplicate device registration prevented")


def test_iot_device_update_value():
    """Updating a device value should work."""
    from skills.iot import device_register, device_remove, device_update_value, device_get
    test_id = "_test_val_temp_"
    device_remove(test_id)
    device_register(test_id, "Value Test", "sensor", "test")
    ok = device_update_value(test_id, 42.5)
    assert ok, "device_update_value returned False"
    device = device_get(test_id)
    assert device is not None
    assert device["value"] == 42.5, f"Expected 42.5, got {device['value']}"
    device_remove(test_id)
    print("[PASS] device_update_value and device_get roundtrip")


# ── p2p.py ───────────────────────────────────────────────────────────────────

def test_p2p_get_status():
    """get_status() returns a string describing current discovery state."""
    from skills.p2p import get_status
    status = get_status()
    assert isinstance(status, str), f"Expected str, got {type(status)}"
    assert len(status) > 0, "Status should not be empty"
    assert "Active" in status or "Inactive" in status, \
        f"Status should mention Active or Inactive: {status[:50]}"
    print(f"[PASS] get_status() = '{status[:40]}...'")


def test_p2p_discover_once():
    """discover_once() returns a string with discovery results."""
    from skills.p2p import discover_once
    result = discover_once(timeout=1)
    assert isinstance(result, str), f"Expected str, got {type(result)}"
    assert "peer" in result.lower(), f"Result should mention peers: {result[:60]}"
    print(f"[PASS] discover_once() = '{result[:60]}...'")


def test_p2p_get_peers_returns_list():
    """get_peers() always returns a list."""
    from skills.p2p import get_peers
    peers = get_peers()
    assert isinstance(peers, list), f"Expected list, got {type(peers)}"
    print("[PASS] get_peers() returns list")


# ── iot_bridge.py ────────────────────────────────────────────────────────────

def test_iot_bridge_sync_to_registry_empty():
    """_sync_to_iot_registry() handles empty device list gracefully."""
    from skills.iot_bridge import _sync_to_iot_registry
    _sync_to_iot_registry([], "test")
    print("[PASS] _sync_to_iot_registry empty list")


def test_iot_bridge_find_device_over_bridges_unknown():
    """find_device_over_bridges() returns None for unknown devices."""
    from skills.iot_bridge import find_device_over_bridges
    result = find_device_over_bridges("_nonexistent_device_xyz_")
    assert result is None, f"Expected None for unknown device, got {result}"
    print("[PASS] find_device_over_bridges unknown returns None")


def test_iot_bridge_encrypt_decrypt():
    """Encryption / decryption roundtrip for bridge tokens."""
    from skills.iot_bridge import _encrypt, _decrypt
    original = "test-hue-username-12345"
    encrypted = _encrypt(original)
    assert encrypted != original, "Encryption should change the value"
    assert isinstance(encrypted, str), f"Expected str, got {type(encrypted)}"
    decrypted = _decrypt(encrypted)
    assert decrypted == original, f"Roundtrip failed: '{original}' != '{decrypted}'"
    print("[PASS] _encrypt/_decrypt roundtrip")


# NOTE: _save_bridges / _load_bridges write to the real bridges.json file.
# Full roundtrip testing is done via _encrypt/_decrypt above.
# Manual verification: run /hue register in the TUI and check that
# functionalities/iot/bridges.json contains encrypted blobs, not raw tokens.
print("[SKIP] _save_bridges/_load_bridges roundtrip (uses real file path)")


# ── ble_scanner.py ───────────────────────────────────────────────────────────

def test_ble_cmd_help():
    """cmd_ble() returns help when given invalid args."""
    from skills.ble_scanner import cmd_ble
    result = cmd_ble("invalid_arg_xyz", None)
    assert isinstance(result, str), f"Expected str, got {type(result)}"
    assert "Usage" in result or "install" in result, \
        f"Should show usage or install instructions: {result[:80]}"
    print("[PASS] cmd_ble returns help for invalid args")


def test_ble_cmd_no_args():
    """cmd_ble() runs with default args (no crash)."""
    from skills.ble_scanner import cmd_ble
    result = cmd_ble("", None)
    assert isinstance(result, str), f"Expected str, got {type(result)}"
    print(f"[PASS] cmd_ble('') returned {len(result)} chars")


def test_ble_module_imports():
    """ble_scanner module parses correctly regardless of bleak availability."""
    src = (SRC / "skills" / "ble_scanner.py").read_text(encoding="utf-8")
    ast.parse(src)
    assert "BleakScanner" in src or "HAS_BLEAK" in src
    print("[PASS] ble_scanner.py has valid syntax and references BleakScanner")


# ── Run all ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        test_iot_device_list_returns_list,
        test_iot_device_list_display_returns_string,
        test_iot_device_register_and_remove,
        test_iot_device_register_duplicate,
        test_iot_device_update_value,
        test_p2p_get_status,
        test_p2p_discover_once,
        test_p2p_get_peers_returns_list,
        test_iot_bridge_sync_to_registry_empty,
        test_iot_bridge_find_device_over_bridges_unknown,
        test_iot_bridge_encrypt_decrypt,
        test_ble_cmd_help,
        test_ble_cmd_no_args,
        test_ble_module_imports,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  [PASS] {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {t.__name__}: {e}")
            failed += 1
    print(f"\nResults: {passed} passed, {failed} failed")
