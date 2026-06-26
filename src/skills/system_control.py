"""
System control module for Pixel Assistant.
Full laptop control: system info, process/window management, power, audio, etc.
Uses psutil + Python standard library. Optional: pyautogui, PIL.
"""
import json
import os
import platform
import re
import shlex
import shutil
import signal
import socket
import struct
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

try:
    import psutil
except ImportError:
    psutil = None

try:
    import pyautogui as _pyautogui
    _HAS_PYAUTOGUI = True
except ImportError:
    _HAS_PYAUTOGUI = False

try:
    from PIL import ImageGrab as _ImageGrab
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _fmt_bytes(b: float) -> str:
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if abs(b) < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} PB"


def _fmt_seconds(secs: float) -> str:
    days, rem = divmod(int(secs), 86400)
    hours, rem = divmod(rem, 3600)
    mins, secs = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if mins:
        parts.append(f"{mins}m")
    parts.append(f"{secs}s")
    return " ".join(parts)


def _check_psutil():
    if psutil is None:
        raise RuntimeError("psutil is required for system control functions")


def _run_pwsh(script: str) -> tuple[str, str]:
    """Run a PowerShell script and return (stdout, stderr)."""
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=15,
        )
        return r.stdout.strip(), r.stderr.strip()
    except subprocess.TimeoutExpired:
        return "", "Timeout"
    except FileNotFoundError:
        return "", "PowerShell not found"
    except Exception as e:
        return "", str(e)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. System Information
# ═══════════════════════════════════════════════════════════════════════════════

def sys_info() -> dict:
    """Return comprehensive system info dict."""
    _check_psutil()
    boot_time = datetime.fromtimestamp(psutil.boot_time())
    uptime = datetime.now() - boot_time
    cpu_freq = psutil.cpu_freq()
    return {
        "os": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
        },
        "hardware": {
            "processor": platform.processor() or os.environ.get("PROCESSOR_IDENTIFIER", "unknown"),
            "cpu_count_physical": psutil.cpu_count(logical=False),
            "cpu_count_logical": psutil.cpu_count(logical=True),
            "architecture": platform.machine(),
            "cpu_freq_current_mhz": round(cpu_freq.current, 2) if cpu_freq else None,
            "cpu_freq_max_mhz": round(cpu_freq.max, 2) if cpu_freq else None,
        },
        "hostname": socket.gethostname(),
        "boot_time": boot_time.isoformat(),
        "uptime_seconds": int(uptime.total_seconds()),
        "uptime_human": _fmt_seconds(uptime.total_seconds()),
        "python_version": sys.version,
    }


def sys_cpu() -> dict:
    """Return CPU stats."""
    _check_psutil()
    per_core = psutil.cpu_percent(interval=0.3, percpu=True)
    overall = psutil.cpu_percent(interval=0.1)
    freq = psutil.cpu_freq()
    return {
        "percent": overall,
        "per_core": per_core,
        "count_physical": psutil.cpu_count(logical=False),
        "count_logical": psutil.cpu_count(logical=True),
        "frequency_current_mhz": round(freq.current, 2) if freq else None,
        "frequency_max_mhz": round(freq.max, 2) if freq else None,
    }


def sys_memory() -> dict:
    """Return memory stats."""
    _check_psutil()
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    return {
        "total": mem.total,
        "total_human": _fmt_bytes(mem.total),
        "available": mem.available,
        "available_human": _fmt_bytes(mem.available),
        "used": mem.used,
        "used_human": _fmt_bytes(mem.used),
        "percent": mem.percent,
        "swap_total": swap.total,
        "swap_total_human": _fmt_bytes(swap.total),
        "swap_used": swap.used,
        "swap_used_human": _fmt_bytes(swap.used),
        "swap_percent": swap.percent,
    }


def sys_disk() -> list[dict]:
    """Return per-partition disk stats."""
    _check_psutil()
    results = []
    for part in psutil.disk_partitions():
        try:
            usage = psutil.disk_usage(part.mountpoint)
            results.append({
                "device": part.device,
                "mountpoint": part.mountpoint,
                "fstype": part.fstype,
                "total": usage.total,
                "total_human": _fmt_bytes(usage.total),
                "used": usage.used,
                "used_human": _fmt_bytes(usage.used),
                "free": usage.free,
                "free_human": _fmt_bytes(usage.free),
                "percent": usage.percent,
            })
        except (PermissionError, OSError):
            continue
    return results


def sys_network() -> dict:
    """Return network stats."""
    _check_psutil()
    net = psutil.net_io_counters()
    conns = psutil.net_connections()
    return {
        "bytes_sent": net.bytes_sent,
        "bytes_sent_human": _fmt_bytes(net.bytes_sent),
        "bytes_recv": net.bytes_recv,
        "bytes_recv_human": _fmt_bytes(net.bytes_recv),
        "packets_sent": net.packets_sent,
        "packets_recv": net.packets_recv,
        "connections_count": len(conns),
    }


