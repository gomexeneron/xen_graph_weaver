"""Schemas for graph nodes and edges."""

from enum import Enum
from typing import Any, Dict, List, Optional
from models.base import BaseModel, Field


class NodeType(str, Enum):
    ACCOUNT = "ACCOUNT"
    DEVICE = "DEVICE"
    BANK_ACCOUNT = "BANK_ACCOUNT"
    IP_ADDRESS = "IP_ADDRESS"
    EMAIL = "EMAIL"
    SSN = "SSN"


class EdgeType(str, Enum):
    FUNDS_TRANSFER = "FUNDS_TRANSFER"
    SHARED_DEVICE = "SHARED_DEVICE"
    SHARED_BANK = "SHARED_BANK"
    SHARED_IP = "SHARED_IP"
    SHARED_EMAIL = "SHARED_EMAIL"
    SHARED_SSN = "SHARED_SSN"


class AccountNode(BaseModel):
    node_id: str = Field(..., description="Unique ID for account, e.g., ACC-1092")
    label: str = Field(..., description="Display label")
    account_number: str = Field(..., description="Brokerage or checking account number")
    holder_name: str = Field(..., description="Entity or individual name")
    entity_type: NodeType = Field(default=NodeType.ACCOUNT)
    broker: str = Field(default="Alpaca Brokerage")
    risk_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Base risk score [0, 1]")
    propagated_risk_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Score after risk diffusion")
    is_flagged: bool = Field(default=False, description="Manual or heuristic AML compliance flag")
    tags: List[str] = Field(default_factory=list, description="Labels like 'mule', 'funnel', 'kyc_fail'")
    created_at: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MetadataNode(BaseModel):
    node_id: str = Field(..., description="Unique ID for metadata anchor, e.g., DEV-9938 or IP-192.168.1.1")
    label: str = Field(..., description="Human readable label")
    entity_type: NodeType = Field(..., description="Metadata anchor type (DEVICE, IP_ADDRESS, BANK_ACCOUNT, etc.)")
    value: str = Field(..., description="Raw attribute value (e.g. fingerprint, routing+acc, IP)")
    risk_weight: float = Field(default=0.1, ge=0.0, le=1.0, description="Anchor contamination factor")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TransferEdge(BaseModel):
    source_id: str = Field(..., description="Originating account ID")
    target_id: str = Field(..., description="Destination account ID")
    amount: float = Field(..., gt=0.0, description="Transaction transfer amount")
    timestamp: str = Field(..., description="ISO 8601 timestamp")
    transaction_id: str = Field(..., description="Unique transaction ID")
    edge_type: EdgeType = Field(default=EdgeType.FUNDS_TRANSFER)
    currency: str = Field(default="USD")
    risk_score: float = Field(default=0.0, ge=0.0, le=1.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SharedEdge(BaseModel):
    source_id: str = Field(..., description="Account node ID")
    target_id: str = Field(..., description="Metadata anchor node ID or linked account ID")
    edge_type: EdgeType = Field(..., description="Type of shared relationship")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence in link association")
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
