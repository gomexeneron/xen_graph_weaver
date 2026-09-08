"""Unit tests for Risk Propagation, Graph Summary Engine, and Simulation Feed."""

import pytest
from simulation.alpaca_feed_sim import AlpacaFeedSimulator
from engine.graph_builder import HeterogeneousGraphBuilder
from engine.risk_propagator import RiskPropagator
from engine.graph_summary import GraphSummaryEngine
from detectors.mule_network import MuleDetector
from detectors.entity_resolver import EntityResolver


def test_simulation_feed_and_rings():
    sim = AlpacaFeedSimulator(seed=42)
    builder = sim.create_fresh_graph()

    assert len(builder.account_nodes) > 15
    assert len(builder.metadata_nodes) > 5
    assert len(builder.transfers) > 10

    mule_det = MuleDetector(builder)
    layering_cycles = mule_det.detect_layering_cycles()
    fan_in_mules = mule_det.detect_fan_in_mules()
    
    resolver = EntityResolver(builder)
    sybils = resolver.resolve_sybil_clusters()

    # Verify Ring 1 (Layering Cycle) detected
    assert len(layering_cycles) >= 1
    assert any("ACC-CYC-01" in c.member_ids for c in layering_cycles)

    # Verify Ring 2 (Fan-In Mule) detected
    assert len(fan_in_mules) >= 1
    assert any("ACC-FUNNEL-01" in f.member_ids for f in fan_in_mules)

    # Verify Ring 3 (Sybil Multi-Accounting) detected
    assert len(sybils) >= 1
    assert any(s.size >= 7 for s in sybils)


def test_risk_propagation():
    sim = AlpacaFeedSimulator(seed=42)
    builder = sim.create_fresh_graph()

    propagator = RiskPropagator(builder)
    scores = propagator.propagate_and_update()

    assert len(scores) == len(builder.graph.nodes)
    
    # Flagged nodes should have high risk
    assert scores["ACC-CYC-01"] >= 0.80
    assert scores["ACC-SINK-OFFSHORE"] >= 0.80

    # Intermediate hops in cycle should receive diffused risk
    assert scores["ACC-CYC-02"] > 0.30
    assert builder.graph.nodes["ACC-CYC-02"]["propagated_risk_score"] == scores["ACC-CYC-02"]


def test_graph_summary_engine():
    sim = AlpacaFeedSimulator(seed=42)
    builder = sim.create_fresh_graph()

    propagator = RiskPropagator(builder)
    propagator.propagate_and_update()

    mule_det = MuleDetector(builder)
    rings = mule_det.detect_all_rings()
    resolver = EntityResolver(builder)
    sybils = resolver.resolve_sybil_clusters()

    summary_engine = GraphSummaryEngine(builder)
    summary = summary_engine.generate_summary(detected_rings=rings, sybil_clusters=sybils)

    assert summary.total_nodes > 0
    assert summary.total_edges > 0
    assert summary.total_transaction_volume > 50000.0
    assert summary.average_degree > 0.0
    assert len(summary.top_central_nodes) > 0
    assert len(summary.top_risk_nodes) > 0
    assert "Automated Forensic AML" in summary.executive_narrative
    assert len(summary.detected_rings) >= 2
