"""Entrypoint to run ingestion simulation and launch compliance GUI server on port 8085."""

import argparse
import sys

from simulation.alpaca_feed_sim import AlpacaFeedSimulator
from engine.graph_builder import HeterogeneousGraphBuilder
from detectors.mule_network import MuleDetector
from detectors.entity_resolver import EntityResolver
from engine.risk_propagator import RiskPropagator
from web.server import run_server


def print_banner(host: str, port: int):
    banner = f"""
======================================================================
  __  _______ _   _    ____ ____      _    ____  _   _ 
  \\ \\/ / ____| \\ | |  / ___|  _ \\    / \\  |  _ \\| | | |
   \\  /|  _| |  \\| | | |  _| |_) |  / _ \\ | |_) | |_| |
   /  \\| |___| |\\  | | |_| |  _ <  / ___ \\|  __/|  _  |
  /_/\\_\\_____|_| \\_|  \\____|_| \\_\\/_/   \\_\\_|   |_| |_|
            W E A V E R   --   C O M P L I A N C E   G U I
======================================================================
 [*] Forensic AML & Sybil Detection Platform Initialized
 [*] Web GUI Active:        http://{host}:{port}
 [*] REST Endpoints Active: http://{host}:{port}/api/graph
 [*] Simulation Feed:       Alpaca Brokerage + Plaid Anchors
======================================================================
"""
    print(banner)


def main():
    parser = argparse.ArgumentParser(description="Xen Graph Weaver Compliance Server")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host address to bind")
    parser.add_argument("--port", type=int, default=8085, help="Port number (default: 8085)")
    args = parser.parse_args()

    # Pre-flight diagnostic simulation check
    sim = AlpacaFeedSimulator(seed=42)
    builder = sim.create_fresh_graph()
    propagator = RiskPropagator(builder)
    propagator.propagate_and_update()

    mule_det = MuleDetector(builder)
    rings = mule_det.detect_all_rings()
    resolver = EntityResolver(builder)
    sybils = resolver.resolve_sybil_clusters()

    print(f"[*] Ingested {len(builder.graph.nodes)} nodes ({len(builder.account_nodes)} accounts, {len(builder.metadata_nodes)} anchors).")
    print(f"[*] Identified {len(rings)} AML flow rings & {len(sybils)} Sybil multi-accounting clusters.")
    print_banner(args.host, args.port)

    # Launch server
    run_server(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
