"""Serve the packaged workbench and fitting API on the local computer."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from urllib.parse import parse_qs, urlsplit

from .demo import demo_analysis
from .engine import fit_batch
from .export import build_export

_ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/reference-library.json": ("reference-library.json", "application/json; charset=utf-8"),
}
_MAX_REQUEST = 24 * 1024 * 1024


class _Handler(BaseHTTPRequestHandler):
    def _send(self, status, data, content_type, attachment=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data: blob:; "
            "style-src 'self' 'unsafe-inline'; object-src 'none'; frame-ancestors 'none'",
        )
        if attachment:
            self.send_header("Content-Disposition", 'attachment; filename="' + attachment + '"')
        self.end_headers()
        self.wfile.write(data)

    def _json(self, status, data):
        body = json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _reject_post(self, status, message):
        # Consume a bounded request body before closing so the client can read
        # the error response even when headers and body arrive separately.
        try:
            remaining = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            remaining = 0
        if 0 < remaining <= _MAX_REQUEST:
            self.connection.settimeout(5)
            try:
                while remaining:
                    chunk = self.rfile.read(min(remaining, 65536))
                    if not chunk:
                        break
                    remaining -= len(chunk)
            except OSError:
                return
        self._json(status, {"error": message})

    def _local(self):
        port = self.server.server_port
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        origin = self.headers.get("Origin")
        return self.headers.get("Host") in hosts and (
            origin is None or origin in {"http://" + host for host in hosts}
        )

    def do_GET(self):
        if not self._local():
            self._json(403, {"error": "Open the workbench from its local address."})
            return
        route = urlsplit(self.path)
        if route.path in _ASSETS:
            name, content_type = _ASSETS[route.path]
            data = files("lcf_lab").joinpath("web", name).read_bytes()
            self._send(200, data, content_type)
        elif route.path == "/api/demo":
            query = parse_qs(route.query)
            try:
                payload = demo_analysis(query.get("element", ["Fe"])[0], query.get("edge", ["L2,3"])[0])
            except ValueError as error:
                self._json(400, {"error": str(error)})
            else:
                self._json(200, payload)
        else:
            self._json(404, {"error": "Endpoint not found."})

    def do_POST(self):
        if not self._local():
            self._reject_post(403, "Open the workbench from its local address.")
            return
        route = urlsplit(self.path).path
        if route not in {"/api/fit", "/api/export"}:
            self._reject_post(404, "Endpoint not found.")
            return
        if self.headers.get_content_type() != "application/json":
            self._reject_post(415, "Send an application/json request.")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._json(400, {"error": "Invalid request length."})
            return
        if length < 1 or length > _MAX_REQUEST:
            self._json(413, {"error": "Analysis requests must be between 1 byte and 24 MiB."})
            return
        try:
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("An analysis request must be a JSON object.")
            if route == "/api/fit":
                self._json(200, fit_batch(payload))
            else:
                bundle = build_export(payload.get("analysis"), payload.get("result"))
                self._send(200, bundle, "application/zip", "lcf-lab-analysis.zip")
        except (ValueError, KeyError, TypeError) as error:
            self._json(400, {"error": str(error)})

    def log_message(self, format, *args):
        """Keep background browser requests out of the terminal."""


def create_server(port: int = 0) -> ThreadingHTTPServer:
    """Create a loopback-only server. Pass port 0 to choose a free port."""
    return ThreadingHTTPServer(("127.0.0.1", port), _Handler)
