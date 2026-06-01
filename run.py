#!/usr/bin/env python3
"""
Launches both the mitmproxy proxy and the FastAPI dashboard in separate processes.

Usage:
    python3 run.py
    python3 run.py --proxy-only
    python3 run.py --api-only
"""
import argparse
import os
import signal
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config.settings import settings


def ensure_data_dir():
    os.makedirs("data", exist_ok=True)
    os.makedirs(settings.MITMPROXY_CA_DIR, exist_ok=True)


def init_database():
    """Initialize DB tables and seed categories before starting proxy."""
    from api.database import init_db
    init_db()
    print("[run] Database initialized")


def start_proxy():
    cmd = [
        sys.executable, "-m", "mitmproxy.tools.main",
        "--scripts", "proxy/addon.py",
        "--listen-port", str(settings.PROXY_PORT),
        "--mode", "regular",
        "--set", f"confdir={settings.MITMPROXY_CA_DIR}",
        "--quiet",
    ]
    print(f"[run] Starting proxy on port {settings.PROXY_PORT}")
    return subprocess.Popen(cmd)


def start_api():
    cmd = [
        sys.executable, "-m", "uvicorn",
        "api.main:app",
        "--host", settings.API_HOST,
        "--port", str(settings.API_PORT),
        "--log-level", "info",
    ]
    print(f"[run] Starting dashboard on http://{settings.API_HOST}:{settings.API_PORT}")
    return subprocess.Popen(cmd)


def main():
    parser = argparse.ArgumentParser(description="Web Traffic Monitor launcher")
    parser.add_argument("--proxy-only", action="store_true")
    parser.add_argument("--api-only", action="store_true")
    args = parser.parse_args()

    ensure_data_dir()
    init_database()

    processes = []

    if not args.api_only:
        processes.append(start_proxy())
        time.sleep(1)  # Let proxy generate CA cert before API starts

    if not args.proxy_only:
        processes.append(start_api())

    print("[run] All services started. Press Ctrl+C to stop.")

    def shutdown(signum, frame):
        print("\n[run] Shutting down…")
        for p in processes:
            p.terminate()
        for p in processes:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Wait for any process to exit unexpectedly
    while True:
        for p in processes:
            if p.poll() is not None:
                print(f"[run] Process {p.pid} exited with code {p.returncode}. Stopping all.")
                shutdown(None, None)
        time.sleep(1)


if __name__ == "__main__":
    main()