def sys_battery() -> dict:
    """Return battery info (if available)."""
    _check_psutil()
    if not hasattr(psutil, "sensors_battery"):
        return {"available": False, "error": "Not supported on this platform"}
    bat = psutil.sensors_battery()
    if bat is None:
        return {"available": False, "error": "No battery detected"}
    secsleft = None
    if bat.secsleft != psutil.POWER_TIME_UNLIMITED and bat.secsleft != psutil.POWER_TIME_UNKNOWN:
        secsleft = bat.secsleft
    return {
        "available": True,
        "percent": bat.percent,
        "power_plugged": bat.power_plugged,
        "time_left_seconds": secsleft,
        "time_left_human": _fmt_seconds(secsleft) if secsleft else "N/A",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Process Management
# ═══════════════════════════════════════════════════════════════════════════════

def process_list(sort_by: str = "cpu", limit: int = 20) -> list[dict]:
    """List top processes sorted by cpu/memory/name/pid."""
    _check_psutil()
    valid_keys = {"cpu", "memory", "name", "pid"}
    if sort_by not in valid_keys:
        sort_by = "cpu"

    processes = []
    for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status", "create_time"]):
        try:
            info = proc.info
            info["create_time"] = info["create_time"]
            processes.append(info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    reverse = sort_by not in ("name", "pid")
    key_map = {
        "cpu": lambda p: p.get("cpu_percent") or 0,
        "memory": lambda p: p.get("memory_percent") or 0,
        "name": lambda p: (p.get("name") or "").lower(),
        "pid": lambda p: p.get("pid") or 0,
    }
    processes.sort(key=key_map[sort_by], reverse=reverse)

    results = []
    for p in processes[:limit]:
        created = None
        if p.get("create_time"):
            try:
                created = datetime.fromtimestamp(p["create_time"]).isoformat()
            except Exception:
                pass
        results.append({
            "pid": p.get("pid"),
            "name": p.get("name", "?"),
            "cpu_percent": round(p.get("cpu_percent") or 0, 1),
            "memory_percent": round(p.get("memory_percent") or 0, 1),
            "status": p.get("status", "?"),
            "created": created,
        })
    return results


def process_kill(pid: int, force: bool = False) -> str:
    """Kill a process by PID. Force = SIGKILL vs SIGTERM."""
    _check_psutil()
    try:
        proc = psutil.Process(pid)
        name = proc.name()
        if force:
            proc.kill()
            return f"Force-killed PID {pid} ({name})"
        else:
            proc.terminate()
            return f"Terminated PID {pid} ({name})"
    except psutil.NoSuchProcess:
        return f"Error: No process with PID {pid}"
    except psutil.AccessDenied:
        return f"Error: Access denied to kill PID {pid}"
    except Exception as e:
        return f"Error: {e}"


def process_info(pid: int) -> dict:
    """Get detailed info about a process."""
    _check_psutil()
    try:
        proc = psutil.Process(pid)
        with proc.oneshot():
            conns = []
            try:
                for c in proc.connections():
                    conns.append({
                        "fd": c.fd,
                        "family": str(c.family),
                        "type": str(c.type),
                        "laddr": f"{c.laddr.ip}:{c.laddr.port}" if c.laddr else None,
                        "raddr": f"{c.raddr.ip}:{c.raddr.port}" if c.raddr else None,
                        "status": c.status,
                    })
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                conns = None

            threads = []
            try:
                for t in proc.threads():
                    threads.append({"id": t.id, "user_time": t.user_time, "system_time": t.system_time})
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                threads = None

            files = []
            try:
                for f in proc.open_files():
                    files.append({"path": f.path, "fd": f.fd})
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                files = None

            env = None
            try:
                env = dict(proc.environ())
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                pass

            return {
                "pid": proc.pid,
                "name": proc.name(),
                "status": proc.status(),
                "created": datetime.fromtimestamp(proc.create_time()).isoformat() if proc.create_time() else None,
                "cpu_percent": proc.cpu_percent(interval=0.1),
                "memory_percent": proc.memory_percent(),
                "memory_rss": proc.memory_info().rss,
                "memory_rss_human": _fmt_bytes(proc.memory_info().rss),
                "cmdline": proc.cmdline(),
                "exe": proc.exe(),
                "cwd": proc.cwd(),
                "username": proc.username(),
                "num_threads": proc.num_threads(),
                "connections": conns,
                "open_files": files,
                "threads": threads,
                "environ": env,
            }
    except psutil.NoSuchProcess:
        return {"error": f"No process with PID {pid}"}
    except psutil.AccessDenied:
        return {"error": f"Access denied to PID {pid}"}
    except Exception as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Window Management
# ═══════════════════════════════════════════════════════════════════════════════

def window_list() -> list[dict]:
    """List visible windows with titles."""
    results = []
    system = platform.system()

    if system == "Windows":
        script = r"""
Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;
using System.Diagnostics;
public class WinAPI {
    public delegate bool EnumWindowsProc(IntPtr hWnd, int lParam);
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, int lParam);
    [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out int lpdwProcessId);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern int GetWindowTextLength(IntPtr hWnd);
}
"@
$windows = @()
$callback = {
    param($hWnd, $lParam)
    if ([WinAPI]::IsWindowVisible($hWnd)) {
        $len = [WinAPI]::GetWindowTextLength($hWnd)
        if ($len -gt 0) {
            $sb = New-Object System.Text.StringBuilder($len + 1)
            [WinAPI]::GetWindowText($hWnd, $sb, $sb.Capacity)
            $title = $sb.ToString()
            $pid = 0
            [WinAPI]::GetWindowThreadProcessId($hWnd, [ref]$pid)
            try {
                $proc = Get-Process -Id $pid -ErrorAction Stop
                $windows += @{hWnd = $hWnd.ToString(); pid = $pid; title = $title; exe = $proc.MainModule.FileName}
            } catch {
                $windows += @{hWnd = $hWnd.ToString(); pid = $pid; title = $title; exe = $null}
            }
        }
    }
    return $true
}
$enum = [WinAPI+EnumWindowsProc]$callback
[WinAPI]::EnumWindows($enum, 0)
$windows | ConvertTo-Json -Compress
"""
        out, err = _run_pwsh(script)
        if out:
            try:
                items = json.loads(out)
                if isinstance(items, dict):
                    items = [items]
                for item in items:
                    results.append({
                        "pid": item.get("pid"),
                        "title": item.get("title", ""),
                        "executable": item.get("exe"),
                    })
            except (json.JSONDecodeError, TypeError):
                pass

    elif system == "Darwin":
        out, _ = _run_pwsh("""osascript -e 'tell application "System Events" to get name of every process whose visible is true' 2>/dev/null""")
        if out:
            for name in out.replace(",", "\n").strip().splitlines():
                name = name.strip()
                if name:
                    results.append({"pid": None, "title": name, "executable": name})

    elif system == "Linux":
        try:
            r = subprocess.run(["wmctrl", "-l"], capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                for line in r.stdout.strip().splitlines():
                    parts = line.split(None, 3)
                    if len(parts) >= 4:
                        results.append({
                            "pid": None,
                            "title": parts[3],
                            "executable": parts[2] if len(parts) > 2 else None,
                        })
        except (FileNotFoundError, subprocess.TimeoutExpired):
            try:
                r = subprocess.run(["xdotool", "search", "--onlyvisible", "--name", ".*"],
                                   capture_output=True, text=True, timeout=5)
                if r.returncode == 0 and r.stdout.strip():
                    for wid in r.stdout.strip().splitlines():
                        name_r = subprocess.run(["xdotool", "getwindowname", wid.strip()],
                                                capture_output=True, text=True, timeout=3)
                        if name_r.stdout.strip():
                            results.append({"pid": None, "title": name_r.stdout.strip(), "executable": None})
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass

    return results


def _win_focus_window(title_or_pid) -> bool:
    """Focus a window on Windows by title substring or PID."""
    script = r"""
param([string]$target)
Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public class WinAPI {
    public delegate bool EnumWindowsProc(IntPtr hWnd, int lParam);
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, int lParam);
    [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out int lpdwProcessId);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern int GetWindowTextLength(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindowAsync(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hWnd);
}
"@
$found = $false
$callback = {
    param($hWnd, $lParam)
    if ([WinAPI]::IsWindowVisible($hWnd)) {
        $len = [WinAPI]::GetWindowTextLength($hWnd)
        if ($len -gt 0) {
            $sb = New-Object System.Text.StringBuilder($len + 1)
            [WinAPI]::GetWindowText($hWnd, $sb, $sb.Capacity)
            $title = $sb.ToString()
            $pid = 0
            [WinAPI]::GetWindowThreadProcessId($hWnd, [ref]$pid)
            $target = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($lParam)
            if ($title -match $target -or $pid -match $target) {
                if ([WinAPI]::IsIconic($hWnd)) { [WinAPI]::ShowWindowAsync($hWnd, 9) | Out-Null }
                [WinAPI]::SetForegroundWindow($hWnd) | Out-Null
                $global:found = $true
                return $false
            }
        }
    }
    return $true
}
$targetStr = $target
$targetPtr = [System.Runtime.InteropServices.Marshal]::StringToHGlobalAuto($targetStr)
$enum = [WinAPI+EnumWindowsProc]$callback
[WinAPI]::EnumWindows($enum, $targetPtr)
[System.Runtime.InteropServices.Marshal]::FreeHGlobal($targetPtr)
if ($global:found) { Write-Output "OK" } else { Write-Output "NOT_FOUND" }
"""
    out, _ = _run_pwsh(f"$target = '{title_or_pid}'; " + script)
    return out.strip() == "OK"


def window_focus(title_or_pid) -> bool:
    """Bring a window to focus by title substring or PID."""
    system = platform.system()
    if system == "Windows":
        return _win_focus_window(title_or_pid)
    elif system == "Darwin":
        script = f"""osascript -e 'tell application "{title_or_pid}" to activate' 2>/dev/null"""
        subprocess.run(["osascript", "-e", f'tell application "{title_or_pid}" to activate'],
                       capture_output=True, timeout=5)
        return True
    elif system == "Linux":
        try:
            subprocess.run(["xdotool", "search", "--name", str(title_or_pid), "windowactivate"],
                           capture_output=True, timeout=5)
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
    return False


def _win_close_window(title_or_pid) -> bool:
    """Close a window on Windows by title substring or PID."""
    script = r"""
param([string]$target)
Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public class WinAPI {
    public delegate bool EnumWindowsProc(IntPtr hWnd, int lParam);
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, int lParam);
    [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out int lpdwProcessId);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern int GetWindowTextLength(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern IntPtr SendMessage(IntPtr hWnd, uint Msg, IntPtr wParam, IntPtr lParam);
    [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr hWnd, uint Msg, IntPtr wParam, IntPtr lParam);
    public const uint WM_CLOSE = 0x0010;
}
"@
$found = $false
$callback = {
    param($hWnd, $lParam)
    if ([WinAPI]::IsWindowVisible($hWnd)) {
        $len = [WinAPI]::GetWindowTextLength($hWnd)
        if ($len -gt 0) {
            $sb = New-Object System.Text.StringBuilder($len + 1)
            [WinAPI]::GetWindowText($hWnd, $sb, $sb.Capacity)
            $title = $sb.ToString()
            $pid = 0
            [WinAPI]::GetWindowThreadProcessId($hWnd, [ref]$pid)
            $target = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($lParam)
            if ($title -match $target -or $pid -match $target) {
                [WinAPI]::PostMessage($hWnd, [WinAPI]::WM_CLOSE, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null
                $global:found = $true
                return $false
            }
        }
    }
    return $true
}
$targetStr = $target
$targetPtr = [System.Runtime.InteropServices.Marshal]::StringToHGlobalAuto($targetStr)
$enum = [WinAPI+EnumWindowsProc]$callback
[WinAPI]::EnumWindows($enum, $targetPtr)
[System.Runtime.InteropServices.Marshal]::FreeHGlobal($targetPtr)
if ($global:found) { Write-Output "OK" } else { Write-Output "NOT_FOUND" }
"""
    out, _ = _run_pwsh(f"$target = '{title_or_pid}'; " + script)
    return out.strip() == "OK"


def window_close(title_or_pid) -> bool:
    """Close a window gracefully."""
    system = platform.system()
    if system == "Windows":
        if isinstance(title_or_pid, int) or (isinstance(title_or_pid, str) and title_or_pid.isdigit()):
            pid = int(title_or_pid)
            try:
                proc = psutil.Process(pid) if psutil else None
                if proc:
                    proc.terminate()
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return _win_close_window(title_or_pid)
    elif system == "Darwin":
        script = f"""osascript -e 'tell application "{title_or_pid}" to quit' 2>/dev/null"""
        subprocess.run(["osascript", "-e", f'tell application "{title_or_pid}" to quit'],
                       capture_output=True, timeout=5)
        return True
    elif system == "Linux":
        try:
            subprocess.run(["xdotool", "search", "--name", str(title_or_pid), "windowclose"],
                           capture_output=True, timeout=5)
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
    return False


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Application Launching
# ═══════════════════════════════════════════════════════════════════════════════

def app_launch(app_name_or_path: str, args: str = "") -> str:
    """Launch an application by name or path."""
    system = platform.system()
    quoted = shlex.quote(app_name_or_path)
    try:
        if system == "Windows":
            cmd = f"start \"\" {quoted} {args}"
            subprocess.Popen(cmd, shell=True)
            return f"Launched: {app_name_or_path}"
        elif system == "Darwin":
            subprocess.Popen(["open", app_name_or_path] + (args.split() if args else []))
            return f"Launched: {app_name_or_path}"
        elif system == "Linux":
            subprocess.Popen(["xdg-open", app_name_or_path] + (args.split() if args else []))
            return f"Launched: {app_name_or_path}"
    except Exception as e:
        # Fallback: try direct execution
        try:
            cmd = [app_name_or_path] + (args.split() if args else [])
            subprocess.Popen(cmd)
            return f"Launched: {app_name_or_path}"
        except Exception as e2:
            return f"Error: Could not launch {app_name_or_path}: {e2}"


def app_find(app_name: str) -> str:
    """Find an application path by name (searches PATH and common locations)."""
    which = shutil.which(app_name)
    if which:
        return which

    system = platform.system()
    common_dirs = []

    if system == "Windows":
        prog_files = os.environ.get("ProgramFiles", "C:\\Program Files")
        prog_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
        local_appdata = os.environ.get("LOCALAPPDATA", "")
        common_dirs = [
            prog_files, prog_files_x86, local_appdata,
            f"{prog_files}\\WindowsApps",
        ]
    elif system == "Darwin":
        common_dirs = ["/Applications", "/Applications/Utilities"]
    elif system == "Linux":
        common_dirs = ["/usr/bin", "/usr/local/bin", "/opt", "/snap/bin"]

    name_lower = app_name.lower()
    for base in common_dirs:
        base_path = Path(base)
        if not base_path.exists():
            continue
        try:
            # Search with .exe/.app/.desktop extensions
            if system == "Windows":
                pattern = f"**/{name_lower}.exe"
            elif system == "Darwin":
                pattern = f"**/{name_lower}.app"
            else:
                pattern = f"**/{name_lower}*"

            for match in base_path.glob(pattern):
                if match.is_file() or match.is_dir():
                    return str(match.resolve())
        except (PermissionError, OSError):
            continue

    # Try PATH search one more time with common extensions
    if system == "Windows":
        for ext in [".exe", ".bat", ".cmd", ".com"]:
            which = shutil.which(app_name + ext)
            if which:
                return which

    return f"Error: Could not find '{app_name}' on PATH or in common locations"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Power Management
# ═══════════════════════════════════════════════════════════════════════════════

def power_sleep():
    """Put system to sleep."""
    system = platform.system()
    try:
        if system == "Windows":
            subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
                           capture_output=True, timeout=5)
        elif system == "Darwin":
            subprocess.run(["pmset", "sleepnow"], capture_output=True, timeout=5)
        elif system == "Linux":
            subprocess.run(["systemctl", "suspend"], capture_output=True, timeout=5)
    except Exception as e:
        return f"Error: Sleep failed: {e}"


def power_hibernate():
    """Hibernate system."""
    system = platform.system()
    try:
        if system == "Windows":
            subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "1,1,0"],
                           capture_output=True, timeout=5)
        elif system == "Darwin":
            subprocess.run(["pmset", "sleepnow"], capture_output=True, timeout=5)
        elif system == "Linux":
            subprocess.run(["systemctl", "hibernate"], capture_output=True, timeout=5)
    except Exception as e:
        return f"Error: Hibernate failed: {e}"


