"""NetworkX Heterogeneous Graph Constructor for Accounts and Bipartite Metadata Anchors."""

from typing import Any, Dict, List, Optional, Set, Tuple
import networkx as nx

from models.entity import (
    AccountNode,
    MetadataNode,
    TransferEdge,
    SharedEdge,
    NodeType,
    EdgeType,
)


class HeterogeneousGraphBuilder:
    """Builds and manages a heterogeneous compliance graph containing Account entities

    and bipartite Metadata anchors (Devices, Bank Accounts, IPs, Emails, SSNs).
    """

    def __init__(self):
        self.graph = nx.MultiDiGraph()
        self.account_nodes: Dict[str, AccountNode] = {}
        self.metadata_nodes: Dict[str, MetadataNode] = {}
        self.transfers: List[TransferEdge] = []
        self.shared_edges: List[SharedEdge] = []

    def add_account_node(self, account: AccountNode) -> None:
        """Add or update an Account node in the graph."""
        self.account_nodes[account.node_id] = account
        self.graph.add_node(
            account.node_id,
            node_type=account.entity_type.value,
            label=account.label,
            account_number=account.account_number,
            holder_name=account.holder_name,
            broker=account.broker,
            risk_score=account.risk_score,
            propagated_risk_score=account.propagated_risk_score,
            is_flagged=account.is_flagged,
            tags=account.tags,
            created_at=account.created_at,
            metadata=account.metadata,
        )

    def add_metadata_node(self, metadata: MetadataNode) -> None:
        """Add or update a Metadata anchor node (Device, Bank, IP, etc.)."""
        self.metadata_nodes[metadata.node_id] = metadata
        self.graph.add_node(
            metadata.node_id,
            node_type=metadata.entity_type.value,
            label=metadata.label,
            value=metadata.value,
            risk_weight=metadata.risk_weight,
            risk_score=metadata.risk_weight,
            propagated_risk_score=metadata.risk_weight,
            metadata=metadata.metadata,
        )

    def add_transfer(self, transfer: TransferEdge) -> None:
        """Add a directed financial transfer edge between two accounts."""
        self.transfers.append(transfer)
        self.graph.add_edge(
            transfer.source_id,
            transfer.target_id,
            key=f"transfer_{transfer.transaction_id}",
            edge_type=transfer.edge_type.value,
            amount=transfer.amount,
            currency=transfer.currency,
            timestamp=transfer.timestamp,
            transaction_id=transfer.transaction_id,
            risk_score=transfer.risk_score,
            metadata=transfer.metadata,
        )

    def add_shared_edge(self, shared: SharedEdge) -> None:
        """Add a shared metadata anchor edge (undirected relation represented by bidirectional or directed edge)."""
        self.shared_edges.append(shared)
        # We add bidirectional edges in MultiDiGraph so neighborhood traversal is symmetric
        edge_key_fwd = f"shared_{shared.source_id}_{shared.target_id}_{shared.edge_type.value}"
        edge_key_rev = f"shared_{shared.target_id}_{shared.source_id}_{shared.edge_type.value}"
        
        attr = {
            "edge_type": shared.edge_type.value,
            "confidence": shared.confidence,
            "first_seen": shared.first_seen,
            "last_seen": shared.last_seen,
            "metadata": shared.metadata,
        }
        self.graph.add_edge(shared.source_id, shared.target_id, key=edge_key_fwd, **attr)
        self.graph.add_edge(shared.target_id, shared.source_id, key=edge_key_rev, **attr)

    def get_account(self, node_id: str) -> Optional[AccountNode]:
        return self.account_nodes.get(node_id)

    def get_metadata(self, node_id: str) -> Optional[MetadataNode]:
        return self.metadata_nodes.get(node_id)

    def get_all_accounts(self) -> List[AccountNode]:
        return list(self.account_nodes.values())

    def get_all_metadata(self) -> List[MetadataNode]:
        return list(self.metadata_nodes.values())

    def update_risk_scores(self, propagated_scores: Dict[str, float]) -> None:
        """Update propagated risk scores on both NetworkX graph and Pydantic models."""
        for node_id, p_score in propagated_scores.items():
            if node_id in self.graph.nodes:
                self.graph.nodes[node_id]["propagated_risk_score"] = float(p_score)
            if node_id in self.account_nodes:
                self.account_nodes[node_id].propagated_risk_score = float(p_score)
                if p_score >= 0.75:
                    self.account_nodes[node_id].is_flagged = True
                    if "high_propagated_risk" not in self.account_nodes[node_id].tags:
                        self.account_nodes[node_id].tags.append("high_propagated_risk")

    def get_funds_flow_digraph(self) -> nx.DiGraph:
        """Extract a simplified DiGraph containing only accounts and transfer edges

        with aggregated transaction weights (for cycle and flow detection).
        """
        flow_graph = nx.DiGraph()
        for acc_id, acc in self.account_nodes.items():
            flow_graph.add_node(acc_id, **self.graph.nodes[acc_id])

        for transfer in self.transfers:
            if flow_graph.has_edge(transfer.source_id, transfer.target_id):
                flow_graph[transfer.source_id][transfer.target_id]["weight"] += transfer.amount
                flow_graph[transfer.source_id][transfer.target_id]["count"] += 1
                flow_graph[transfer.source_id][transfer.target_id]["tx_ids"].append(transfer.transaction_id)
            else:
                flow_graph.add_edge(
                    transfer.source_id,
                    transfer.target_id,
                    weight=transfer.amount,
                    count=1,
                    tx_ids=[transfer.transaction_id],
                )
        return flow_graph

    def get_bipartite_entity_graph(self) -> nx.Graph:
        """Extract an undirected graph containing Account and Metadata anchor nodes

        connected via SHARED_* edges (for connected component Sybil resolution).
        """
        bipartite_g = nx.Graph()
        for acc_id in self.account_nodes:
            bipartite_g.add_node(acc_id, bipartite=0, node_type=NodeType.ACCOUNT.value)
        for meta_id, meta in self.metadata_nodes.items():
            bipartite_g.add_node(meta_id, bipartite=1, node_type=meta.entity_type.value)

        for edge in self.shared_edges:
            bipartite_g.add_edge(
                edge.source_id,
                edge.target_id,
                edge_type=edge.edge_type.value,
                confidence=edge.confidence,
            )
        return bipartite_g

    def get_node_forensics(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve comprehensive forensic 1-hop and 2-hop detail for a selected node."""
        if node_id not in self.graph.nodes:
            return None

        node_data = dict(self.graph.nodes[node_id])
        node_type = node_data.get("node_type", "ACCOUNT")

        # Inbound and outbound transfers
        inbound_transfers = []
        outbound_transfers = []
        linked_anchors = []
        linked_accounts = []

        for u, v, k, d in self.graph.in_edges(node_id, keys=True, data=True):
            if d.get("edge_type") == EdgeType.FUNDS_TRANSFER.value:
                inbound_transfers.append({
                    "from_node": u,
                    "from_label": self.graph.nodes[u].get("label", u),
                    "amount": d.get("amount", 0.0),
                    "timestamp": d.get("timestamp"),
                    "tx_id": d.get("transaction_id"),
                })

        for u, v, k, d in self.graph.out_edges(node_id, keys=True, data=True):
            if d.get("edge_type") == EdgeType.FUNDS_TRANSFER.value:
                outbound_transfers.append({
                    "to_node": v,
                    "to_label": self.graph.nodes[v].get("label", v),
                    "amount": d.get("amount", 0.0),
                    "timestamp": d.get("timestamp"),
                    "tx_id": d.get("transaction_id"),
                })
            elif str(d.get("edge_type", "")).startswith("SHARED_"):
                target_data = self.graph.nodes[v]
                anchor_type = target_data.get("node_type", "UNKNOWN")
                if anchor_type != NodeType.ACCOUNT.value:
                    linked_anchors.append({
                        "anchor_id": v,
                        "anchor_label": target_data.get("label", v),
                        "anchor_type": anchor_type,
                        "relationship": d.get("edge_type"),
                        "confidence": d.get("confidence", 1.0),
                    })
                else:
                    linked_accounts.append({
                        "account_id": v,
                        "account_label": target_data.get("label", v),
                        "relationship": d.get("edge_type"),
                    })

        total_inflow = sum(t["amount"] for t in inbound_transfers)
        total_outflow = sum(t["amount"] for t in outbound_transfers)

        return {
            "node_id": node_id,
            "node_type": node_type,
            "attributes": node_data,
            "inbound_transfers": inbound_transfers,
            "outbound_transfers": outbound_transfers,
            "total_inflow": total_inflow,
            "total_outflow": total_outflow,
            "net_flow": total_inflow - total_outflow,
            "linked_anchors": linked_anchors,
            "linked_accounts": linked_accounts,
            "degree": self.graph.degree(node_id),
        }

    def to_visjs_payload(self) -> Dict[str, Any]:
        """Convert the heterogeneous graph to Vis.js Network nodes and edges format

        with rich fintech styling, shapes, colors, and interactive metadata tooltips.
        """
        vis_nodes = []
        vis_edges = []

        # Color and Shape mappings
        type_palette = {
            NodeType.ACCOUNT.value: {
                "shape": "dot",
                "color_base": "#06b6d4",       # Cyan
                "color_border": "#0891b2",
                "color_high_risk": "#ef4444",   # Crimson
                "color_med_risk": "#f59e0b",    # Amber
            },
            NodeType.DEVICE.value: {
                "shape": "diamond",
                "color_base": "#a855f7",        # Purple
                "color_border": "#9333ea",
                "color_high_risk": "#ec4899",
                "color_med_risk": "#c084fc",
            },
            NodeType.BANK_ACCOUNT.value: {
                "shape": "square",
                "color_base": "#10b981",        # Emerald
                "color_border": "#059669",
                "color_high_risk": "#f43f5e",
                "color_med_risk": "#34d399",
            },
            NodeType.IP_ADDRESS.value: {
                "shape": "hexagon",
                "color_base": "#f97316",        # Orange
                "color_border": "#ea580c",
                "color_high_risk": "#dc2626",
                "color_med_risk": "#fb923c",
            },
            NodeType.EMAIL.value: {
                "shape": "triangle",
                "color_base": "#38bdf8",        # Sky blue
                "color_border": "#0284c7",
                "color_high_risk": "#ef4444",
                "color_med_risk": "#7dd3fc",
            },
            NodeType.SSN.value: {
                "shape": "star",
                "color_base": "#e11d48",        # Rose
                "color_border": "#be123c",
                "color_high_risk": "#9f1239",
                "color_med_risk": "#f43f5e",
            },
        }

        # Build Vis.js nodes
        for node_id, data in self.graph.nodes(data=True):
            node_type = data.get("node_type", NodeType.ACCOUNT.value)
            cfg = type_palette.get(node_type, type_palette[NodeType.ACCOUNT.value])

            risk = max(data.get("risk_score", 0.0), data.get("propagated_risk_score", 0.0))
            is_flagged = data.get("is_flagged", False) or risk >= 0.75

            # Determine background and border colors
            if is_flagged or risk >= 0.75:
                bg_color = "#ef4444"
                border_color = "#b91c1c"
                highlight_bg = "#dc2626"
            elif risk >= 0.40:
                bg_color = "#f59e0b"
                border_color = "#d97706"
                highlight_bg = "#b45309"
            else:
                bg_color = cfg["color_base"]
                border_color = cfg["color_border"]
                highlight_bg = "#38bdf8"

            degree = self.graph.degree(node_id)
            node_size = max(18, min(48, int(18 + (degree * 2.5) + (risk * 20))))

            # Formulate HTML tooltip
            holder = data.get("holder_name", "")
            tags = ", ".join(data.get("tags", [])) if data.get("tags") else "None"
            tooltip_html = (
                f"<div style='font-family: monospace; font-size: 12px; padding: 6px; color: #f8fafc; background: #0f172a; border: 1px solid #334155; border-radius: 6px;'>"
                f"<b>ID:</b> {node_id}<br/>"
                f"<b>Type:</b> {node_type}<br/>"
                + (f"<b>Holder:</b> {holder}<br/>" if holder else "")
                + f"<b>Base Risk:</b> {data.get('risk_score', 0.0):.2f}<br/>"
                + f"<b>Diffusion Risk:</b> {data.get('propagated_risk_score', 0.0):.2f}<br/>"
                + f"<b>Flagged:</b> {'YES' if is_flagged else 'NO'}<br/>"
                + f"<b>Tags:</b> {tags}<br/>"
                f"<b>Degree:</b> {degree}"
                f"</div>"
            )

            vis_nodes.append({
                "id": node_id,
                "label": data.get("label", node_id),
                "title": tooltip_html,
                "shape": cfg["shape"],
                "size": node_size,
                "color": {
                    "background": bg_color,
                    "border": border_color,
                    "highlight": {
                        "background": highlight_bg,
                        "border": "#ffffff",
                    },
                },
                "borderWidth": 2 if not is_flagged else 4,
                "font": {
                    "color": "#f1f5f9",
                    "size": 12,
                    "face": "system-ui, -apple-system, sans-serif",
                },
                "node_type": node_type,
                "risk_score": round(risk, 3),
                "is_flagged": is_flagged,
            })

        # Build Vis.js edges (avoid rendering duplicate reversed shared edges)
        seen_shared_pairs: Set[Tuple[str, str, str]] = set()

        for u, v, k, data in self.graph.edges(keys=True, data=True):
            edge_type = data.get("edge_type", EdgeType.FUNDS_TRANSFER.value)

            if edge_type == EdgeType.FUNDS_TRANSFER.value:
                amount = data.get("amount", 0.0)
                edge_risk = data.get("risk_score", 0.0)
                is_high_risk = edge_risk > 0.6 or self.graph.nodes[u].get("is_flagged") or self.graph.nodes[v].get("is_flagged")
                
                edge_color = "#ef4444" if is_high_risk else "#38bdf8"
                edge_width = max(1.5, min(6.0, 1.5 + (amount / 15000.0) * 4))

                vis_edges.append({
                    "id": k,
                    "from": u,
                    "to": v,
                    "label": f"${amount:,.0f}",
                    "arrows": {
                        "to": {
                            "enabled": True,
                            "scaleFactor": 0.8,
                        }
                    },
                    "color": {
                        "color": edge_color,
                        "highlight": "#ffffff",
                        "opacity": 0.85,
                    },
                    "width": edge_width,
                    "smooth": {"type": "curvedCW", "roundness": 0.15},
                    "edge_type": edge_type,
                    "amount": amount,
                    "title": f"Transfer: ${amount:,.2f} | TxID: {data.get('transaction_id')} | Time: {data.get('timestamp')}",
                    "font": {
                        "color": "#cbd5e1",
                        "size": 10,
                        "align": "middle",
                        "background": "#0f172a",
                    },
                })
            else:
                pair_key = tuple(sorted([u, v])) + (edge_type,)
                if pair_key in seen_shared_pairs:
                    continue
                seen_shared_pairs.add(pair_key)

                conf = data.get("confidence", 1.0)
                anchor_type = self.graph.nodes[v].get("node_type", "") if self.graph.nodes[u].get("node_type") == NodeType.ACCOUNT.value else self.graph.nodes[u].get("node_type", "")

                color_map = {
                    NodeType.DEVICE.value: "#c084fc",
                    NodeType.BANK_ACCOUNT.value: "#34d399",
                    NodeType.IP_ADDRESS.value: "#fb923c",
                    NodeType.EMAIL.value: "#67e8f9",
                    NodeType.SSN.value: "#f43f5e",
                }
                edge_color = color_map.get(anchor_type, "#94a3b8")

                vis_edges.append({
                    "id": f"shared_{u}_{v}_{edge_type}",
                    "from": u,
                    "to": v,
                    "dashes": [4, 4],
                    "color": {
                        "color": edge_color,
                        "highlight": "#ffffff",
                        "opacity": 0.6,
                    },
                    "width": 1.5,
                    "edge_type": edge_type,
                    "title": f"Shared Anchor: {edge_type} (Conf: {conf * 100:.0f}%)",
                })

        return {
            "nodes": vis_nodes,
            "edges": vis_edges,
            "node_count": len(vis_nodes),
            "edge_count": len(vis_edges),
        }
