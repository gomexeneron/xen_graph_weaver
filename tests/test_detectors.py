"""Unit tests for AML and Sybil forensic detectors."""

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
from detectors.mule_network import MuleDetector
from detectors.entity_resolver import EntityResolver


def test_layering_cycle_detection():
    b = HeterogeneousGraphBuilder()
    
    # 3 accounts in a circular transfer loop
    for i in range(1, 4):
        b.add_account_node(
            AccountNode(
                node_id=f"ACC-C{i}",
                label=f"Loop Node {i}",
                account_number=f"ACC-{i}",
                holder_name=f"User {i}",
            )
        )

    b.add_transfer(
        TransferEdge(source_id="ACC-C1", target_id="ACC-C2", amount=10000.0, timestamp="T1", transaction_id="TX1")
    )
    b.add_transfer(
        TransferEdge(source_id="ACC-C2", target_id="ACC-C3", amount=9500.0, timestamp="T2", transaction_id="TX2")
    )
    b.add_transfer(
        TransferEdge(source_id="ACC-C3", target_id="ACC-C1", amount=9000.0, timestamp="T3", transaction_id="TX3")
    )

    detector = MuleDetector(b)
    cycles = detector.detect_layering_cycles(min_len=3, max_len=5)

    assert len(cycles) == 1
    assert cycles[0].ring_type == "layering_cycle"
    assert cycles[0].account_count == 3
    assert set(cycles[0].member_ids) == {"ACC-C1", "ACC-C2", "ACC-C3"}
    assert cycles[0].severity == "CRITICAL"


def test_fan_in_mule_detection():
    b = HeterogeneousGraphBuilder()

    aggregator = "ACC-AGG"
    b.add_account_node(AccountNode(node_id=aggregator, label="Aggregator", account_number="999", holder_name="Hub"))

    for i in range(1, 5):
        mule_id = f"ACC-M{i}"
        b.add_account_node(AccountNode(node_id=mule_id, label=f"Mule {i}", account_number=f"M{i}", holder_name=f"Mule {i}"))
        b.add_transfer(
            TransferEdge(
                source_id=mule_id,
                target_id=aggregator,
                amount=6000.0,
                timestamp="T",
                transaction_id=f"TX-IN-{i}",
            )
        )

    detector = MuleDetector(b)
    fan_ins = detector.detect_fan_in_mules(min_senders=3, min_inflow=5000.0)

    assert len(fan_ins) == 1
    assert fan_ins[0].ring_type == "fan_in_mule"
    assert fan_ins[0].transaction_volume == 24000.0
    assert aggregator in fan_ins[0].member_ids


def test_fan_out_mule_detection():
    b = HeterogeneousGraphBuilder()

    distributor = "ACC-DIST"
    b.add_account_node(AccountNode(node_id=distributor, label="Distributor", account_number="111", holder_name="Smurf Boss"))

    for i in range(1, 5):
        target_id = f"ACC-RECV-{i}"
        b.add_account_node(AccountNode(node_id=target_id, label=f"Receiver {i}", account_number=f"R{i}", holder_name=f"Recv {i}"))
        b.add_transfer(
            TransferEdge(
                source_id=distributor,
                target_id=target_id,
                amount=3000.0,
                timestamp="T",
                transaction_id=f"TX-OUT-{i}",
            )
        )

    detector = MuleDetector(b)
    fan_outs = detector.detect_fan_out_mules(min_recipients=3, min_outflow=5000.0)

    assert len(fan_outs) == 1
    assert fan_outs[0].ring_type == "fan_out_mule"
    assert fan_outs[0].transaction_volume == 12000.0


def test_sybil_entity_resolution():
    b = HeterogeneousGraphBuilder()

    dev = MetadataNode(node_id="DEV-SHARED-1", label="Shared Device", entity_type=NodeType.DEVICE, value="fp-123")
    b.add_metadata_node(dev)

    for i in range(1, 5):
        acc_id = f"ACC-SYB-{i}"
        b.add_account_node(AccountNode(node_id=acc_id, label=f"Syb {i}", account_number=f"S{i}", holder_name=f"Puppet {i}"))
        b.add_shared_edge(
            SharedEdge(
                source_id=acc_id,
                target_id=dev.node_id,
                edge_type=EdgeType.SHARED_DEVICE,
            )
        )

    resolver = EntityResolver(b)
    clusters = resolver.resolve_sybil_clusters(min_cluster_size=2)

    assert len(clusters) == 1
    assert clusters[0].size == 4
    assert set(clusters[0].accounts) == {"ACC-SYB-1", "ACC-SYB-2", "ACC-SYB-3", "ACC-SYB-4"}
    assert clusters[0].sybil_probability >= 0.75

    reports = resolver.generate_sybil_ring_reports(clusters)
    assert len(reports) == 1
    assert reports[0].ring_type == "sybil_ring"