def power_shutdown(delay: int = 0):
    """Shut down system after delay seconds."""
    system = platform.system()
    try:
        if system == "Windows":
            subprocess.run(["shutdown", "/s", "/t", str(int(delay))], capture_output=True, timeout=5)
            return f"Shutdown scheduled in {delay}s"
        elif system == "Darwin":
            subprocess.run(["sudo", "shutdown", "-h", f"+{int(delay)}"], capture_output=True, timeout=5)
            return f"Shutdown scheduled in {delay}s"
        elif system == "Linux":
            subprocess.run(["shutdown", "-h", f"+{int(delay)}"], capture_output=True, timeout=5)
            return f"Shutdown scheduled in {delay}s"
    except Exception as e:
        return f"Error: Shutdown failed: {e}"


def power_restart(delay: int = 0):
    """Restart system after delay seconds."""
    system = platform.system()
    try:
        if system == "Windows":
            subprocess.run(["shutdown", "/r", "/t", str(int(delay))], capture_output=True, timeout=5)
            return f"Restart scheduled in {delay}s"
        elif system == "Darwin":
            subprocess.run(["sudo", "shutdown", "-r", f"+{int(delay)}"], capture_output=True, timeout=5)
            return f"Restart scheduled in {delay}s"
        elif system == "Linux":
            subprocess.run(["shutdown", "-r", f"+{int(delay)}"], capture_output=True, timeout=5)
            return f"Restart scheduled in {delay}s"
    except Exception as e:
        return f"Error: Restart failed: {e}"


