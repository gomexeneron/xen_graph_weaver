"""Integration tests for Web API endpoints."""

import threading
import time
import requests
import pytest
from web.server import run_server, ThreadedHTTPServer, ComplianceRequestHandler


@pytest.fixture(scope="module")
def server_url():
    port = 8099
    host = "127.0.0.1"
    server = ThreadedHTTPServer((host, port), ComplianceRequestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.5)
    base_url = f"http://{host}:{port}"
    yield base_url
    server.shutdown()
    server.server_close()


def test_api_health(server_url):
    res = requests.get(f"{server_url}/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["nodes"] > 0


def test_api_graph(server_url):
    res = requests.get(f"{server_url}/api/graph")
    assert res.status_code == 200
    data = res.json()
    assert "nodes" in data
    assert "edges" in data
    assert len(data["nodes"]) > 0


def test_api_summary(server_url):
    res = requests.get(f"{server_url}/api/summary")
    assert res.status_code == 200
    data = res.json()
    assert "total_transaction_volume" in data
    assert "executive_narrative" in data
    assert len(data["detected_rings"]) >= 2


def test_api_rings(server_url):
    res = requests.get(f"{server_url}/api/rings")
    assert res.status_code == 200
    rings = res.json()
    assert isinstance(rings, list)
    assert len(rings) >= 2


def test_api_node_forensics(server_url):
    res = requests.get(f"{server_url}/api/node/ACC-CYC-01")
    assert res.status_code == 200
    data = res.json()
    assert data["node_id"] == "ACC-CYC-01"
    assert data["total_outflow"] > 0


def test_api_propagate_risk(server_url):
    res = requests.post(f"{server_url}/api/propagate-risk")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["updated_nodes_count"] > 0
