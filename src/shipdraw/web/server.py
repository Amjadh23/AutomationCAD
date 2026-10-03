"""Local web server for the drawing page. It listens on this computer only (127.0.0.1)."""
from __future__ import annotations

import json
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .api import DrawingService, ExportRefused

STATIC_DIR = Path(__file__).resolve().parent / "static"
MAX_BODY_BYTES = 100_000
_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}


class _Server(ThreadingHTTPServer):
    allow_reuse_address = False  # on Windows, address reuse would let two servers share one port
    daemon_threads = True


def make_handler(service: DrawingService) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "shipdraw"

        def log_message(self, format, *args):  # keep the console window quiet
            pass

        def do_GET(self):
            if not self._host_allowed():
                return self._json(HTTPStatus.FORBIDDEN, {"error": "forbidden"})
            path = self.path.split("?", 1)[0]
            if path == "/":
                return self._static("index.html")
            if path.startswith("/static/"):
                return self._static(path[len("/static/"):])
            if path == "/api/defaults":
                return self._json(HTTPStatus.OK, service.defaults())
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

        def do_POST(self):
            if not self._host_allowed():
                return self._json(HTTPStatus.FORBIDDEN, {"error": "forbidden"})
            path = self.path.split("?", 1)[0]
            values = self._read_json()
            if values is None:
                return
            if path == "/api/preview":
                return self._json(HTTPStatus.OK, service.preview(values))
            if path.startswith("/api/export/"):
                try:
                    export = service.export(values, path[len("/api/export/"):])
                except ExportRefused as exc:
                    return self._json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(exc)})
                return self._send(
                    HTTPStatus.OK,
                    export.content_type,
                    export.data,
                    {"Content-Disposition": f'attachment; filename="{export.filename}"'},
                )
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

        def _host_allowed(self) -> bool:
            port = self.server.server_address[1]
            return self.headers.get("Host", "") in {f"127.0.0.1:{port}", f"localhost:{port}"}

        def _read_json(self) -> dict | None:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = -1
            if length < 0 or length > MAX_BODY_BYTES:
                self.close_connection = True
                self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "request too large"})
                return None
            try:
                data = json.loads(self.rfile.read(length) or b"null")
            except (UnicodeDecodeError, json.JSONDecodeError):
                data = None
            if not isinstance(data, dict):
                self._json(HTTPStatus.BAD_REQUEST, {"error": "expected a JSON object"})
                return None
            return data

        def _static(self, name: str) -> None:
            target = (STATIC_DIR / name).resolve()
            if target.parent != STATIC_DIR or target.suffix not in _CONTENT_TYPES or not target.is_file():
                return self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            self._send(HTTPStatus.OK, _CONTENT_TYPES[target.suffix], target.read_bytes(), {"Cache-Control": "no-cache"})

        def _json(self, status: HTTPStatus, payload: dict) -> None:
            self._send(status, "application/json; charset=utf-8", json.dumps(payload).encode("utf-8"))

        def _send(self, status: HTTPStatus, content_type: str, body: bytes, headers: dict | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

    return Handler


def create_server(service: DrawingService, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    handler = make_handler(service)
    try:
        return _Server((host, port), handler)
    except OSError:  # port busy: let the operating system pick a free one
        return _Server((host, 0), handler)


def serve(service: DrawingService, port: int = 8765, open_browser: bool = True) -> None:
    server = create_server(service, port=port)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"Bulkhead drawing tool is running at {url}")
    print("Keep this window open while you use the page. Close it (or press Ctrl+C) to stop.")
    if open_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