def power_lock():
    """Lock workstation."""
    system = platform.system()
    try:
        if system == "Windows":
            subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"], capture_output=True, timeout=5)
        elif system == "Darwin":
            subprocess.run(["/System/Library/CoreServices/Menu Extras/User.menu/Contents/Resources/CGSession", "-suspend"],
                           capture_output=True, timeout=5)
        elif system == "Linux":
            subprocess.run(["gnome-screensaver-command", "-l"], capture_output=True, timeout=5)
            subprocess.run(["xdg-screensaver", "lock"], capture_output=True, timeout=5)
    except Exception as e:
        return f"Error: Lock failed: {e}"


def power_logoff():
    """Log off current user."""
    system = platform.system()
    try:
        if system == "Windows":
            subprocess.run(["shutdown", "/l"], capture_output=True, timeout=5)
        elif system == "Darwin":
            subprocess.run(["osascript", "-e", 'tell application "System Events" to log out'],
                           capture_output=True, timeout=5)
        elif system == "Linux":
            subprocess.run(["gnome-session-quit", "--logout", "--no-prompt"],
                           capture_output=True, timeout=5)
    except Exception as e:
        return f"Error: Logoff failed: {e}"


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Screen & Display
# ═══════════════════════════════════════════════════════════════════════════════

def screen_resolution() -> dict:
    """Get screen resolution."""
    if _HAS_PYAUTOGUI:
        w, h = _pyautogui.size()
        return {"width": w, "height": h}
    if _HAS_PIL:
        img = _ImageGrab.grab()
        return {"width": img.width, "height": img.height}
    # Fallback to platform-specific methods
    system = platform.system()
    if system == "Windows":
        try:
            import ctypes
            user32 = ctypes.windll.user32
            return {"width": user32.GetSystemMetrics(0), "height": user32.GetSystemMetrics(1)}
        except Exception:
            pass
        try:
            out, _ = _run_pwsh("Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Screen]::PrimaryScreen.Bounds | ConvertTo-Json -Compress")
            if out:
                data = json.loads(out)
                return {"width": data.get("Width"), "height": data.get("Height")}
        except Exception:
            pass
    elif system in ("Darwin", "Linux"):
        try:
            r = subprocess.run(["xdpyinfo"], capture_output=True, text=True, timeout=5)
            m = re.search(r"dimensions:\s+(\d+)x(\d+)", r.stdout)
            if m:
                return {"width": int(m.group(1)), "height": int(m.group(2))}
        except Exception:
            pass
    return {"width": None, "height": None}


