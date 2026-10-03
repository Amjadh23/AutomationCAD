import http.client
import json
import socket
import threading

import pytest

from shipdraw.web.api import DrawingService
from shipdraw.web.form import DEFAULT_VALUES
from shipdraw.web.server import create_server


@pytest.fixture
def server(standard, shipped_profiles):
    srv = create_server(DrawingService(standard, shipped_profiles), port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv
    srv.shutdown()
    srv.server_close()


def call(server, method, path, body=None, raw=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=60)
    payload = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    conn.request(method, path, body=payload, headers={"Content-Type": "application/json", **(headers or {})})
    response = conn.getresponse()
    data = response.read()
    conn.close()
    return response, data


def test_listens_on_this_computer_only(server):
    assert server.server_address[0] == "127.0.0.1"


def test_page_and_assets(server):
    response, data = call(server, "GET", "/")
    assert response.status == 200 and response.getheader("Content-Type").startswith("text/html")
    assert b"<title>" in data
    assert call(server, "GET", "/static/app.js")[0].getheader("Content-Type").startswith("text/javascript")
    assert call(server, "GET", "/static/app.css")[0].status == 200


@pytest.mark.parametrize("path", ["/static/../pyproject.toml", "/static/%2e%2e/pyproject.toml", "/static/nope.js", "/nope"])
def test_nothing_outside_the_static_folder(server, path):
    assert call(server, "GET", path)[0].status == 404


def test_defaults_and_preview(server):
    response, data = call(server, "GET", "/api/defaults")
    assert response.status == 200 and json.loads(data)["values"]["drawing_no"] == "SY-101"
    response, data = call(server, "POST", "/api/preview", body=DEFAULT_VALUES)
    result = json.loads(data)
    assert response.status == 200 and result["status"] == "warning" and result["svg"].startswith("<svg")


def test_export_is_a_download(server):
    response, data = call(server, "POST", "/api/export/dxf", body=DEFAULT_VALUES)
    assert response.status == 200
    assert response.getheader("Content-Disposition") == 'attachment; filename="SY-101.dxf"'
    assert b"SECTION" in data[:40]


def test_refused_export_is_422(server):
    response, data = call(server, "POST", "/api/export/dxf", body={**DEFAULT_VALUES, "at_frame": "35"})
    assert response.status == 422 and "fix the problems" in json.loads(data)["error"]


@pytest.mark.parametrize("raw", [b"[1, 2]", b"not json", b"\xff\xfe"])
def test_body_must_be_a_json_object(server, raw):
    assert call(server, "POST", "/api/preview", raw=raw)[0].status == 400


def test_oversized_body_is_413(server):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=30)
    conn.putrequest("POST", "/api/preview")
    conn.putheader("Content-Length", "10000000")
    conn.endheaders()
    assert conn.getresponse().status == 413
    conn.close()


def test_foreign_host_is_403(server):
    assert call(server, "GET", "/api/defaults", headers={"Host": "evil.example"})[0].status == 403


def test_busy_port_falls_back_to_a_free_one(standard, shipped_profiles):
    blocker = socket.socket()
    blocker.bind(("127.0.0.1", 0))
    blocker.listen()
    busy = blocker.getsockname()[1]
    try:
        srv = create_server(DrawingService(standard, shipped_profiles), port=busy)
        try:
            assert srv.server_address[1] != busy
        finally:
            srv.server_close()
    finally:
        blocker.close()
