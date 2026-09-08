"""Topological and forensic summary engine for compliance graphs."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import networkx as nx

from models.entity import NodeType, EdgeType
from models.summary import (
    GraphSummary,
    ClusterMetric,
    RingReport,
    CentralityTopNode,
)
from .graph_builder import HeterogeneousGraphBuilder


class GraphSummaryEngine:
    """Computes topological graph metrics, centralities, risk aggregations,

    and generates automated executive compliance narratives.
    """

    def __init__(self, builder: HeterogeneousGraphBuilder):
        self.builder = builder

    def generate_summary(
        self,
        detected_rings: Optional[List[RingReport]] = None,
        sybil_clusters: Optional[List[ClusterMetric]] = None,
    ) -> GraphSummary:
        """Calculate complete graph metrics and generate structured summary report."""
        g = self.builder.graph
        total_nodes = len(g.nodes)
        total_edges = len(g.edges)

        # Accounts vs Metadata breakdowns
        account_nodes_count = len(self.builder.account_nodes)
        metadata_nodes_count = len(self.builder.metadata_nodes)
        transfer_edges_count = len(self.builder.transfers)
        shared_edges_count = len(self.builder.shared_edges)
        total_volume = sum(t.amount for t in self.builder.transfers)

        # Topological statistics
        avg_degree = (2.0 * total_edges / total_nodes) if total_nodes > 0 else 0.0
        
        # Simple graph projection for density and connected components
        undirected_proj = nx.Graph(g)
        density = nx.density(undirected_proj) if total_nodes > 1 else 0.0
        connected_components_count = (
            nx.number_connected_components(undirected_proj) if total_nodes > 0 else 0
        )

        # Compute betweenness and pagerank centralities
        flow_g = self.builder.get_funds_flow_digraph()
        
        try:
            betweenness = nx.betweenness_centrality(undirected_proj)
        except Exception:
            betweenness = {n: 0.0 for n in g.nodes}

        try:
            pageranks = nx.pagerank(flow_g, alpha=0.85, max_iter=100) if len(flow_g.nodes) > 0 else {}
        except Exception:
            pageranks = {n: 0.0 for n in g.nodes}

        # Identify top central nodes
        top_central: List[CentralityTopNode] = []
        for n, data in g.nodes(data=True):
            in_deg = g.in_degree(n)
            out_deg = g.out_degree(n)
            tot_deg = g.degree(n)
            bw = betweenness.get(n, 0.0)
            pr = pageranks.get(n, 0.0)
            r_base = data.get("risk_score", 0.0)
            r_prop = data.get("propagated_risk_score", r_base)
            is_flg = data.get("is_flagged", False)

            top_central.append(
                CentralityTopNode(
                    node_id=n,
                    label=data.get("label", n),
                    entity_type=data.get("node_type", "ACCOUNT"),
                    degree=tot_deg,
                    in_degree=in_deg,
                    out_degree=out_deg,
                    betweenness_centrality=round(bw, 4),
                    pagerank=round(pr, 4),
                    risk_score=round(r_base, 3),
                    propagated_risk_score=round(r_prop, 3),
                    is_flagged=is_flg,
                )
            )

        # Sort top central nodes by combined betweenness + pagerank
        top_central.sort(key=lambda x: (x.betweenness_centrality * 2 + x.pagerank), reverse=True)
        top_central = top_central[:10]

        # Top risk accounts
        top_risk_accounts: List[Dict[str, Any]] = []
        high_risk_count = 0
        for acc in self.builder.get_all_accounts():
            effective_risk = max(acc.risk_score, acc.propagated_risk_score)
            if effective_risk >= 0.70 or acc.is_flagged:
                high_risk_count += 1
            top_risk_accounts.append({
                "node_id": acc.node_id,
                "holder_name": acc.holder_name,
                "account_number": acc.account_number,
                "base_risk": acc.risk_score,
                "propagated_risk": acc.propagated_risk_score,
                "is_flagged": acc.is_flagged,
                "tags": acc.tags,
            })

        top_risk_accounts.sort(key=lambda x: max(x["base_risk"], x["propagated_risk"]), reverse=True)
        top_risk_accounts = top_risk_accounts[:10]

        rings = detected_rings or []
        sybils = sybil_clusters or []

        narrative = self._build_executive_narrative(
            total_nodes=total_nodes,
            total_edges=total_edges,
            total_volume=total_volume,
            high_risk_count=high_risk_count,
            rings=rings,
            sybils=sybils,
            top_central=top_central,
        )

        return GraphSummary(
            total_nodes=total_nodes,
            total_edges=total_edges,
            account_nodes_count=account_nodes_count,
            metadata_nodes_count=metadata_nodes_count,
            transfer_edges_count=transfer_edges_count,
            shared_edges_count=shared_edges_count,
            total_transaction_volume=round(total_volume, 2),
            average_degree=round(avg_degree, 2),
            graph_density=round(density, 4),
            connected_components_count=connected_components_count,
            high_risk_accounts_count=high_risk_count,
            sybil_clusters=sybils,
            detected_rings=rings,
            top_central_nodes=top_central,
            top_risk_nodes=top_risk_accounts,
            executive_narrative=narrative,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    def _build_executive_narrative(
        self,
        total_nodes: int,
        total_edges: int,
        total_volume: float,
        high_risk_count: int,
        rings: List[RingReport],
        sybils: List[ClusterMetric],
        top_central: List[CentralityTopNode],
    ) -> str:
        """Construct a structured Markdown compliance forensic brief."""
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        ring_lines = []
        for r in rings:
            ring_lines.append(
                f"- **[{r.ring_id}] {r.ring_type.upper()}** (Severity: `{r.severity}`, Vol: `${r.transaction_volume:,.2f}`)\n"
                f"  - Members: `{', '.join(r.member_ids[:6])}{'...' if len(r.member_ids) > 6 else ''}`\n"
                f"  - Evidence: {'; '.join(r.evidence[:2])}\n"
                f"  - Recommended Action: `{r.recommended_action}`"
            )
        rings_md = "\n".join(ring_lines) if ring_lines else "*No active money laundering rings identified.*"

        sybil_lines = []
        for s in sybils:
            sybil_lines.append(
                f"- **[{s.cluster_id}] {s.description}**\n"
                f"  - Linked Accounts ({s.size}): `{', '.join(s.accounts[:5])}`\n"
                f"  - Shared Anchors: `{', '.join(s.shared_anchors)}`\n"
                f"  - Sybil Probability: **{s.sybil_probability * 100:.1f}%** (Risk: `{s.risk_level}`)"
            )
        sybils_md = "\n".join(sybil_lines) if sybil_lines else "*No multi-accounting Sybil clusters detected.*"

        hub_node = top_central[0].node_id if top_central else "N/A"

        return f"""# Automated Forensic AML & Sybil Compliance Brief