def screen_capture(filepath: str = None) -> str:
    """Capture screenshot. Returns path to saved image or error message."""
    if not filepath:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = str(Path.home() / "Pictures" / f"screenshot_{ts}.png")

    try:
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    if _HAS_PYAUTOGUI:
        try:
            img = _pyautogui.screenshot()
            img.save(filepath)
            return filepath
        except Exception as e:
            return f"Error: pyautogui screenshot failed: {e}"

    if _HAS_PIL:
        try:
            img = _ImageGrab.grab()
            img.save(filepath)
            return filepath
        except Exception as e:
            return f"Error: PIL screenshot failed: {e}"

    # Fallback: platform-specific
    system = platform.system()
    try:
        if system == "Windows":
            # Use PowerShell .NET approach
            script = f"""
Add-Type -AssemblyName System.Windows.Forms
$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bitmap = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.CopyFromScreen($bounds.X, $bounds.Y, 0, 0, $bounds.Size)
$bitmap.Save('{filepath}', [System.Drawing.Imaging.ImageFormat]::Png)
$graphics.Dispose()
$bitmap.Dispose()
"""
            out, err = _run_pwsh(script)
            if Path(filepath).exists():
                return filepath
            return f"Error: PowerShell screenshot failed: {err or 'unknown'}"
        elif system == "Darwin":
            subprocess.run(["screencapture", filepath], capture_output=True, timeout=10)
            if Path(filepath).exists():
                return filepath
        elif system == "Linux":
            subprocess.run(["import", filepath], capture_output=True, timeout=10)
            if Path(filepath).exists():
                return filepath
    except Exception as e:
        return f"Error: Screenshot failed: {e}"

    return "Error: No screenshot method available (install pyautogui or pillow)"


def screen_brightness(level: int = None) -> int:
    """Get or set screen brightness (0-100). Windows specific."""
    system = platform.system()
    if system != "Windows":
        return -1

    if level is not None:
        level = max(0, min(100, level))
        script = f"""
$wmi = Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightnessMethods
if ($wmi) {{
    $wmi[0].WmiSetBrightness(1, {level})
    Write-Output "OK"
}} else {{
    Write-Output "NO_WMI"
}}
"""
        out, _ = _run_pwsh(script)
        return level if "OK" in out else -1

    script = r"""
$wmi = Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightness
if ($wmi) {
    Write-Output $wmi[0].CurrentBrightness
} else {
    Write-Output "-1"
}
"""
    out, _ = _run_pwsh(script)
    try:
        return int(out.strip())
    except (ValueError, TypeError):
        return -1


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Audio Control
# ═══════════════════════════════════════════════════════════════════════════════

def audio_volume(level: int = None) -> int:
    """Get or set system volume (0-100)."""
    system = platform.system()

    if system == "Windows":
        if level is not None:
            level = max(0, min(100, level))
            script = f"""
$obj = New-Object -ComObject "WScript.Shell"
for ($i = 0; $i -lt 50; $i++) {{ $obj.SendKeys([char]174) }}
for ($i = 0; $i -lt [math]::Round($level / 2); $i++) {{ $obj.SendKeys([char]175) }}
Write-Output $level
"""
            out, _ = _run_pwsh(script)
            try:
                return int(out.strip())
            except (ValueError, TypeError):
                pass

            # Alternative via Core Audio API
            alt_script = f"""
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public class AudioHelper {{
    [DllImport("winmm.dll")] public static extern int waveOutSetVolume(IntPtr hwo, uint dwVolume);
    [DllImport("winmm.dll")] public static extern int waveOutGetVolume(IntPtr hwo, out uint dwVolume);
    public static int GetVolume() {{
        uint v; waveOutGetVolume(IntPtr.Zero, out v);
        return (int)(v & 0xFFFF) * 100 / 0xFFFF;
    }}
    public static void SetVolume(int lvl) {{
        uint v = (uint)lvl * 0xFFFF / 100;
        waveOutSetVolume(IntPtr.Zero, v | (v << 16));
    }}
}}
'@
[AudioHelper]::SetVolume({level})
Write-Output ([AudioHelper]::GetVolume())
"""
            out, _ = _run_pwsh(alt_script)
            try:
                return int(out.strip())
            except (ValueError, TypeError):
                return -1

        # Get volume
        script = r"""
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public class AudioHelper {
    [DllImport("winmm.dll")] public static extern int waveOutSetVolume(IntPtr hwo, uint dwVolume);
    [DllImport("winmm.dll")] public static extern int waveOutGetVolume(IntPtr hwo, out uint dwVolume);
    public static int GetVolume() {
        uint v; waveOutGetVolume(IntPtr.Zero, out v);
        return (int)(v & 0xFFFF) * 100 / 0xFFFF;
    }
}
'@
Write-Output ([AudioHelper]::GetVolume())
"""
        out, _ = _run_pwsh(script)
        try:
            return int(out.strip())
        except (ValueError, TypeError):
            return 50

    elif system == "Darwin":
        if level is not None:
            level = max(0, min(100, level))
            osa_vol = level / 100.0
            subprocess.run(["osascript", "-e", f"set volume output volume {level}"],
                           capture_output=True, timeout=5)
        out, _ = subprocess.run(
            ["osascript", "-e", "get volume settings"],
            capture_output=True, text=True, timeout=5,
        )
        m = re.search(r"output volume:(\d+)", out.stdout)
        return int(m.group(1)) if m else 50

    elif system == "Linux":
        try:
            if level is not None:
                level = max(0, min(100, level))
                subprocess.run(["amixer", "set", "Master", f"{level}%"],
                               capture_output=True, timeout=5)
            r = subprocess.run(["amixer", "get", "Master"], capture_output=True, text=True, timeout=5)
            m = re.search(r"(\d+)%", r.stdout)
            if m:
                return int(m.group(1))
        except Exception:
            pass

    return 50


def audio_mute(state: bool = None) -> bool:
    """Get or set mute state."""
    system = platform.system()

    if system == "Windows":
        if state is not None:
            if state:
                _run_pwsh("$obj = New-Object -ComObject 'WScript.Shell'; $obj.SendKeys([char]173)")
            else:
                _run_pwsh("$obj = New-Object -ComObject 'WScript.Shell'; $obj.SendKeys([char]173)")

        # Check mute state via Core Audio API
        script = r"""
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public class AudioMute {
    [DllImport("winmm.dll")] public static extern int waveOutGetVolume(IntPtr hwo, out uint dwVolume);
    public static bool IsMuted() {
        uint v; waveOutGetVolume(IntPtr.Zero, out v);
        return (v & 0xFFFF) == 0;
    }
}
'@
if ([AudioMute]::IsMuted()) { Write-Output "MUTED" } else { Write-Output "UNMUTED" }
"""
        out, _ = _run_pwsh(script)
        return out.strip() == "MUTED"

    elif system == "Darwin":
        if state is not None:
            subprocess.run(
                ["osascript", "-e", f"set volume output muted {(str(state).lower())}"],
                capture_output=True, timeout=5,
            )
        out, _ = subprocess.run(
            ["osascript", "-e", "get volume settings"],
            capture_output=True, text=True, timeout=5,
        )
        return "muted:true" in out.stdout.lower()

    elif system == "Linux":
        try:
            if state is not None:
                flag = "mute" if state else "unmute"
                subprocess.run(["amixer", "set", "Master", flag], capture_output=True, timeout=5)
            r = subprocess.run(["amixer", "get", "Master"], capture_output=True, text=True, timeout=5)
            return "[off]" in r.stdout or "0%" in r.stdout.split("[")[1] if "[" in r.stdout else False
        except Exception:
            pass

    return False


