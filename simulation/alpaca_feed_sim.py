"""Ingests mock Alpaca Broker API and Plaid payloads with 3 embedded synthetic fraud rings."""

from datetime import datetime, timezone, timedelta
import random
from typing import Tuple

from models.entity import (
    AccountNode,
    MetadataNode,
    TransferEdge,
    SharedEdge,
    NodeType,
    EdgeType,
)
from engine.graph_builder import HeterogeneousGraphBuilder


class AlpacaFeedSimulator:
    """Simulates real-world Alpaca Brokerage account feeds, transaction streams,

    and Plaid bank/device link payloads containing 3 distinct AML forensic rings.
    """

    def __init__(self, seed: int = 42):
        self.seed = seed
        random.seed(seed)

    def populate(self, builder: HeterogeneousGraphBuilder) -> HeterogeneousGraphBuilder:
        """Populate the graph builder with benign accounts and 3 embedded forensic rings."""
        now = datetime.now(timezone.utc)

        # ---------------------------------------------------------
        # RING 1: Layering Cycle Ring (Circular Transfer Flow)
        # ---------------------------------------------------------
        cyc_accounts = [
            AccountNode(
                node_id="ACC-CYC-01",
                label="Apex Vault (ACC-CYC-01)",
                account_number="ALP-90210-A",
                holder_name="Vanguard Global Syndicate",
                broker="Alpaca Trading",
                risk_score=0.88,
                is_flagged=True,
                tags=["layering_origin", "finra_inquiry"],
                created_at=(now - timedelta(days=120)).isoformat(),
                metadata={"jurisdiction": "Delaware", "kyc_status": "HIGH_RISK_PASSED"},
            ),
            AccountNode(
                node_id="ACC-CYC-02",
                label="Nordic Shell (ACC-CYC-02)",
                account_number="ALP-90210-B",
                holder_name="Nordic Horizon Capital",
                broker="Alpaca Trading",
                risk_score=0.45,
                is_flagged=False,
                tags=["layering_hop_1"],
                created_at=(now - timedelta(days=110)).isoformat(),
            ),
            AccountNode(
                node_id="ACC-CYC-03",
                label="Zephyr Trade (ACC-CYC-03)",
                account_number="ALP-90210-C",
                holder_name="Zephyr Liquidity Partners",
                broker="Alpaca Trading",
                risk_score=0.40,
                is_flagged=False,
                tags=["layering_hop_2"],
                created_at=(now - timedelta(days=100)).isoformat(),
            ),
            AccountNode(
                node_id="ACC-CYC-04",
                label="Helios Escrow (ACC-CYC-04)",
                account_number="ALP-90210-D",
                holder_name="Helios Custody Trust",
                broker="Alpaca Trading",
                risk_score=0.50,
                is_flagged=False,
                tags=["layering_hop_3"],
                created_at=(now - timedelta(days=90)).isoformat(),
            ),
        ]
        for acc in cyc_accounts:
            builder.add_account_node(acc)

        # Circular transfers with amount chipping / fee retention
        cyc_transfers = [
            ("ACC-CYC-01", "ACC-CYC-02", 48500.0, "TX-CYC-001", 10),
            ("ACC-CYC-02", "ACC-CYC-03", 46800.0, "TX-CYC-002", 8),
            ("ACC-CYC-03", "ACC-CYC-04", 45200.0, "TX-CYC-003", 6),
            ("ACC-CYC-04", "ACC-CYC-01", 44000.0, "TX-CYC-004", 4),
        ]
        for src, tgt, amt, tx_id, days_ago in cyc_transfers:
            builder.add_transfer(
                TransferEdge(
                    source_id=src,
                    target_id=tgt,
                    amount=amt,
                    currency="USD",
                    timestamp=(now - timedelta(days=days_ago)).isoformat(),
                    transaction_id=tx_id,
                    risk_score=0.85,
                    metadata={"wire_type": "ALPACA_INTERNAL_JOURNAL", "memo": "Liquidity rebalancing"},
                )
            )

        # Metadata for Ring 1
        cyc_ip = MetadataNode(
            node_id="IP-185.220.101.5",
            label="Tor Exit / VPN Relay",
            entity_type=NodeType.IP_ADDRESS,
            value="185.220.101.5",
            risk_weight=0.75,
            metadata={"isp": "M247 Ltd", "country": "NL", "is_tor": True},
        )
        builder.add_metadata_node(cyc_ip)
        for acc in cyc_accounts:
            builder.add_shared_edge(
                SharedEdge(
                    source_id=acc.node_id,
                    target_id=cyc_ip.node_id,
                    edge_type=EdgeType.SHARED_IP,
                    confidence=0.92,
                    first_seen=(now - timedelta(days=30)).isoformat(),
                )
            )

        # ---------------------------------------------------------
        # RING 2: Mule Aggregation Network (Fan-In Funnel to Sink)
        # ---------------------------------------------------------
        funnel_acc = AccountNode(
            node_id="ACC-FUNNEL-01",
            label="Titan Aggregator (ACC-FUNNEL-01)",
            account_number="ALP-88102-FUNNEL",
            holder_name="Titan Alpha Clearing LLC",
            broker="Alpaca Trading",
            risk_score=0.70,
            is_flagged=False,
            tags=["mule_funnel", "high_velocity_sink"],
            created_at=(now - timedelta(days=45)).isoformat(),
        )
        builder.add_account_node(funnel_acc)

        sink_acc = AccountNode(
            node_id="ACC-SINK-OFFSHORE",
            label="Offshore Exit (ACC-SINK-OFFSHORE)",
            account_number="ALP-99301-EXT",
            holder_name="Pacific Meridian Capital Ltd",
            broker="External International",
            risk_score=0.90,
            is_flagged=True,
            tags=["offshore_sink", "high_risk_jurisdiction"],
            created_at=(now - timedelta(days=180)).isoformat(),
        )
        builder.add_account_node(sink_acc)

        mule_names = [
            ("ACC-MULE-01", "Marcus Brody", 9400.0, True),
            ("ACC-MULE-02", "Elena Rostova", 8900.0, False),
            ("ACC-MULE-03", "Chen Wei", 9200.0, False),
            ("ACC-MULE-04", "Sarah Jenkins", 8750.0, False),
            ("ACC-MULE-05", "Dmitri Volkov", 9500.0, True),
        ]

        for m_id, m_name, amt, is_flg in mule_names:
            m_acc = AccountNode(
                node_id=m_id,
                label=f"Mule: {m_name.split()[0]} ({m_id})",
                account_number=f"ALP-MULE-{m_id[-2:]}",
                holder_name=m_name,
                broker="Alpaca Trading",
                risk_score=0.75 if is_flg else 0.35,
                is_flagged=is_flg,
                tags=["mule_depositor", "smurfing_structuring"],
                created_at=(now - timedelta(days=20)).isoformat(),
            )
            builder.add_account_node(m_acc)

            # Mule -> Funnel transfer
            builder.add_transfer(
                TransferEdge(
                    source_id=m_id,
                    target_id=funnel_acc.node_id,
                    amount=amt,
                    currency="USD",
                    timestamp=(now - timedelta(days=random.randint(2, 5))).isoformat(),
                    transaction_id=f"TX-MULE-IN-{m_id[-2:]}",
                    risk_score=0.78,
                    metadata={"channel": "PLAID_ACH_INSTANT", "structuring_flag": True},
                )
            )

        # Funnel -> Offshore Sink transfer
        builder.add_transfer(
            TransferEdge(
                source_id=funnel_acc.node_id,
                target_id=sink_acc.node_id,
                amount=44500.0,
                currency="USD",
                timestamp=(now - timedelta(days=1)).isoformat(),
                transaction_id="TX-FUNNEL-OUT-99",
                risk_score=0.92,
                metadata={"channel": "SWIFT_WIRE", "beneficiary_bank": "Valletta Bank Malta"},
            )
        )

        # Shared device between mules 1 and 2
        mule_dev = MetadataNode(
            node_id="DEV-MULE-RIG-77",
            label="Hardware Emulator Device",
            entity_type=NodeType.DEVICE,
            value="FP-ANDROID-EMU-NOX-77",
            risk_weight=0.80,
            metadata={"os": "Android 12 Emulated", "canvas_hash": "a9f8721c00e1"},
        )
        builder.add_metadata_node(mule_dev)
        builder.add_shared_edge(
            SharedEdge(
                source_id="ACC-MULE-01",
                target_id=mule_dev.node_id,
                edge_type=EdgeType.SHARED_DEVICE,
                confidence=0.98,
            )
        )
        builder.add_shared_edge(
            SharedEdge(
                source_id="ACC-MULE-02",
                target_id=mule_dev.node_id,
                edge_type=EdgeType.SHARED_DEVICE,
                confidence=0.98,
            )
        )

        # ---------------------------------------------------------
        # RING 3: Sybil Multi-Accounting Ring (Shared Plaid & Device)
        # ---------------------------------------------------------
        shared_plaid_bank = MetadataNode(
            node_id="BANK-PLAID-CHASE-9912",
            label="Plaid Link: Chase Checking *9912",
            entity_type=NodeType.BANK_ACCOUNT,
            value="ROUTING:021000021-ACC:991288341",
            risk_weight=0.65,
            metadata={"institution": "JPMorgan Chase", "plaid_item_id": "item_plaid_chase_live_9912"},
        )
        builder.add_metadata_node(shared_plaid_bank)

        shared_device_sybil = MetadataNode(
            node_id="DEV-IPHONE-PRO-881",
            label="Shared iPhone 15 Pro Max",
            entity_type=NodeType.DEVICE,
            value="FP-IOS-A17-UUID-8812-BF9",
            risk_weight=0.70,
            metadata={"device_model": "iPhone 15,3", "ios_version": "17.4.1"},
        )
        builder.add_metadata_node(shared_device_sybil)

        shared_email_domain = MetadataNode(
            node_id="EMAIL-DOMAIN-TEMP-MAIL",
            label="Shared Domain: @ghosttrade.cc",
            entity_type=NodeType.EMAIL,
            value="*@ghosttrade.cc",
            risk_weight=0.55,
            metadata={"mx_record": "disposable_mail_server"},
        )
        builder.add_metadata_node(shared_email_domain)

        sybil_members = [
            ("ACC-SYBIL-01", "Aaron K. Vance", 0.60),
            ("ACC-SYBIL-02", "Bella T. Sterling", 0.55),
            ("ACC-SYBIL-03", "Carter J. Ross", 0.50),
            ("ACC-SYBIL-04", "Daisy M. Collins", 0.50),
            ("ACC-SYBIL-05", "Evan P. Knight", 0.55),
            ("ACC-SYBIL-06", "Fiona G. Ward", 0.60),
            ("ACC-SYBIL-07", "Gage H. Fisher", 0.65),
        ]

        for s_id, s_name, r_score in sybil_members:
            s_acc = AccountNode(
                node_id=s_id,
                label=f"Puppet: {s_name.split()[0]} ({s_id})",
                account_number=f"ALP-SYB-{s_id[-2:]}",
                holder_name=s_name,
                broker="Alpaca Trading",
                risk_score=r_score,
                is_flagged=False,
                tags=["sybil_puppet", "synthetic_id_suspect"],
                created_at=(now - timedelta(days=random.randint(10, 25))).isoformat(),
            )
            builder.add_account_node(s_acc)

            # Bind puppet to shared Plaid bank and Device
            builder.add_shared_edge(
                SharedEdge(
                    source_id=s_id,
                    target_id=shared_plaid_bank.node_id,
                    edge_type=EdgeType.SHARED_BANK,
                    confidence=1.0,
                )
            )
            builder.add_shared_edge(
                SharedEdge(
                    source_id=s_id,
                    target_id=shared_device_sybil.node_id,
                    edge_type=EdgeType.SHARED_DEVICE,
                    confidence=0.95,
                )
            )
            builder.add_shared_edge(
                SharedEdge(
                    source_id=s_id,
                    target_id=shared_email_domain.node_id,
                    edge_type=EdgeType.SHARED_EMAIL,
                    confidence=0.88,
                )
            )

        # Internal transfers between puppets
        builder.add_transfer(
            TransferEdge(
                source_id="ACC-SYBIL-01",
                target_id="ACC-SYBIL-03",
                amount=7500.0,
                currency="USD",
                timestamp=(now - timedelta(days=7)).isoformat(),
                transaction_id="TX-SYB-01",
                risk_score=0.65,
            )
        )
        builder.add_transfer(
            TransferEdge(
                source_id="ACC-SYBIL-02",
                target_id="ACC-SYBIL-05",
                amount=8200.0,
                currency="USD",
                timestamp=(now - timedelta(days=6)).isoformat(),
                transaction_id="TX-SYB-02",
                risk_score=0.65,
            )
        )
        builder.add_transfer(
            TransferEdge(
                source_id="ACC-SYBIL-04",
                target_id="ACC-SYBIL-07",
                amount=6900.0,
                currency="USD",
                timestamp=(now - timedelta(days=5)).isoformat(),
                transaction_id="TX-SYB-03",
                risk_score=0.65,
            )
        )

        # ---------------------------------------------------------
        # BENIGN RETAIL POPULATION (Background Noise)
        # ---------------------------------------------------------
        benign_users = [
            ("ACC-RETAIL-01", "Alice Smith", "BANK-BOA-1102", "DEV-MACBOOK-01", "IP-73.189.44.12"),
            ("ACC-RETAIL-02", "Bob Johnson", "BANK-WELLS-2204", "DEV-PIXEL-02", "IP-24.12.98.55"),
            ("ACC-RETAIL-03", "Clara Martinez", "BANK-CHASE-3305", "DEV-IPAD-03", "IP-68.4.110.2"),
            ("ACC-RETAIL-04", "David Lee", "BANK-CITI-4408", "DEV-WIN-04", "IP-172.56.21.90"),
            ("ACC-RETAIL-05", "Emma Watson", "BANK-SCHWAB-5509", "DEV-MACBOOK-05", "IP-99.88.77.66"),
            ("ACC-RETAIL-06", "Frank Miller", "BANK-FIDELITY-6601", "DEV-SAMSUNG-06", "IP-108.20.14.3"),
            ("ACC-RETAIL-07", "Grace Hopper", "BANK-US-7703", "DEV-LINUX-07", "IP-140.82.112.4"),
            ("ACC-RETAIL-08", "Henry Ford", "BANK-PNC-8806", "DEV-IPHONE-08", "IP-71.200.19.82"),
        ]

        for acc_id, name, b_id, d_id, ip_id in benign_users:
            b_acc = AccountNode(
                node_id=acc_id,
                label=f"Retail: {name.split()[0]} ({acc_id})",
                account_number=f"ALP-RET-{acc_id[-2:]}",
                holder_name=name,
                broker="Alpaca Trading",
                risk_score=round(random.uniform(0.02, 0.15), 3),
                is_flagged=False,
                tags=["retail_investor", "verified_kyc"],
                created_at=(now - timedelta(days=random.randint(60, 300))).isoformat(),
            )
            builder.add_account_node(b_acc)

            # Metadata nodes
            b_bank = MetadataNode(
                node_id=b_id,
                label=f"Bank: {b_id}",
                entity_type=NodeType.BANK_ACCOUNT,
                value=f"PLAID_TOKEN_{b_id}",
                risk_weight=0.05,
            )
            b_dev = MetadataNode(
                node_id=d_id,
                label=f"Device: {d_id}",
                entity_type=NodeType.DEVICE,
                value=f"FP_VERIFIED_{d_id}",
                risk_weight=0.05,
            )
            b_ip = MetadataNode(
                node_id=ip_id,
                label=f"IP: {ip_id}",
                entity_type=NodeType.IP_ADDRESS,
                value=ip_id.replace("IP-", ""),
                risk_weight=0.05,
            )

            builder.add_metadata_node(b_bank)
            builder.add_metadata_node(b_dev)
            builder.add_metadata_node(b_ip)

            builder.add_shared_edge(
                SharedEdge(
                    source_id=acc_id,
                    target_id=b_bank.node_id,
                    edge_type=EdgeType.SHARED_BANK,
                    confidence=1.0,
                )
            )
            builder.add_shared_edge(
                SharedEdge(
                    source_id=acc_id,
                    target_id=b_dev.node_id,
                    edge_type=EdgeType.SHARED_DEVICE,
                    confidence=1.0,
                )
            )
            builder.add_shared_edge(
                SharedEdge(
                    source_id=acc_id,
                    target_id=b_ip.node_id,
                    edge_type=EdgeType.SHARED_IP,
                    confidence=0.90,
                )
            )

        # Ordinary benign transfers
        benign_transfers = [
            ("ACC-RETAIL-01", "ACC-RETAIL-02", 1200.0, "TX-RET-01"),
            ("ACC-RETAIL-03", "ACC-RETAIL-04", 2500.0, "TX-RET-02"),
            ("ACC-RETAIL-05", "ACC-RETAIL-06", 800.0, "TX-RET-03"),
            ("ACC-RETAIL-07", "ACC-RETAIL-08", 3100.0, "TX-RET-04"),
            ("ACC-RETAIL-02", "ACC-RETAIL-05", 1500.0, "TX-RET-05"),
        ]
        for src, tgt, amt, tx_id in benign_transfers:
            builder.add_transfer(
                TransferEdge(
                    source_id=src,
                    target_id=tgt,
                    amount=amt,
                    currency="USD",
                    timestamp=(now - timedelta(days=random.randint(1, 15))).isoformat(),
                    transaction_id=tx_id,
                    risk_score=0.05,
                    metadata={"memo": "P2P Settlement"},
                )
            )

        return builder

    def create_fresh_graph(self) -> HeterogeneousGraphBuilder:
        builder = HeterogeneousGraphBuilder()
        return self.populate(builder)
