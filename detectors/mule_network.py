"""Forensic detection of Fan-In, Fan-Out mule networks, and circular layering cycles."""

from typing import Any, Dict, List, Set, Tuple
import networkx as nx

from models.summary import RingReport
from engine.graph_builder import HeterogeneousGraphBuilder


class MuleDetector:
    """Detects money mule topologies including Fan-In aggregators,

    Fan-Out distributors (smurfing), and circular layering cycles using NetworkX algorithms.
    """

    def __init__(self, builder: HeterogeneousGraphBuilder):
        self.builder = builder

    def detect_layering_cycles(self, min_len: int = 3, max_len: int = 8) -> List[RingReport]:
        """Detect circular flows of funds using NetworkX simple cycles."""
        flow_g = self.builder.get_funds_flow_digraph()
        cycles_found: List[RingReport] = []

        try:
            raw_cycles = list(nx.simple_cycles(flow_g))
        except Exception:
            raw_cycles = []

        seen_cycle_sets: List[Set[str]] = []
        cycle_idx = 1

        for raw_c in raw_cycles:
            if min_len <= len(raw_c) <= max_len:
                c_set = set(raw_c)
                # Deduplicate identical cycles with different starting rotations
                if any(c_set == existing for existing in seen_cycle_sets):
                    continue
                seen_cycle_sets.append(c_set)

                # Calculate cumulative and bottleneck cycle transaction volume
                cycle_edges_vol = 0.0
                min_edge_vol = float("inf")
                
                for i in range(len(raw_c)):
                    u = raw_c[i]
                    v = raw_c[(i + 1) % len(raw_c)]
                    if flow_g.has_edge(u, v):
                        edge_w = flow_g[u][v].get("weight", 0.0)
                        cycle_edges_vol += edge_w
                        min_edge_vol = min(min_edge_vol, edge_w)

                if min_edge_vol == float("inf"):
                    min_edge_vol = 0.0

                evidence = [
                    f"Closed circular fund flow detected across {len(raw_c)} accounts",
                    f"Bottleneck cycle liquidity: ${min_edge_vol:,.2f} USD",
                    f"Path sequence: {' -> '.join(raw_c)} -> {raw_c[0]}",
                ]

                # Risk score based on cycle length and volume
                risk_score = min(0.99, max(0.80, 0.75 + (min_edge_vol / 50000.0) * 0.2))

                cycles_found.append(
                    RingReport(
                        ring_id=f"RING-CYCLE-{cycle_idx:02d}",
                        ring_type="layering_cycle",
                        member_ids=raw_c,
                        account_count=len(raw_c),
                        transaction_volume=round(cycle_edges_vol, 2),
                        risk_score=round(risk_score, 3),
                        cycle_path=raw_c + [raw_c[0]],
                        evidence=evidence,
                        severity="CRITICAL",
                        recommended_action="FREEZE_IMMEDIATELY_AND_SAR",
                    )
                )
                cycle_idx += 1

        return cycles_found

    def detect_fan_in_mules(
        self,
        min_senders: int = 3,
        min_inflow: float = 5000.0,
    ) -> List[RingReport]:
        """Detect Fan-In aggregator mule accounts receiving transfers from multiple distinct accounts."""
        flow_g = self.builder.get_funds_flow_digraph()
        fan_ins: List[RingReport] = []
        idx = 1

        for node_id in flow_g.nodes:
            in_edges = list(flow_g.in_edges(node_id, data=True))
            distinct_senders = [u for u, _, _ in in_edges]
            
            if len(distinct_senders) >= min_senders:
                total_inflow = sum(d.get("weight", 0.0) for _, _, d in in_edges)
                if total_inflow >= min_inflow:
                    # Also check outbound funneling
                    out_edges = list(flow_g.out_edges(node_id, data=True))
                    total_outflow = sum(d.get("weight", 0.0) for _, _, d in out_edges)
                    out_recipients = [v for _, v, _ in out_edges]

                    all_members = list(set([node_id] + distinct_senders + out_recipients))
                    
                    evidence = [
                        f"Aggregator node received inbound transfers from {len(distinct_senders)} distinct accounts",
                        f"Total inbound funnel volume: ${total_inflow:,.2f} USD",
                    ]
                    if total_outflow > 0:
                        velocity_ratio = min(1.0, total_outflow / (total_inflow + 1e-5))
                        evidence.append(f"Pass-through outbound liquidity ratio: {velocity_ratio * 100:.1f}%")

                    risk_score = min(0.95, 0.70 + (len(distinct_senders) * 0.05))

                    fan_ins.append(
                        RingReport(
                            ring_id=f"RING-FANIN-{idx:02d}",
                            ring_type="fan_in_mule",
                            member_ids=all_members,
                            account_count=len(all_members),
                            transaction_volume=round(total_inflow, 2),
                            risk_score=round(risk_score, 3),
                            cycle_path=[f"{s} -> {node_id}" for s in distinct_senders],
                            evidence=evidence,
                            severity="HIGH",
                            recommended_action="SUBMIT_SAR_AND_RESTRICT_WIRES",
                        )
                    )
                    idx += 1

        return fan_ins

    def detect_fan_out_mules(
        self,
        min_recipients: int = 3,
        min_outflow: float = 5000.0,
    ) -> List[RingReport]:
        """Detect Fan-Out smurfing/structuring distributor nodes scattering funds to multiple satellite accounts."""
        flow_g = self.builder.get_funds_flow_digraph()
        fan_outs: List[RingReport] = []
        idx = 1

        for node_id in flow_g.nodes:
            out_edges = list(flow_g.out_edges(node_id, data=True))
            distinct_recipients = [v for _, v, _ in out_edges]

            if len(distinct_recipients) >= min_recipients:
                total_outflow = sum(d.get("weight", 0.0) for _, _, d in out_edges)
                if total_outflow >= min_outflow:
                    in_edges = list(flow_g.in_edges(node_id, data=True))
                    distinct_senders = [u for u, _, _ in in_edges]
                    all_members = list(set([node_id] + distinct_recipients + distinct_senders))

                    evidence = [
                        f"Smurfing distributor node scattered funds to {len(distinct_recipients)} distinct satellite accounts",
                        f"Total structured outbound dispersion: ${total_outflow:,.2f} USD",
                    ]

                    risk_score = min(0.92, 0.68 + (len(distinct_recipients) * 0.04))

                    fan_outs.append(
                        RingReport(
                            ring_id=f"RING-FANOUT-{idx:02d}",
                            ring_type="fan_out_mule",
                            member_ids=all_members,
                            account_count=len(all_members),
                            transaction_volume=round(total_outflow, 2),
                            risk_score=round(risk_score, 3),
                            cycle_path=[f"{node_id} -> {r}" for r in distinct_recipients],
                            evidence=evidence,
                            severity="HIGH",
                            recommended_action="FLAG_STRUCTURING_AND_REQUEST_KYC",
                        )
                    )
                    idx += 1

        return fan_outs

    def detect_all_rings(self) -> List[RingReport]:
        """Run all topological mule and cycle detectors and return combined list of rings."""
        all_rings: List[RingReport] = []
        all_rings.extend(self.detect_layering_cycles())
        all_rings.extend(self.detect_fan_in_mules())
        all_rings.extend(self.detect_fan_out_mules())
        return all_rings
