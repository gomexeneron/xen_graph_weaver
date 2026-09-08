"""Data structures for forensic summaries, cluster metrics, and ring detection reports."""

from typing import Any, Dict, List, Optional
from models.base import BaseModel, Field


class ClusterMetric(BaseModel):
    cluster_id: str = Field(..., description="Unique ID of the Sybil or entity cluster")
    size: int = Field(..., description="Number of member account nodes")
    cluster_type: str = Field(default="shared_anchor_sybil", description="Type of cluster")
    density: float = Field(default=0.0, description="Internal subgraph edge density")
    accounts: List[str] = Field(default_factory=list, description="Account node IDs in this cluster")
    shared_anchors: List[str] = Field(default_factory=list, description="Metadata anchor IDs (Device, Bank, IP) binding the cluster")
    risk_level: str = Field(default="MEDIUM", description="LOW, MEDIUM, HIGH, CRITICAL")
    sybil_probability: float = Field(default=0.0, ge=0.0, le=1.0, description="Estimated probability of coordinated Sybil operation")
    primary_anchor: Optional[str] = None
    description: str = Field(default="", description="Forensic narrative explaining the linkage")


class RingReport(BaseModel):
    ring_id: str = Field(..., description="Unique ring identifier, e.g., RING-CYCLE-01")
    ring_type: str = Field(..., description="layering_cycle, fan_in_mule, fan_out_mule, sybil_ring")
    account_count: int = Field(..., description="Total accounts involved")
    member_ids: List[str] = Field(default_factory=list, description="Account and anchor node IDs involved")
    transaction_volume: float = Field(default=0.0, description="Cumulative financial volume moving through the ring")
    risk_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Calculated composite risk score")
    cycle_path: Optional[List[str]] = Field(default=None, description="Ordered node path for cycles or flows")
    evidence: List[str] = Field(default_factory=list, description="List of forensic observations / red flags")
    severity: str = Field(default="HIGH", description="LOW, MEDIUM, HIGH, CRITICAL")
    recommended_action: str = Field(default="FREEZE_AND_SAR", description="Recommended compliance protocol")


class CentralityTopNode(BaseModel):
    node_id: str
    label: str
    entity_type: str
    degree: int
    in_degree: int
    out_degree: int
    betweenness_centrality: float
    pagerank: float
    risk_score: float
    propagated_risk_score: float
    is_flagged: bool


class GraphSummary(BaseModel):
    total_nodes: int
    total_edges: int
    account_nodes_count: int
    metadata_nodes_count: int
    transfer_edges_count: int
    shared_edges_count: int
    total_transaction_volume: float
    average_degree: float
    graph_density: float
    connected_components_count: int
    high_risk_accounts_count: int
    generated_at: str
    sybil_clusters: List[ClusterMetric] = Field(default_factory=list)
    detected_rings: List[RingReport] = Field(default_factory=list)
    top_central_nodes: List[CentralityTopNode] = Field(default_factory=list)
    top_risk_nodes: List[Dict[str, Any]] = Field(default_factory=list)
    executive_narrative: str = Field(default="", description="Executive markdown summary for compliance officers")