def audio_play(filepath: str) -> str:
    """Play an audio file."""
    if not filepath or not Path(filepath).exists():
        return f"Error: File not found: {filepath}"

    system = platform.system()
    try:
        if system == "Windows":
            subprocess.Popen(["powershell", "-c",
                              f"(New-Object Media.SoundPlayer '{filepath}').PlaySync()"],
                             capture_output=True)
            return f"Playing: {filepath}"
        elif system == "Darwin":
            subprocess.Popen(["afplay", filepath])
            return f"Playing: {filepath}"
        elif system == "Linux":
            subprocess.Popen(["aplay", filepath])
            return f"Playing: {filepath}"
    except Exception as e:
        return f"Error: Could not play audio: {e}"


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Clipboard
# ═══════════════════════════════════════════════════════════════════════════════

def clipboard_get() -> str:
    """Get clipboard contents."""
    system = platform.system()
    try:
        if system == "Windows":
            out, _ = _run_pwsh("Get-Clipboard")
            return out if out else ""
        elif system == "Darwin":
            r = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=5)
            return r.stdout
        elif system == "Linux":
            r = subprocess.run(["xclip", "-o", "-selection", "clipboard"],
                               capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                return r.stdout
            r = subprocess.run(["xsel", "-o", "-b"], capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                return r.stdout
    except Exception as e:
        return f"Error: Clipboard read failed: {e}"


def clipboard_set(text: str) -> bool:
    """Set clipboard contents."""
    if not text:
        return False
    system = platform.system()
    try:
        if system == "Windows":
            # Escape single quotes for PowerShell
            safe = text.replace("'", "''")
            out, _ = _run_pwsh(f"Set-Clipboard -Value '{safe}'")
            return True
        elif system == "Darwin":
            p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
            p.communicate(text.encode("utf-8"))
            return True
        elif system == "Linux":
            p = subprocess.Popen(["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE)
            p.communicate(text.encode("utf-8"))
            return True
    except Exception:
        pass
    return False


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Notifications
# ═══════════════════════════════════════════════════════════════════════════════

def notify(title: str, message: str, duration: int = 5) -> bool:
    """Show a desktop notification."""
    system = platform.system()
    try:
        if system == "Windows":
            safe_title = title.replace("'", "''")
            safe_msg = message.replace("'", "''")
            script = f"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
$template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$textNodes = $template.GetElementsByTagName("text")
$textNodes.Item(0).AppendChild($template.CreateTextNode('{safe_title}')) > $null
$textNodes.Item(1).AppendChild($template.CreateTextNode('{safe_msg}')) > $null
$toast = [Windows.UI.Notifications.ToastNotification]::new($template)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier().Show($toast)
"""
            out, err = _run_pwsh(script)
            if not err or "succeeded" in err.lower():
                return True

            # Fallback: legacy PowerShell toast
            fallback = f"""
Add-Type -AssemblyName System.Windows.Forms
$notify = New-Object System.Windows.Forms.NotifyIcon
$notify.Icon = [System.Drawing.SystemIcons]::Information
$notify.BalloonTipTitle = '{safe_title}'
$notify.BalloonTipText = '{safe_msg}'
$notify.Visible = $true
$notify.ShowBalloonTip({duration * 1000})
Start-Sleep -Seconds {duration}
$notify.Dispose()
"""
            out, _ = _run_pwsh(fallback)
            return True

        elif system == "Darwin":
            script = f'display notification "{message}" with title "{title}"'
            subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)
            return True

        elif system == "Linux":
            subprocess.run(["notify-send", title, message, f"-t", str(duration * 1000)],
                           capture_output=True, timeout=5)
            return True

    except Exception:
        pass
    return False


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Network Discovery & Connections
# ═══════════════════════════════════════════════════════════════════════════════

def net_connections() -> list[dict]:
    """List all network connections."""
    _check_psutil()
    results = []
    try:
        for conn in psutil.net_connections():
            results.append({
                "pid": conn.pid,
                "fd": conn.fd,
                "family": str(conn.family),
                "type": str(conn.type),
                "local_addr": f"{conn.laddr.ip}:{conn.laddr.port}" if conn.laddr else None,
                "remote_addr": f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else None,
                "status": conn.status,
            })
    except (psutil.AccessDenied, psutil.Error):
        pass
    return results


def net_listen_ports() -> list[dict]:
    """List listening ports."""
    _check_psutil()
    results = []
    try:
        for conn in psutil.net_connections(kind="listen"):
            proc_name = None
            if conn.pid:
                try:
                    proc_name = psutil.Process(conn.pid).name()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            family = "IPv4" if conn.family == socket.AF_INET else "IPv6" if conn.family == socket.AF_INET6 else str(conn.family)
            proto = "TCP" if conn.type == socket.SOCK_STREAM else "UDP" if conn.type == socket.SOCK_DGRAM else str(conn.type)
            results.append({
                "port": conn.laddr.port if conn.laddr else None,
                "address": conn.laddr.ip if conn.laddr else "*",
                "pid": conn.pid,
                "process": proc_name,
                "protocol": proto,
                "family": family,
            })
    except (psutil.AccessDenied, psutil.Error):
        pass
    return results


def net_bandwidth() -> dict:
    """Current network bandwidth usage (bytes/sec sent/recv)."""
    _check_psutil()
    # Sample twice with a 1s interval
    before = psutil.net_io_counters()
    time.sleep(1)
    after = psutil.net_io_counters()
    return {
        "bytes_sent_per_sec": after.bytes_sent - before.bytes_sent,
        "bytes_recv_per_sec": after.bytes_recv - before.bytes_recv,
        "packets_sent_per_sec": after.packets_sent - before.packets_sent,
        "packets_recv_per_sec": after.packets_recv - before.packets_recv,
        "bytes_sent_per_sec_human": _fmt_bytes(after.bytes_sent - before.bytes_sent) + "/s",
        "bytes_recv_per_sec_human": _fmt_bytes(after.bytes_recv - before.bytes_recv) + "/s",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 11. Keyboard Automation
# ═══════════════════════════════════════════════════════════════════════════════

def keyboard_type(text: str, interval: float = 0.05) -> bool:
    """Type text (simulate keyboard). Uses pyautogui if available."""
    if _HAS_PYAUTOGUI:
        try:
            _pyautogui.typewrite(text, interval=interval)
            return True
        except Exception:
            pass

    # Fallback: platform-specific
    system = platform.system()
    try:
        if system == "Windows":
            # Escape single quotes
            safe = text.replace("'", "''")
            script = f"""
$wshell = New-Object -ComObject WScript.Shell
$wshell.SendKeys('{safe}')
"""
            _run_pwsh(script)
            return True
        elif system == "Darwin":
            script = f"""
tell application "System Events"
    keystroke "{text}"
end tell
"""
            subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)
            return True
        elif system == "Linux":
            subprocess.run(["xdotool", "type", text], capture_output=True, timeout=5)
            return True
    except Exception:
        pass
    return False


def keyboard_hotkey(*keys) -> bool:
    """Simulate a hotkey combination, e.g. keyboard_hotkey('ctrl', 'c')."""
    if _HAS_PYAUTOGUI:
        try:
            _pyautogui.hotkey(*keys)
            return True
        except Exception:
            pass

    system = platform.system()
    try:
        if system == "Windows":
            # Convert keys to SendKeys format
            key_map = {
                "ctrl": "^", "alt": "%", "shift": "+", "win": "#",
                "enter": "{ENTER}", "tab": "{TAB}", "esc": "{ESC}",
                "backspace": "{BACKSPACE}", "delete": "{DELETE}",
                "up": "{UP}", "down": "{DOWN}", "left": "{LEFT}", "right": "{RIGHT}",
                "home": "{HOME}", "end": "{END}", "pgup": "{PGUP}", "pgdn": "{PGDN}",
                "f1": "{F1}", "f2": "{F2}", "f3": "{F3}", "f4": "{F4}",
                "f5": "{F5}", "f6": "{F6}", "f7": "{F7}", "f8": "{F8}",
                "f9": "{F9}", "f10": "{F10}", "f11": "{F11}", "f12": "{F12}",
            }
            combo = ""
            for k in keys:
                k2 = k.lower()
                if k2 in key_map:
                    combo += key_map[k2]
                elif len(k) == 1:
                    combo += k
                else:
                    combo += "{" + k.upper() + "}"
            script = f"""
$wshell = New-Object -ComObject WScript.Shell
$wshell.SendKeys('{combo}')
"""
            _run_pwsh(script)
            return True
        elif system == "Darwin":
            # Convert to osascript format
            key_map = {
                "ctrl": "command down", "alt": "option down", "shift": "shift down",
                "cmd": "command down", "command": "command down",
                "option": "option down",
            }
            modifiers = []
            main_key = None
            for k in keys:
                k2 = k.lower()
                if k2 in key_map or k2 in ("command down", "option down", "shift down", "control down"):
                    if k2 in key_map:
                        modifiers.append(key_map[k2])
                    else:
                        modifiers.append(k2)
                else:
                    main_key = k
            mod_str = ", ".join(modifiers)
            parts = []
            if mod_str:
                parts.append(f"using {{{mod_str}}}")
            if main_key:
                parts.append(f"keystroke \"{main_key}\"")
            if not parts:
                return False
            script = f"tell application \"System Events\"\n    {chr(10).join(parts)}\nend tell"
            subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)
            return True
        elif system == "Linux":
            combo = "+".join(keys)
            subprocess.run(["xdotool", "key", combo], capture_output=True, timeout=5)
            return True
    except Exception:
        pass
    return False


# ═══════════════════════════════════════════════════════════════════════════════
# 12. Command Registration
# ═══════════════════════════════════════════════════════════════════════════════

_registered = False


def register_commands():
    global _registered
    if _registered:
        return
    _registered = True
    from skills import _COMMANDS, _ALIAS_MAP

    # ── System Info ──────────────────────────────────────────────────────────

    def _cmd_sys(args, assistant):
        try:
            info = sys_info()
            lines = [
                "System Information",
                f"  OS:      {info['os']['system']} {info['os']['release']}",
                f"  Host:    {info['hostname']}",
                f"  CPU:     {info['hardware']['cpu_count_physical']} phys / {info['hardware']['cpu_count_logical']} logical cores",
                f"  Arch:    {info['hardware']['architecture']}",
                f"  Uptime:  {info['uptime_human']}",
                f"  Python:  {info['python_version'].split()[0]}",
            ]
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    def _cmd_cpu(args, assistant):
        try:
            cpu = sys_cpu()
            lines = [
                f"CPU Usage: {cpu['percent']}% overall",
            ]
            freq = cpu.get("frequency_current_mhz")
            if freq:
                lines.append(f"Frequency: {freq:.0f} MHz / Max: {cpu.get('frequency_max_mhz', '?')} MHz")
            lines.append(f"Cores: {cpu['count_physical']} physical, {cpu['count_logical']} logical")
            per = cpu.get("per_core", [])
            if per:
                cores_str = ", ".join(f"{p}%" for p in per)
                lines.append(f"Per-core: [{cores_str}]")
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    def _cmd_memory(args, assistant):
        try:
            mem = sys_memory()
            lines = [
                f"Memory: {mem['used_human']} / {mem['total_human']} ({mem['percent']}%)",
                f"Available: {mem['available_human']}",
                f"Swap: {mem['swap_used_human']} / {mem['swap_total_human']} ({mem['swap_percent']}%)",
            ]
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    def _cmd_disk(args, assistant):
        try:
            disks = sys_disk()
            if not disks:
                return "No disk partitions found."
            lines = ["Disk Usage:"]
            for d in disks:
                lines.append(
                    f"  {d['device']:20s} {d['mountpoint']:10s} "
                    f"{d['used_human']:>8s} / {d['total_human']:>8s} "
                    f"({d['percent']}%)  {d['fstype']}"
                )
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    def _cmd_battery(args, assistant):
        try:
            bat = sys_battery()
            if not bat.get("available"):
                return f"Battery: {bat.get('error', 'Not available')}"
            lines = [
                f"Battery: {bat['percent']:.0f}%",
                f"Plugged: {bat['power_plugged']}",
                f"Time left: {bat.get('time_left_human', 'N/A')}",
            ]
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    # ── Process Management ──────────────────────────────────────────────────

    def _cmd_ps(args, assistant):
        sort_by = "cpu"
        limit = 20
        if args:
            parts = args.strip().split()
            if parts[0] in ("cpu", "memory", "mem", "name", "pid"):
                sort_by = parts[0]
                if sort_by == "mem":
                    sort_by = "memory"
            if len(parts) > 1:
                try:
                    limit = int(parts[1])
                except ValueError:
                    pass
        try:
            procs = process_list(sort_by=sort_by, limit=limit)
            if not procs:
                return "No processes found."
            lines = [f"{'PID':>6s} {'CPU%':>6s} {'MEM%':>6s} {'Status':>10s}  Name"]
            for p in procs:
                lines.append(
                    f"{p['pid']:>6d} {p['cpu_percent']:>5.1f}% "
                    f"{p['memory_percent']:>5.1f}% "
                    f"{p['status']:>10s}  {p['name']}"
                )
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    def _cmd_kill(args, assistant):
        if not args:
            return "Usage: /kill <pid> [force]"
        parts = args.strip().split()
        try:
            pid = int(parts[0])
        except ValueError:
            return f"Error: Invalid PID '{parts[0]}'"
        force = len(parts) > 1 and parts[1].lower() in ("force", "-f", "--force", "f")
        return process_kill(pid, force=force)

    # ── Window Management ───────────────────────────────────────────────────

    def _cmd_windows(args, assistant):
        try:
            wins = window_list()
            if not wins:
                return "No visible windows found."
            lines = [f"{'PID':>6s}  Window Title"]
            for w in wins:
                title = (w.get("title") or "").strip()
                lines.append(f"{w.get('pid') or '?':>6}  {title}")
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    def _cmd_focus(args, assistant):
        if not args:
            return "Usage: /focus <window title or PID>"
        target = args.strip()
        try:
            pid = int(target)
        except ValueError:
            pid = target
        if window_focus(pid):
            return f"Focused window: {target}"
        return f"Error: Could not find/focus window: {target}"

    # ── Application Launching ───────────────────────────────────────────────

    def _cmd_launch(args, assistant):
        if not args:
            return "Usage: /launch <app_name_or_path> [args...]"
        parts = args.strip().split(maxsplit=1)
        app = parts[0]
        app_args = parts[1] if len(parts) > 1 else ""
        return app_launch(app, app_args)

    # ── Power Management ────────────────────────────────────────────────────

    def _cmd_shutdown(args, assistant):
        assistant.say("Are you sure you want to SHUT DOWN the computer? Type 'yes' to confirm.")
        resp = assistant.input("Shutdown confirmation")
        if resp and resp.strip().lower() == "yes":
            delay = 0
            if args:
                try:
                    delay = int(args.strip())
                except ValueError:
                    pass
            result = power_shutdown(delay)
            return f"Shutdown: {result}"
        return "Shutdown cancelled."

    def _cmd_restart(args, assistant):
        assistant.say("Are you sure you want to RESTART the computer? Type 'yes' to confirm.")
        resp = assistant.input("Restart confirmation")
        if resp and resp.strip().lower() == "yes":
            delay = 0
            if args:
                try:
                    delay = int(args.strip())
                except ValueError:
                    pass
            result = power_restart(delay)
            return f"Restart: {result}"
        return "Restart cancelled."

    def _cmd_sleep(args, assistant):
        assistant.say("Sleeping computer...")
        power_sleep()
        return "Computer is going to sleep."

    def _cmd_lock(args, assistant):
        power_lock()
        return "Workstation locked."

    # ── Screenshot ──────────────────────────────────────────────────────────

    def _cmd_screenshot(args, assistant):
        filepath = args.strip() if args else None
        result = screen_capture(filepath)
        if result.startswith("Error:"):
            return result
        return f"Screenshot saved: {result}"

    # ── Audio ───────────────────────────────────────────────────────────────

    def _cmd_volume(args, assistant):
        if args:
            try:
                level = int(args.strip())
                level = max(0, min(100, level))
                actual = audio_volume(level)
                return f"Volume set to {actual}%"
            except ValueError:
                return "Usage: /volume [0-100]"
        vol = audio_volume()
        return f"Volume: {vol}%"

    def _cmd_mute(args, assistant):
        if args:
            state = args.strip().lower() in ("on", "true", "1", "yes", "mute")
            audio_mute(state)
            return f"Mute: {'on' if state else 'off'}"
        muted = audio_mute()
        return f"Mute: {'on' if muted else 'off'}"

    # ── Notifications ───────────────────────────────────────────────────────

    def _cmd_notify(args, assistant):
        if not args:
            return "Usage: /notify <title> | <message>"
        parts = args.split("|", 1)
        title = parts[0].strip()
        message = parts[1].strip() if len(parts) > 1 else ""
        if notify(title, message):
            return f"Notification sent: {title}"
        return "Error: Could not send notification"

    # ── Clipboard ───────────────────────────────────────────────────────────

    def _cmd_clipboard(args, assistant):
        if args:
            if clipboard_set(args):
                return f"Clipboard set ({len(args)} chars)"
            return "Error: Could not set clipboard"
        content = clipboard_get()
        if content.startswith("Error:"):
            return content
        if not content:
            return "Clipboard is empty"
        return f"Clipboard ({len(content)} chars):\n{content[:500]}"

    # ── Register All Commands ───────────────────────────────────────────────

    commands = [
        ("sys", _cmd_sys, ["system"], "System overview (CPU, RAM, disk, network, battery)"),
        ("cpu", _cmd_cpu, [], "CPU usage details"),
        ("memory", _cmd_memory, ["mem", "ram"], "Memory usage"),
        ("disk", _cmd_disk, [], "Disk usage per partition"),
        ("battery", _cmd_battery, ["bat", "power"], "Battery status"),
        ("ps", _cmd_ps, ["processes", "tasks"], "List top processes"),
        ("kill", _cmd_kill, [], "Kill a process by PID"),
        ("windows", _cmd_windows, ["wins", "winlist"], "List open windows"),
        ("focus", _cmd_focus, ["winfocus", "activate"], "Focus a window"),
        ("launch", _cmd_launch, ["run", "open-app"], "Launch an application"),
        ("shutdown", _cmd_shutdown, [], "Shutdown computer (with confirm)"),
        ("restart", _cmd_restart, [], "Restart computer (with confirm)"),
        ("sleep", _cmd_sleep, [], "Sleep computer"),
        ("lock", _cmd_lock, [], "Lock workstation"),
        ("screenshot", _cmd_screenshot, ["scrot", "capture"], "Take a screenshot"),
        ("volume", _cmd_volume, ["vol"], "Get/set volume"),
        ("mute", _cmd_mute, [], "Get/set mute"),
        ("notify", _cmd_notify, ["notice", "alert"], "Show desktop notification"),
        ("clipboard", _cmd_clipboard, ["clip"], "Get/set clipboard"),
    ]

    for name, handler, aliases, help_text in commands:
        _COMMANDS[name] = {"handler": handler, "help": help_text, "aliases": aliases, "name": name}
        for alias in aliases:
            _ALIAS_MAP[alias] = name


# Auto-register when this module is imported by load_skills()
register_commands()