**Generated At:** {timestamp}
**Target Ledger:** Alpaca Brokerage & Plaid Anchor Network

---

### Executive Overview
- **Network Scope:** {total_nodes} entities ({len(self.builder.account_nodes)} accounts, {len(self.builder.metadata_nodes)} metadata anchors) across {total_edges} relations.
- **Audit Volume:** **${total_volume:,.2f} USD** evaluated across financial transfer channels.
- **Threat Vector:** **{len(rings)} AML Ring(s)** and **{len(sybils)} Coordinated Sybil Cluster(s)** isolated.
- **High-Risk Exposure:** **{high_risk_count}** accounts flagged for enhanced due diligence (SAR escalation).
- **Primary Bottleneck / Hub Node:** `{hub_node}` (High Betweenness & Contamination Flow).

---

### Detected Laundering & Mule Topologies
{rings_md}

---

### Identity Resolution & Sybil Multi-Accounting Clusters
{sybils_md}

---

### Recommended Compliance Remediation
1. **Immediate Freezes:** Restrict wire outflows and Alpaca trading permissions for accounts identified in circular layering cycles and mule aggregator hubs.
2. **FinCEN SAR Filing:** File Suspicious Activity Reports for accounts exhibiting coordinated device / bank account anchor collisions.
3. **Automated Risk Propagation:** Maintain live risk diffusion damping ($\alpha = 0.65$) to detect second-degree money mule recruitment.
"""
