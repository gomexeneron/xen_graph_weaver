"""Unit tests for HeterogeneousGraphBuilder."""

import pytest
from models.entity import (
    AccountNode,
    MetadataNode,
    TransferEdge,
    SharedEdge,
    NodeType,
    EdgeType,
)
from engine.graph_builder import HeterogeneousGraphBuilder


@pytest.fixture
def empty_builder():
    return HeterogeneousGraphBuilder()


def test_add_account_and_metadata(empty_builder):
    b = empty_builder
    acc = AccountNode(
        node_id="ACC-01",
        label="Test Account 1",
        account_number="12345",
        holder_name="Alice Smith",
        risk_score=0.2,
    )
    dev = MetadataNode(
        node_id="DEV-01",
        label="Test Device 1",
        entity_type=NodeType.DEVICE,
        value="fingerprint-abc",
    )
    b.add_account_node(acc)
    b.add_metadata_node(dev)

    assert "ACC-01" in b.graph.nodes
    assert "DEV-01" in b.graph.nodes
    assert b.get_account("ACC-01").holder_name == "Alice Smith"
    assert b.get_metadata("DEV-01").value == "fingerprint-abc"


def test_add_transfers_and_shared_edges(empty_builder):
    b = empty_builder
    acc1 = AccountNode(node_id="ACC-01", label="A1", account_number="1", holder_name="A")
    acc2 = AccountNode(node_id="ACC-02", label="A2", account_number="2", holder_name="B")
    dev = MetadataNode(node_id="DEV-01", label="D1", entity_type=NodeType.DEVICE, value="fp")

    b.add_account_node(acc1)
    b.add_account_node(acc2)
    b.add_metadata_node(dev)

    tx = TransferEdge(
        source_id="ACC-01",
        target_id="ACC-02",
        amount=5000.0,
        timestamp="2026-09-01T00:00:00Z",
        transaction_id="TX-100",
    )
    b.add_transfer(tx)

    shared1 = SharedEdge(
        source_id="ACC-01",
        target_id="DEV-01",
        edge_type=EdgeType.SHARED_DEVICE,
    )
    shared2 = SharedEdge(
        source_id="ACC-02",
        target_id="DEV-01",
        edge_type=EdgeType.SHARED_DEVICE,
    )
    b.add_shared_edge(shared1)
    b.add_shared_edge(shared2)

    assert len(b.transfers) == 1
    assert len(b.shared_edges) == 2

    # Verify flow graph
    flow = b.get_funds_flow_digraph()
    assert flow.has_edge("ACC-01", "ACC-02")
    assert flow["ACC-01"]["ACC-02"]["weight"] == 5000.0

    # Verify bipartite graph
    bipartite = b.get_bipartite_entity_graph()
    assert bipartite.has_edge("ACC-01", "DEV-01")
    assert bipartite.has_edge("ACC-02", "DEV-01")


def test_to_visjs_payload(empty_builder):
    b = empty_builder
    acc = AccountNode(
        node_id="ACC-FLAG",
        label="Flagged Account",
        account_number="999",
        holder_name="Bad Actor",
        risk_score=0.9,
        is_flagged=True,
    )
    b.add_account_node(acc)

    payload = b.to_visjs_payload()
    assert payload["node_count"] == 1
    node_vis = payload["nodes"][0]
    assert node_vis["id"] == "ACC-FLAG"
    assert node_vis["is_flagged"] is True
    assert node_vis["shape"] == "dot"
    assert node_vis["color"]["background"] == "#ef4444"


def test_node_forensics(empty_builder):
    b = empty_builder
    acc1 = AccountNode(node_id="ACC-01", label="A1", account_number="1", holder_name="A")
    acc2 = AccountNode(node_id="ACC-02", label="A2", account_number="2", holder_name="B")
    b.add_account_node(acc1)
    b.add_account_node(acc2)

    b.add_transfer(
        TransferEdge(
            source_id="ACC-01",
            target_id="ACC-02",
            amount=12000.0,
            timestamp="2026-09-01T12:00:00Z",
            transaction_id="TX-F1",
        )
    )

    forensics = b.get_node_forensics("ACC-02")
    assert forensics is not None
    assert forensics["total_inflow"] == 12000.0
    assert forensics["total_outflow"] == 0.0
    assert len(forensics["inbound_transfers"]) == 1
    assert forensics["inbound_transfers"][0]["from_node"] == "ACC-01"
