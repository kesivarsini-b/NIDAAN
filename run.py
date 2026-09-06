#!/usr/bin/env python3
"""
run.py
======
One-click launcher for the NIDAAN demo server.

Features:
  - Auto-installs any missing lightweight dependencies.
  - Starts uvicorn on http://127.0.0.1:8000 (auto-picks port if busy).
  - Opens your default browser to the dashboard after boot.
"""
import importlib
import os
import platform
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

HOST = "127.0.0.1"
PORT = int(os.getenv("NIDAAN_PORT", "8000"))
URL = f"http://{HOST}:{PORT}"

LITE_DEPS = [
    ("fastapi", "fastapi>=0.110"),
    ("uvicorn", "uvicorn[standard]>=0.27"),
    ("websockets", "websockets>=12.0"),
    ("numpy", "numpy>=1.26"),
    ("pydantic", "pydantic>=2.6"),
    ("httpx", "httpx>=0.27"),
    ("jinja2", "jinja2>=3.1"),
    ("aiofiles", "aiofiles>=23.2"),
    ("dotenv", "python-dotenv>=1.0"),
    ("scipy", "scipy>=1.11"),
]


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((HOST, port)) == 0


def _find_free_port(start: int) -> int:
    p = start
    while p < start + 50 and _port_in_use(p):
        p += 1
    return p


def ensure_deps():
    missing = []
    for mod_name, pip_spec in LITE_DEPS:
        try:
            importlib.import_module(mod_name)
        except ImportError:
            missing.append(pip_spec)
    if missing:
        print(f"[run] Installing missing deps: {', '.join(missing)}")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-q", *missing],
            stdout=subprocess.DEVNULL,
        )


def open_browser():
    time.sleep(1.8)
    webbrowser.open(URL)


def main():
    ensure_deps()

    port = _find_free_port(PORT)
    if port != PORT:
        global URL
        PORT_USED = port
        URL = f"http://{HOST}:{port}"
        print(f"[run] Port {PORT} busy — using {port}")
    else:
        PORT_USED = PORT

    print(f"[run] NIDAAN server starting on {URL}")
    print(f"[run] Python {platform.python_version()} | Open Ctrl+C to stop")

    t = threading.Thread(target=open_browser, daemon=True)
    t.start()

    import uvicorn
    uvicorn.run(
        "backend.app:app",
        host=HOST,
        port=PORT_USED,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
