"""Verify the same analysis survives the public entry points and export."""

import csv
import io
import json
import select
from contextlib import contextmanager
from http.client import HTTPConnection
from threading import Thread
from zipfile import ZipFile

import numpy as np
import pytest

from lcf_lab import fit_batch
from lcf_lab.cli import main
from lcf_lab.demo import demo_analysis
from lcf_lab.export import build_export
from lcf_lab.server import create_server


@pytest.mark.parametrize("element,edge", [("Fe", "L2,3"), ("Mn", "L2"), ("Mn", "L3")])
def test_demo_fit_and_export(element, edge):
    analysis = demo_analysis(element, edge)
    result = fit_batch(analysis)
    first = result["results"][0]
    assert first["status"] == "ok"
    assert first["energy_shift"] == pytest.approx(0.12, abs=0.02)
    assert [ref["weight"] for ref in first["weights"]] == pytest.approx([0.36, 0.64, 0], abs=0.02)
    assert np.allclose(first["residual"], np.array(first["observed"]) - first["fitted"])
    with ZipFile(io.BytesIO(build_export(analysis, result))) as archive:
        replay = json.loads(archive.read("analysis.json"))
        summary = list(csv.DictReader(io.StringIO(archive.read("summary.csv").decode("utf-8"))))
        curves = list(csv.DictReader(io.StringIO(archive.read("curves/001_Scan_01.csv").decode("utf-8"))))
        assert replay == analysis
        assert fit_batch(replay) == result
        assert len(summary) == len(analysis["samples"])
        assert len(curves) == len(first["energy"])
        assert json.loads(archive.read("results.json"))["format_version"] == 1


def test_invalid_demo_and_export():
    with pytest.raises(ValueError, match="Fe and Mn"):
        demo_analysis("Cr")
    with pytest.raises(ValueError, match="Synthetic projects cover"):
        demo_analysis("Fe", "L1")
    with pytest.raises(ValueError, match="requires an analysis"):
        build_export({}, {})


def test_export_uses_safe_csv_labels_and_paths():
    analysis = demo_analysis()
    analysis["samples"][0]["label"] = "=1+1"
    analysis["samples"][1]["label"] = "../"
    result = fit_batch(analysis)
    with ZipFile(io.BytesIO(build_export(analysis, result))) as archive:
        assert "002_sample.csv" in {name.split("/")[-1] for name in archive.namelist()}
        summary = list(csv.DictReader(io.StringIO(archive.read("summary.csv").decode("utf-8"))))
        assert summary[0]["sample"] == "'=1+1"
        assert json.loads(archive.read("analysis.json"))["samples"][0]["label"] == "=1+1"


def test_cli_export_and_existing_output(tmp_path, capsys):
    request = tmp_path / "analysis.json"
    output = tmp_path / "results.zip"
    assert main(["example", "Mn", "-o", str(request)]) == 0
    assert main(["fit", str(request), "-o", str(output)]) == 0
    assert main(["fit", str(request), "-o", str(output)]) == 1
    assert "LCF Lab" in capsys.readouterr().err
    with ZipFile(output) as archive:
        assert json.loads(archive.read("analysis.json"))["element"] == "Mn"


def test_cli_opens_local_address_and_handles_stop(monkeypatch):
    opened = []

    class StubServer:
        server_port = 8765

        def serve_forever(self):
            raise KeyboardInterrupt()

    @contextmanager
    def stub(port):
        assert port == 0
        yield StubServer()

    monkeypatch.setattr("lcf_lab.cli.create_server", stub)
    monkeypatch.setattr("lcf_lab.cli.webbrowser.open", opened.append)
    assert main(["serve"]) == 0
    assert opened == ["http://127.0.0.1:8765/"]


@pytest.fixture
def running_server():
    with create_server(0) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        yield server.server_port
        server.shutdown()
        thread.join(timeout=5)


def _request(port, method, route, body=None, headers=None):
    conn = HTTPConnection("127.0.0.1", port, timeout=15)
    try:
        conn.request(method, route, body, headers or {})
        response = conn.getresponse()
        return response.status, response.read(), dict(response.getheaders())
    finally:
        conn.close()


