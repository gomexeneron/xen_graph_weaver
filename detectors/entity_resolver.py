"""Entity Resolution and Sybil Cluster Detection using Bipartite Connected Components."""

from typing import Dict, List, Set, Tuple
import networkx as nx

from models.entity import NodeType, EdgeType
from models.summary import ClusterMetric, RingReport
from engine.graph_builder import HeterogeneousGraphBuilder


class EntityResolver:
    """Resolves true entities and detects multi-accounting Sybil rings

    by identifying connected components across shared Device, Bank, IP, and Email anchors.
    """

    def __init__(self, builder: HeterogeneousGraphBuilder):
        self.builder = builder

    def resolve_sybil_clusters(self, min_cluster_size: int = 2) -> List[ClusterMetric]:
        """Identify clusters of accounts linked via one or more shared metadata anchors."""
        bipartite_g = self.builder.get_bipartite_entity_graph()
        clusters: List[ClusterMetric] = []

        components = list(nx.connected_components(bipartite_g))
        cluster_idx = 1

        for comp in components:
            # Separate account nodes from metadata anchor nodes
            accounts = [
                n for n in comp
                if bipartite_g.nodes[n].get("node_type") == NodeType.ACCOUNT.value
            ]
            anchors = [
                n for n in comp
                if bipartite_g.nodes[n].get("node_type") != NodeType.ACCOUNT.value
            ]

            # Sybil cluster must contain at least min_cluster_size accounts sharing anchors
            if len(accounts) >= min_cluster_size and len(anchors) > 0:
                sub_g = bipartite_g.subgraph(comp)
                density = round(nx.density(sub_g), 4)

                # Determine primary binding anchor types
                anchor_types = [
                    self.builder.graph.nodes[a].get("node_type", "UNKNOWN")
                    for a in anchors if a in self.builder.graph.nodes
                ]

                # Calculate Sybil coordination probability
                # Factors: number of accounts, shared device/bank weights, density
                has_shared_device = NodeType.DEVICE.value in anchor_types
                has_shared_bank = NodeType.BANK_ACCOUNT.value in anchor_types
                has_shared_ssn = NodeType.SSN.value in anchor_types

                base_prob = 0.50
                if has_shared_device:
                    base_prob += 0.25
                if has_shared_bank:
                    base_prob += 0.20
                if has_shared_ssn:
                    base_prob += 0.30
                if len(accounts) >= 5:
                    base_prob += 0.15

                sybil_prob = min(0.99, max(0.40, base_prob))

                risk_level = "CRITICAL" if sybil_prob >= 0.85 else ("HIGH" if sybil_prob >= 0.65 else "MEDIUM")

                primary_anchor = anchors[0] if anchors else "N/A"
                desc = (
                    f"Sybil ring of {len(accounts)} accounts sharing "
                    f"{len(anchors)} anchor(s) ({', '.join(set(anchor_types))})"
                )

                clusters.append(
                    ClusterMetric(
                        cluster_id=f"SYBIL-CLUSTER-{cluster_idx:02d}",
                        cluster_type="shared_anchor_sybil",
                        size=len(accounts),
                        density=density,
                        accounts=accounts,
                        shared_anchors=anchors,
                        risk_level=risk_level,
                        sybil_probability=round(sybil_prob, 3),
                        primary_anchor=primary_anchor,
                        description=desc,
                    )
                )
                cluster_idx += 1

        # Sort clusters by size and probability descending
        clusters.sort(key=lambda c: (c.size, c.sybil_probability), reverse=True)
        return clusters

    def generate_sybil_ring_reports(
        self, clusters: List[ClusterMetric]
    ) -> List[RingReport]:
        """Convert detected Sybil clusters into standardized RingReport formats."""
        reports: List[RingReport] = []

        for c in clusters:
            all_members = c.accounts + c.shared_anchors
            
            # Calculate cumulative transaction volume for accounts in this cluster
            cluster_vol = 0.0
            for transfer in self.builder.transfers:
                if transfer.source_id in c.accounts or transfer.target_id in c.accounts:
                    cluster_vol += transfer.amount

            evidence = [
                f"Multi-accounting Sybil ring binding {c.size} accounts",
                f"Shared anchors: {', '.join(c.shared_anchors)}",
                f"Coordination probability index: {c.sybil_probability * 100:.1f}%",
            ]

            reports.append(
                RingReport(
                    ring_id=f"RING-SYBIL-{c.cluster_id.split('-')[-1]}",
                    ring_type="sybil_ring",
                    member_ids=all_members,
                    account_count=c.size,
                    transaction_volume=round(cluster_vol, 2),
                    risk_score=c.sybil_probability,
                    evidence=evidence,
                    severity=c.risk_level,
                    recommended_action="CONSOLIDATE_ENTITIES_AND_FREEZE",
                )
            )

        return reports
