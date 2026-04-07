import json
import logging
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from functools import partial

logger = logging.getLogger(__name__)

_REQUIRED_FIELDS = [
    "session_pct", "session_reset",
    "week_all_pct", "week_all_reset",
    "week_sonnet_pct", "week_sonnet_reset",
    "extra_spent", "extra_limit",
]


def _make_handler(state, lock, token):
    """Create a request handler class with access to shared state."""

    class UsageHandler(BaseHTTPRequestHandler):

        def log_message(self, format, *args):
            logger.debug(format, *args)

        def do_POST(self):
            if self.path != "/usage":
                self.send_error(404)
                return

            # Check auth token
            auth = self.headers.get("Authorization", "")
            if auth != f"Bearer {token}":
                self.send_error(401, "Invalid token")
                return

            # Read body
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length == 0:
                self.send_error(400, "Empty body")
                return

            try:
                body = self.rfile.read(content_length)
                data = json.loads(body)
            except (json.JSONDecodeError, ValueError) as e:
                self.send_error(400, f"Invalid JSON: {e}")
                return

            # Validate required fields
            missing = [f for f in _REQUIRED_FIELDS if f not in data]
            if missing:
                self.send_error(400, f"Missing fields: {', '.join(missing)}")
                return

            # Update shared state
            with lock:
                state["subscription"] = {
                    "session_pct": int(data["session_pct"]),
                    "session_reset": str(data["session_reset"]),
                    "week_all_pct": int(data["week_all_pct"]),
                    "week_all_reset": str(data["week_all_reset"]),
                    "week_sonnet_pct": int(data["week_sonnet_pct"]),
                    "week_sonnet_reset": str(data["week_sonnet_reset"]),
                    "extra_spent": float(data["extra_spent"]),
                    "extra_limit": float(data["extra_limit"]),
                }
                state["last_updated"] = datetime.now().isoformat()

            logger.info("Subscription usage updated via push")

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode())

        def do_GET(self):
            if self.path != "/health":
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "healthy"}).encode())

    return UsageHandler


class ReceiverThread(threading.Thread):
    """Background thread running an HTTP server to receive subscription data."""

    def __init__(self, config: dict, state: dict, lock: threading.Lock):
        super().__init__(name="receiver", daemon=True)
        port = config["receiver"]["port"]
        token = config["receiver"]["token"]
        handler = _make_handler(state, lock, token)
        self.server = HTTPServer(("0.0.0.0", port), handler)
        self.port = port

    def run(self):
        logger.info(f"Usage receiver listening on port {self.port}")
        self.server.serve_forever()

    def stop(self):
        self.server.shutdown()