def test_packaged_assets_demo_fit_and_download(running_server):
    port = running_server
    status, html, headers = _request(port, "GET", "/")
    assert status == 200 and b"LCF Lab" in html
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    for route in ("/app.js", "/style.css"):
        assert _request(port, "GET", route)[0] == 200
    status, body, _ = _request(port, "GET", "/api/demo?element=Mn")
    assert status == 200
    request = json.loads(body)
    headers = {"Content-Type": "application/json"}
    status, result, _ = _request(port, "POST", "/api/fit", body, headers)
    assert status == 200
    payload = json.dumps({"analysis": request, "result": json.loads(result)})
    status, archive, response_headers = _request(port, "POST", "/api/export", payload, headers)
    assert status == 200
    assert response_headers["Content-Type"] == "application/zip"
    with ZipFile(io.BytesIO(archive)) as bundle:
        assert json.loads(bundle.read("analysis.json")) == request


def test_reference_library_is_packaged_and_exports_exact_references(running_server):
    status, body, headers = _request(running_server, "GET", "/reference-library.json")
    assert status == 200 and headers["Content-Type"].startswith("application/json")
    pack = json.loads(body)
    assert pack["schema_version"] == 1
    assert {item["element"] for item in pack["standards"]} == {"Mn", "Co", "Ni", "Cu"}
    assert len({item["id"] for item in pack["standards"]}) == len(pack["standards"])
    for item in pack["standards"]:
        assert item["license"] == "CC-BY-4.0"
        assert item["detection_mode"] == "TEY"
        assert item["source_url"].startswith("https://")
        assert len(item["energy"]) == len(item["signal"]) >= 3
        assert np.isfinite(item["signal"]).all() and np.isfinite(item["energy"]).all()
        assert np.all(np.diff(item["energy"]) > 0)
    ref = next(item for item in pack["standards"] if item["element"] == "Cu")
    analysis = {
        "element": "Cu", "edge": "L2,3",
        "samples": [{**ref, "id": "sample", "label": "Replay of the source curve"}],
        "standards": [{**ref, "library": {"pack_id": pack["id"], "version": pack["version"]}}],
        "settings": {"fit_min": ref["energy"][0], "fit_max": ref["energy"][-1]},
    }
    result = fit_batch(analysis)
    assert result["results"][0]["rmse"] == pytest.approx(0)
    with ZipFile(io.BytesIO(build_export(analysis, result))) as bundle:
        assert json.loads(bundle.read("analysis.json"))["standards"] == analysis["standards"]


def test_server_rejects_invalid_requests(running_server):
    port = running_server
    json_header = {"Content-Type": "application/json"}
    cases = [
        ("GET", "/api/demo?element=Cr", None, {}, 400),
        ("GET", "/missing", None, {}, 404),
        ("GET", "/", None, {"Host": "wrong.invalid"}, 403),
        ("POST", "/api/fit", "{}", {"Origin": "https://wrong.invalid"}, 403),
        ("POST", "/missing", "{}", json_header, 404),
        ("POST", "/api/fit", "{}", {}, 415),
        ("POST", "/api/fit", "", json_header, 413),
        ("POST", "/api/fit", "[]", json_header, 400),
        ("POST", "/api/fit", "{", json_header, 400),
        ("POST", "/api/fit", "{}", json_header, 400),
        ("POST", "/api/export", "{}", json_header, 400),
    ]
    for method, route, body, headers, expected in cases:
        status, response, _ = _request(port, method, route, body, headers)
        assert status == expected
        assert json.loads(response)["error"]


def test_rejected_post_with_separate_header_and_body(running_server):
    conn = HTTPConnection("127.0.0.1", running_server, timeout=5)
    try:
        conn.putrequest("POST", "/api/fit")
        conn.putheader("Origin", "https://wrong.invalid")
        conn.putheader("Content-Type", "application/json")
        conn.putheader("Content-Length", "2")
        conn.endheaders()
        ready, _, _ = select.select([conn.sock], [], [], 0.1)
        assert ready == [], "The server closed the connection before receiving the body."
        conn.send(b"{}")
        response = conn.getresponse()
        assert response.status == 403
        assert "local address" in json.loads(response.read())["error"]
    finally:
        conn.close()
