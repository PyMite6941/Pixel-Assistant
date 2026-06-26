"""
Pixel Assistant — unified launcher.

Modes:
  terminal      CLI mode (original Rich terminal UI)
  tui           Textual TUI (modern multi-domain terminal UI)
  api           FastAPI web server only
  full          API + frontend dev server (default)
  build         Build frontend then start API
  dev           API + frontend hot-reload (for development)
  dashboard     Streamlit system vitals dashboard with LLM insights

Usage:
  python run.py [mode] [--port PORT] [--host HOST] [--no-browser]
  python run.py terminal
  python run.py tui
  python run.py api --port 8080
  python run.py full --no-browser
  python run.py dashboard
"""
import os
import re
import sys
import subprocess
import argparse
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
SRC = ROOT / "src"
FRONTEND = ROOT / "frontend"


def fix_encoding():
    if sys.platform == "win32":
        import io
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )
        sys.stderr = io.TextIOWrapper(
            sys.stderr.buffer, encoding="utf-8", errors="replace"
        )


def print_header(mode: str, host: str, port: int, extra: str = ""):
    fix_encoding()
    ip = _get_local_ip()
    dashes = "=" * 58
    print()
    print(f"  {dashes}")
    print(f"    Pixel Assistant  —  mode: {mode}")
    print(f"  {dashes}")
    print(f"    Local:   http://{host}:{port}")
    if ip:
        print(f"    Network: http://{ip}:{port}")
    if extra:
        print(f"    {extra}")
    print(f"  {dashes}")
    print()


def _get_local_ip() -> str:
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return ""


def _check_deps():
    missing = []
    try:
        import uvicorn  # noqa
    except ImportError:
        missing.append("uvicorn")
    try:
        import fastapi  # noqa
    except ImportError:
        missing.append("fastapi")
    if missing:
        print(f"  Missing dependencies: {', '.join(missing)}")
        print(f"  Install: pip install {' '.join(missing)}")
        return False
    return True


def cmd_terminal():
    """Launch the CLI terminal UI."""
    sys.path.insert(0, str(SRC))
    fix_encoding()
    from core_files.config import Config
    from main import PixelAssistant
    cfg = Config()
    bot = PixelAssistant(provider=cfg.provider)
    bot.run_text()


def cmd_tui():
    """Launch the Textual TUI."""
    sys.path.insert(0, str(SRC))
    fix_encoding()

    # Auto-clean cache dirs on launch
    _clean_pycache(SRC)
    _clean_pycache(ROOT / "tests")

    from skills import load_skills
    load_skills()
    from core_files.tui_app import run_tui
    run_tui()


def _clean_pycache(directory: Path):
    """Recursively remove __pycache__ directories."""
    import shutil
    for p in list(directory.rglob("__pycache__")):
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
    for p in list(directory.rglob("*.pyc")):
        if p.is_file():
            try:
                p.unlink()
            except Exception:
                pass
    for p in list(directory.rglob("*.pyo")):
        if p.is_file():
            try:
                p.unlink()
            except Exception:
                pass


def cmd_api(host: str, port: int, no_browser: bool):
    """Start the FastAPI server only."""
    if not _check_deps():
        sys.exit(1)
    if not no_browser:
        _try_open(f"http://{host}:{port}")
    print_header("api", host, port)
    os.chdir(str(ROOT))
    import uvicorn
    uvicorn.run("src.api.app:app", host=host, port=port, reload=True)


def cmd_build(host: str, port: int, no_browser: bool):
    """Build frontend then start API."""
    _build_frontend()
    cmd_api(host, port, no_browser)


def cmd_full(host: str, port: int, no_browser: bool):
    """Build + start API (no frontend dev server)."""
    cmd_build(host, port, no_browser)


def cmd_dev(host: str, port: int, no_browser: bool, api_port: int = 8000):
    """Start frontend dev server (proxies to API)."""
    _check_frontend_deps()
    if not no_browser:
        _try_open(f"http://{host}:{port}")
    print_header("dev", host, port, f"API proxy → http://{host}:{api_port}")
    env = os.environ.copy()
    proc = subprocess.Popen(
        ["npx", "vite", "--host", host, "--port", str(port)],
        cwd=str(FRONTEND),
        env=env,
    )
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()


def _build_frontend():
    _check_frontend_deps()
    print("  Building frontend...")
    res = subprocess.run(
        ["npm", "run", "build"],
        cwd=str(FRONTEND),
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        print(res.stdout)
        print(res.stderr)
        print("  Frontend build failed.")
        sys.exit(1)
    print("  Frontend built successfully.")


def _check_frontend_deps():
    node_modules = FRONTEND / "node_modules"
    if not node_modules.is_dir():
        print("  Installing frontend dependencies...")
        res = subprocess.run(
            ["npm", "install"],
            cwd=str(FRONTEND),
            capture_output=True,
            text=True,
        )
        if res.returncode != 0:
            print(res.stdout)
            print(res.stderr)
            print("  npm install failed.")
            sys.exit(1)


def cmd_dashboard(host: str, port: int, no_browser: bool):
    """Launch Streamlit dashboard."""
    try:
        import streamlit  # noqa
    except ImportError:
        print("  Streamlit not installed. Run: pip install streamlit plotly")
        sys.exit(1)
    print_header("dashboard", host, port)
    if not no_browser:
        _try_open(f"http://{host}:{port}")
    # Streamlit needs --server.port and --server.address
    os.chdir(str(ROOT))
    subprocess.run([
        sys.executable, "-m", "streamlit", "run", "dashboard.py",
        "--server.port", str(port),
        "--server.address", host,
    ])


def _try_open(url: str):
    import webbrowser
    try:
        webbrowser.open(url)
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser(
        description="Pixel Assistant launcher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "mode",
        nargs="?",
        default="api",
        choices=["terminal", "tui", "api", "full", "build", "dev", "dashboard"],
        help="Run mode (default: api)",
    )
    parser.add_argument("--port", "-p", type=int, default=8000, help="API port")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Bind host")
    parser.add_argument(
        "--api-port", type=int, default=8000,
        help="API port for dev mode (default: 8000)",
    )
    parser.add_argument(
        "--no-browser", action="store_true", help="Don't open browser"
    )

    args = parser.parse_args()

    if args.mode == "terminal":
        cmd_terminal()
    elif args.mode == "tui":
        cmd_tui()
    elif args.mode == "api":
        cmd_api(args.host, args.port, args.no_browser)
    elif args.mode in ("full", "build"):
        cmd_build(args.host, args.port, args.no_browser)
    elif args.mode == "dev":
        cmd_dev(args.host, args.port, args.no_browser, args.api_port)
    elif args.mode == "dashboard":
        cmd_dashboard(args.host, args.port, args.no_browser)


if __name__ == "__main__":
    main()
