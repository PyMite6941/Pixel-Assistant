"""
BLE (Bluetooth Low Energy) device scanner for Pixel Assistant.
Discovers nearby BLE peripherals and registers them in the IoT device registry.
Requires bleak (pip install bleak).
"""
import asyncio
import logging
import sys
import threading
from datetime import datetime, timezone

from skills import command

logger = logging.getLogger(__name__)

try:
    from bleak import BleakScanner
    HAS_BLEAK = True
except ImportError:
    HAS_BLEAK = False


def _available() -> str:
    if sys.platform == "win32":
        return "Available (Windows)"
    elif sys.platform == "darwin":
        return "Available (macOS)"
    elif sys.platform == "linux":
        return "Available (Linux — may need sudo/bluez)"
    return "Unknown platform"


def _scan_sync(duration: int = 8) -> list[dict]:
    """Run a BLE scan synchronously (wraps asyncio)."""
    if not HAS_BLEAK:
        return []

    found = []

    async def _scan():
        nonlocal found
        try:
            devices = await BleakScanner.discover(timeout=duration, return_adv=True)
            for addr, adv_data in devices.items():
                adv = adv_data if isinstance(adv_data, tuple) and len(adv_data) > 0 else None
                name = ""
                rssi = -100
                if adv:
                    if hasattr(adv, 'name') and adv.name:
                        name = adv.name
                    if hasattr(adv, 'rssi'):
                        rssi = adv.rssi

                if not name:
                    name = f"BLE-{addr[:8]}"

                manufacturer = ""
                if adv and hasattr(adv, 'manufacturer_data') and adv.manufacturer_data:
                    for mid in list(adv.manufacturer_data.keys())[:1]:
                        manufacturer = f"0x{mid:04X}"

                found.append({
                    "address": addr,
                    "name": name,
                    "rssi": rssi,
                    "manufacturer": manufacturer,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
        except Exception as e:
            logger.warning("BLE scan error: %s", e)

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_scan())
        loop.close()
    except Exception as e:
        logger.warning("BLE scan loop error: %s", e)

    found.sort(key=lambda d: d["rssi"], reverse=True)
    return found


def _sync_to_iot_registry(devices: list[dict]):
    """Register discovered BLE devices into the IoT device registry."""
    try:
        from skills.iot import device_register, device_list
        existing = device_list()
        existing_ids = {d.get("id") for d in existing if isinstance(d, dict)}
        for d in devices:
            did = d.get("address", "").replace(":", "-").lower()
            if did and did not in existing_ids:
                device_register(
                    did,
                    d.get("name", did),
                    "ble_sensor",
                    "bluetooth",
                )
    except ImportError:
        logger.debug("iot.py not available for registry sync")
    except Exception as e:
        logger.warning("BLE registry sync error: %s", e)


@command(name="ble", aliases=["blescan", "bluetooth"],
         help_text="Scan for BLE devices: /ble [duration_seconds]")
def cmd_ble(args: str, assistant) -> str:
    duration_str = args.strip()
    duration = 8
    if duration_str.isdigit():
        duration = int(duration_str)
    elif duration_str:
        return ("Usage: /ble [duration_seconds]\n"
                "Scan for nearby Bluetooth Low Energy devices.\n"
                "  /ble              scan for 8 seconds\n"
                "  /ble 15           scan for 15 seconds\n"
                f"Status: {_available()}\n"
                f"Bleak: {'installed' if HAS_BLEAK else 'NOT installed — run: pip install bleak'}")

    if not HAS_BLEAK:
        return ("BLE scanning requires the 'bleak' library.\n"
                "Install with: pip install bleak\n"
                f"Platform: {_available()}")

    devices = _scan_sync(duration)

    if not devices:
        return "No BLE devices found nearby."

    _sync_to_iot_registry(devices)

    lines = [f"Found {len(devices)} BLE device(s):"]
    for d in devices:
        name = d.get("name", "?")
        addr = d.get("address", "?")
        rssi = d.get("rssi", -100)
        mfr = d.get("manufacturer", "")
        bars = "█" * max(1, (rssi + 100) // 5) if rssi > -100 else "?"
        mfr_str = f" [{mfr}]" if mfr else ""
        lines.append(f"  {bars:20s} {name:30s} {addr:18s} {rssi}dBm{mfr_str}")

    lines.extend([
        "",
        "Devices are now registered in the IoT registry.",
        "  /iot list                — view all devices",
        "  /iot sensor start <id>   — simulate sensor values",
    ])
    return "\n".join(lines)
