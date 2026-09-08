"""Personalized PageRank and Neighbor Risk Contamination Diffusion Algorithms."""

from typing import Dict, Optional, Tuple
import networkx as nx

from models.entity import NodeType, EdgeType
from .graph_builder import HeterogeneousGraphBuilder


class RiskPropagator:
    """Propagates AML and compliance risk scores across the heterogeneous graph

    using Personalized PageRank and Iterative Neighbor Contamination Diffusion.
    """

    def __init__(
        self,
        builder: HeterogeneousGraphBuilder,
        damping_factor: float = 0.85,
        diffusion_alpha: float = 0.65,
        max_iterations: int = 30,
        convergence_tol: float = 1e-5,
    ):
        self.builder = builder
        self.damping_factor = damping_factor
        self.diffusion_alpha = diffusion_alpha
        self.max_iterations = max_iterations
        self.convergence_tol = convergence_tol

    def compute_personalized_pagerank(
        self,
        seed_scores: Optional[Dict[str, float]] = None,
    ) -> Dict[str, float]:
        """Compute Personalized PageRank (PPR) weighted towards known flagged / high-risk seed accounts.

        Returns normalized PPR dictionary keyed by node ID.
        """
        g = self.builder.graph
        if len(g.nodes) == 0:
            return {}

        # Create a single weighted DiGraph for PageRank computation
        flow_g = nx.DiGraph()
        for n, data in g.nodes(data=True):
            flow_g.add_node(n)

        for u, v, k, d in g.edges(keys=True, data=True):
            edge_type = d.get("edge_type")
            if edge_type == EdgeType.FUNDS_TRANSFER.value:
                # Financial transfers carry flow weight
                amount = float(d.get("amount", 100.0))
                weight = 1.0 + (amount / 1000.0)
                if flow_g.has_edge(u, v):
                    flow_g[u][v]["weight"] += weight
                else:
                    flow_g.add_edge(u, v, weight=weight)
            else:
                # Shared metadata edges allow bidirectional risk leakage
                conf = float(d.get("confidence", 0.8))
                weight = 0.5 * conf
                if flow_g.has_edge(u, v):
                    flow_g[u][v]["weight"] += weight
                else:
                    flow_g.add_edge(u, v, weight=weight)

        # Build personalization vector
        personalization = {}
        total_seed_weight = 0.0

        for n, data in g.nodes(data=True):
            if seed_scores and n in seed_scores:
                score = seed_scores[n]
            else:
                score = data.get("risk_score", 0.0)
                if data.get("is_flagged", False):
                    score = max(score, 0.9)

            # Assign small baseline epsilon so unseeded nodes participate
            p_val = score if score > 0 else 0.01
            personalization[n] = p_val
            total_seed_weight += p_val

        # Normalize personalization vector
        if total_seed_weight > 0:
            for n in personalization:
                personalization[n] /= total_seed_weight
        else:
            uniform = 1.0 / len(g.nodes)
            for n in personalization:
                personalization[n] = uniform

        try:
            ppr = nx.pagerank(
                flow_g,
                alpha=self.damping_factor,
                personalization=personalization,
                weight="weight",
                max_iter=200,
                tol=1e-6,
            )
        except Exception:
            # Fallback uniform pagerank if disconnected or convergence error
            ppr = {n: 1.0 / len(g.nodes) for n in g.nodes}

        # Rescale PPR values to [0, 1] relative to maximum PPR observed
        max_ppr = max(ppr.values()) if ppr else 1.0
        if max_ppr > 0:
            return {k: v / max_ppr for k, v in ppr.items()}
        return ppr

    def compute_neighbor_contamination(
        self,
        base_scores: Optional[Dict[str, float]] = None,
    ) -> Dict[str, float]:
        """Perform iterative neighbor risk diffusion across transfer and shared metadata links.

        R^(t+1)(v) = (1 - alpha) * R^(0)(v) + alpha * sum(W(u, v) * R^(t)(u))
        """
        g = self.builder.graph
        nodes = list(g.nodes)
        if not nodes:
            return {}

        # Initial scores
        r_0: Dict[str, float] = {}
        for n in nodes:
            data = g.nodes[n]
            if base_scores and n in base_scores:
                r_0[n] = float(base_scores[n])
            else:
                score = float(data.get("risk_score", 0.0))
                if data.get("is_flagged", False):
                    score = max(score, 0.95)
                r_0[n] = score

        r_curr = dict(r_0)

        # Precompute incoming edge transition weights for each node
        # For a node v, calculate transmission weight from predecessor u
        in_weights: Dict[str, Dict[str, float]] = {n: {} for n in nodes}
        for v in nodes:
            total_w = 0.0
            # Check all incoming edges to v
            for u, _, k, d in g.in_edges(v, keys=True, data=True):
                edge_type = d.get("edge_type")
                if edge_type == EdgeType.FUNDS_TRANSFER.value:
                    # Transfer amount gives strong risk transmission
                    amount = float(d.get("amount", 100.0))
                    w = 1.0 + (amount / 2000.0)
                else:
                    conf = float(d.get("confidence", 0.8))
                    w = 0.7 * conf

                in_weights[v][u] = in_weights[v].get(u, 0.0) + w
                total_w += w

            # Normalize incoming weights for node v
            if total_w > 0:
                for u in in_weights[v]:
                    in_weights[v][u] /= total_w

        # Iterative diffusion
        for _ in range(self.max_iterations):
            r_next: Dict[str, float] = {}
            max_delta = 0.0

            for v in nodes:
                diffused_neighbor_sum = sum(
                    in_weights[v][u] * r_curr[u] for u in in_weights[v]
                )
                
                # Blend base score and neighbor contamination
                new_score = (1.0 - self.diffusion_alpha) * r_0[v] + self.diffusion_alpha * diffused_neighbor_sum
                # Anchor risk cannot drop below base risk score
                new_score = max(new_score, r_0[v] * 0.85)
                new_score = min(1.0, max(0.0, new_score))

                delta = abs(new_score - r_curr[v])
                if delta > max_delta:
                    max_delta = delta
                r_next[v] = new_score

            r_curr = r_next
            if max_delta < self.convergence_tol:
                break

        return r_curr

    def propagate_and_update(self) -> Dict[str, float]:
        """Runs both Personalized PageRank and Contamination Diffusion,

        combines them into an ensemble propagated risk score, and updates the graph.
        """
        ppr_scores = self.compute_personalized_pagerank()
        diffusion_scores = self.compute_neighbor_contamination()

        combined_scores: Dict[str, float] = {}
        for n in self.builder.graph.nodes:
            base_score = self.builder.graph.nodes[n].get("risk_score", 0.0)
            ppr = ppr_scores.get(n, 0.0)
            diff = diffusion_scores.get(n, 0.0)

            # Ensemble score: 50% Contamination Diffusion, 30% PPR, 20% Base Risk
            ens = (0.50 * diff) + (0.30 * ppr) + (0.20 * base_score)
            
            # If flagged, enforce high floor
            if self.builder.graph.nodes[n].get("is_flagged", False):
                ens = max(ens, 0.85)

            combined_scores[n] = round(min(1.0, max(0.0, ens)), 4)

        self.builder.update_risk_scores(combined_scores)
        return combined_scores
