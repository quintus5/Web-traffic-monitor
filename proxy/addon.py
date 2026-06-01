"""
mitmproxy addon for web traffic monitoring.

Run via:
    mitmdump --scripts proxy/addon.py --listen-port 8080

Or via run.py which manages both this and the FastAPI process.
"""
import sys
import os
import logging
from datetime import datetime
from queue import Queue

# Ensure project root is on path when loaded by mitmproxy
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import settings
from proxy.writer import DatabaseWriter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s %(message)s")
logger = logging.getLogger("proxy.addon")

_queue: Queue = Queue()
_writer: DatabaseWriter = None


class TrafficMonitorAddon:
    def __init__(self):
        global _writer
        _writer = DatabaseWriter(
            queue=_queue,
            db_url=settings.DATABASE_URL,
            batch_size=settings.WRITER_BATCH_SIZE,
            flush_interval=settings.WRITER_FLUSH_INTERVAL,
        )
        _writer.start()
        logger.info("TrafficMonitor addon loaded. Writing to %s", settings.DATABASE_URL)

    def request(self, flow):
        """Called for every intercepted request."""
        try:
            host = flow.request.pretty_host
            # Skip the monitoring dashboard itself
            if host in ("localhost", "127.0.0.1") and flow.request.port == settings.API_PORT:
                return

            _queue.put({
                "timestamp": datetime.utcnow(),
                "src_ip": flow.client_conn.peername[0] if flow.client_conn.peername else "0.0.0.0",
                "domain": host,
                "url": flow.request.pretty_url if flow.request.scheme == "http" else None,
                "method": flow.request.method,
                "protocol": flow.request.scheme or "https",
                "status_code": None,
                "bytes_sent": len(flow.request.content or b""),
                "bytes_received": 0,
            })
        except Exception as e:
            logger.debug("request hook error: %s", e)

    def response(self, flow):
        """Update bytes_received from the response (best-effort)."""
        try:
            if flow.response:
                _queue.put({
                    "_update": True,
                    "src_ip": flow.client_conn.peername[0] if flow.client_conn.peername else "0.0.0.0",
                    "domain": flow.request.pretty_host,
                    "timestamp": datetime.utcnow(),
                    "status_code": flow.response.status_code,
                    "bytes_received": len(flow.response.content or b""),
                })
        except Exception as e:
            logger.debug("response hook error: %s", e)

    def done(self):
        """Called when mitmproxy shuts down."""
        global _writer
        if _writer:
            _writer.stop()
            _writer.join(timeout=5)
        logger.info("TrafficMonitor addon unloaded")


addons = [TrafficMonitorAddon()]
