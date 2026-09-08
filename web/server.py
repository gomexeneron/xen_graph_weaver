"""High-performance compliance REST API and GUI static server for xen_graph_weaver."""

import json
import mimetypes
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import urlparse, parse_qs, unquote

from engine.graph_builder import HeterogeneousGraphBuilder
from engine.risk_propagator import RiskPropagator
from engine.graph_summary import GraphSummaryEngine
from detectors.mule_network import MuleDetector
from detectors.entity_resolver import EntityResolver
from simulation.alpaca_feed_sim import AlpacaFeedSimulator
from models.summary import GraphSummary, RingReport, ClusterMetric


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Multi-threaded HTTP Server for handling concurrent GUI and API requests."""
    daemon_threads = True
    allow_reuse_address = True


class AppState:
    """Global state container for the active ledger, engines, and detectors."""

    def __init__(self):
        self.builder: HeterogeneousGraphBuilder = HeterogeneousGraphBuilder()
        self.simulator: AlpacaFeedSimulator = AlpacaFeedSimulator(seed=42)
        self.propagator: Optional[RiskPropagator] = None
        self.summary_engine: Optional[GraphSummaryEngine] = None
        self.mule_detector: Optional[MuleDetector] = None
        self.entity_resolver: Optional[EntityResolver] = None
        self.detected_rings: List[RingReport] = []
        self.sybil_clusters: List[ClusterMetric] = []
        self.initialize_engine()

    def initialize_engine(self):
        self.builder = self.simulator.create_fresh_graph()
        self.propagator = RiskPropagator(self.builder)
        self.mule_detector = MuleDetector(self.builder)
        self.entity_resolver = EntityResolver(self.builder)
        self.summary_engine = GraphSummaryEngine(self.builder)
        
        # Initial risk propagation and ring detection
        self.propagator.propagate_and_update()
        self.run_detection()

    def run_detection(self):
        mule_rings = self.mule_detector.detect_all_rings()
        sybils = self.entity_resolver.resolve_sybil_clusters()
        sybil_rings = self.entity_resolver.generate_sybil_ring_reports(sybils)
        
        self.sybil_clusters = sybils
        self.detected_rings = mule_rings + sybil_rings


state = AppState()
STATIC_DIR = Path(__file__).resolve().parent / "static"


class ComplianceRequestHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler implementing RESTful endpoints and static asset serving."""

    def _set_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def _send_json(self, data: Any, status: int = 200):
        body = json.dumps(data, default=lambda o: o.model_dump() if hasattr(o, "model_dump") else (o.dict() if hasattr(o, "dict") else str(o))).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._set_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, filepath: Path):
        if not filepath.exists() or filepath.is_dir():
            self._send_json({"error": "File not found"}, status=404)
            return

        mime_type, _ = mimetypes.guess_type(str(filepath))
        if not mime_type:
            mime_type = "application/octet-stream"

        with open(filepath, "rb") as f:
            content = f.read()

        self.send_response(200)
        self.send_header("Content-Type", mime_type)
        self.send_header("Content-Length", str(len(content)))
        self._set_cors_headers()
        self.end_headers()
        self.wfile.write(content)

    def do_OPTIONS(self):
        self.send_response(204)
        self._set_cors_headers()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        # Static GUI files
        if path == "/" or path == "/index.html":
            self._send_file(STATIC_DIR / "index.html")
            return
        elif path.startswith("/static/"):
            rel_path = path.replace("/static/", "", 1)
            self._send_file(STATIC_DIR / rel_path)
            return

        # REST API Routes
        if path == "/api/health":
            self._send_json({
                "status": "healthy",
                "service": "xen_graph_weaver",
                "nodes": len(state.builder.graph.nodes),
                "edges": len(state.builder.graph.edges),
            })
            return

        elif path == "/api/graph":
            min_risk = float(params.get("min_risk", [0.0])[0])
            include_metadata = params.get("include_metadata", ["true"])[0].lower() == "true"
            payload = state.builder.to_visjs_payload()

            if min_risk > 0.0 or not include_metadata:
                filtered_nodes = []
                keep_ids = set()

                for node in payload["nodes"]:
                    n_type = node.get("node_type", "ACCOUNT")
                    if not include_metadata and n_type != "ACCOUNT":
                        continue
                    if node.get("risk_score", 0.0) >= min_risk:
                        filtered_nodes.append(node)
                        keep_ids.add(node["id"])

                filtered_edges = [
                    e for e in payload["edges"]
                    if e["from"] in keep_ids and e["to"] in keep_ids
                ]

                self._send_json({
                    "nodes": filtered_nodes,
                    "edges": filtered_edges,
                    "node_count": len(filtered_nodes),
                    "edge_count": len(filtered_edges),
                })
                return

            self._send_json(payload)
            return

        elif path == "/api/summary":
            summary = state.summary_engine.generate_summary(
                detected_rings=state.detected_rings,
                sybil_clusters=state.sybil_clusters,
            )
            self._send_json(summary.model_dump())
            return

        elif path == "/api/rings":
            self._send_json([r.model_dump() for r in state.detected_rings])
            return

        elif path == "/api/sybils":
            self._send_json([s.model_dump() for s in state.sybil_clusters])
            return

        elif path.startswith("/api/node/"):
            node_id = unquote(path.replace("/api/node/", "", 1))
            forensics = state.builder.get_node_forensics(node_id)
            if not forensics:
                self._send_json({"error": f"Node '{node_id}' not found."}, status=404)
                return
            self._send_json(forensics)
            return

        self._send_json({"error": f"Endpoint '{path}' not found."}, status=404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == "/api/propagate-risk":
            updated_scores = state.propagator.propagate_and_update()
            state.run_detection()
            self._send_json({
                "status": "success",
                "updated_nodes_count": len(updated_scores),
                "high_risk_count": sum(1 for s in updated_scores.values() if s >= 0.70),
                "scores": updated_scores,
            })
            return

        elif path == "/api/simulate/reset":
            seed = int(params.get("seed", [42])[0])
            state.simulator = AlpacaFeedSimulator(seed=seed)
            state.initialize_engine()
            self._send_json({
                "status": "success",
                "message": "Graph simulation re-seeded and re-initialized.",
                "nodes": len(state.builder.graph.nodes),
                "edges": len(state.builder.graph.edges),
            })
            return

        self._send_json({"error": f"POST endpoint '{path}' not found."}, status=404)

    def log_message(self, format, *args):
        # Suppress noisy standard request logs for cleaner CLI output
        pass


def run_server(host: str = "127.0.0.1", port: int = 8085):
    """Start the compliance web server."""
    server = ThreadedHTTPServer((host, port), ComplianceRequestHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


# Compatibility entrypoint
app = run_server
