/**
 * Xen Graph Weaver - Interactive Compliance GUI & Forensic Engine Client
 */

let network = null;
let nodesDataSet = null;
let edgesDataSet = null;

let allGraphData = { nodes: [], edges: [] };
let detectedRings = [];
let graphSummary = null;
let physicsEnabled = true;
let selectedNodeId = null;

// Initialize on DOM load
document.addEventListener("DOMContentLoaded", () => {
  initEventListeners();
  loadAllData();
});

function initEventListeners() {
  document.getElementById("btnPropagateRisk").addEventListener("click", handleRunRiskDiffusion);
  document.getElementById("btnResetSim").addEventListener("click", handleResetSim);
  document.getElementById("btnShowSummary").addEventListener("click", openSummaryModal);
  document.getElementById("btnCloseModal").addEventListener("click", closeSummaryModal);
  document.getElementById("btnCloseModalBtn").addEventListener("click", closeSummaryModal);
  document.getElementById("btnCopyReport").addEventListener("click", copyReportText);

  document.getElementById("btnTogglePhysics").addEventListener("click", togglePhysics);
  document.getElementById("btnFitCanvas").addEventListener("click", () => network && network.fit({ animation: true }));

  document.getElementById("riskFilter").addEventListener("input", (e) => {
    const val = parseFloat(e.target.value);
    document.getElementById("riskFilterVal").innerText = val.toFixed(2);
    applyFilters();
  });

  document.getElementById("chkMetadata").addEventListener("change", applyFilters);

  document.getElementById("nodeSearch").addEventListener("input", (e) => {
    const query = e.target.value.trim().toLowerCase();
    if (!query || !network || !nodesDataSet) return;

    const matches = nodesDataSet.get({
      filter: (n) => n.id.toLowerCase().includes(query) || (n.label && n.label.toLowerCase().includes(query))
    });

    if (matches.length > 0) {
      network.selectNodes([matches[0].id]);
      network.focus(matches[0].id, { scale: 1.2, animation: true });
      loadNodeInspector(matches[0].id);
    }
  });
}

async function loadAllData() {
  try {
    const [graphRes, summaryRes, ringsRes] = await Promise.all([
      fetch("/api/graph"),
      fetch("/api/summary"),
      fetch("/api/rings"),
    ]);

    allGraphData = await graphRes.json();
    graphSummary = await summaryRes.json();
    detectedRings = await ringsRes.json();

    updateKPIs(graphSummary);
    renderRingCards(detectedRings);
    renderGraph(allGraphData);
  } catch (err) {
    console.error("Failed to load initial data:", err);
  }
}

function updateKPIs(summary) {
  if (!summary) return;
  document.getElementById("kpiEntities").innerText = summary.total_nodes;
  document.getElementById("kpiVolume").innerText = `$${(summary.total_transaction_volume / 1000).toFixed(1)}k`;
  document.getElementById("kpiRings").innerText = summary.detected_rings.length;
  document.getElementById("kpiHighRisk").innerText = summary.high_risk_accounts_count;
  document.getElementById("kpiDensity").innerText = summary.graph_density.toFixed(3);
  document.getElementById("ringBadgeCount").innerText = summary.detected_rings.length;
}

function renderRingCards(rings) {
  const container = document.getElementById("ringContainer");
  container.innerHTML = "";

  if (!rings || rings.length === 0) {
    container.innerHTML = `<div style="padding: 20px; text-align: center; color: var(--text-muted);">No active AML rings detected.</div>`;
    return;
  }

  rings.forEach((ring) => {
    const card = document.createElement("div");
    card.className = "ring-card";
    card.dataset.ringId = ring.ring_id;

    const sevClass = ring.severity === "CRITICAL" ? "sev-critical" : (ring.severity === "HIGH" ? "sev-high" : "sev-medium");
    const ringTypeLabel = ring.ring_type.replace(/_/g, " ").toUpperCase();

    card.innerHTML = `
      <div class="ring-card-header">
        <span class="ring-title">${ring.ring_id}</span>
        <span class="ring-severity ${sevClass}">${ring.severity}</span>
      </div>
      <div class="ring-desc">${ring.evidence[0] || ringTypeLabel}</div>
      <div class="ring-meta">
        <span>${ring.account_count} Nodes</span>
        <span>Vol: $${ring.transaction_volume.toLocaleString()}</span>
      </div>
    `;

    card.addEventListener("click", () => focusOnRing(ring, card));
    container.appendChild(card);
  });
}

function focusOnRing(ring, cardEl) {
  // Highlight selected card
  document.querySelectorAll(".ring-card").forEach((c) => c.classList.remove("selected"));
  if (cardEl) cardEl.classList.add("selected");

  if (!network) return;

  // Filter existing nodes that belong to this ring
  const validNodeIds = ring.member_ids.filter((id) => nodesDataSet.get(id));
  if (validNodeIds.length > 0) {
    network.selectNodes(validNodeIds);
    network.fit({
      nodes: validNodeIds,
      animation: { duration: 900, easingFunction: "easeInOutQuad" },
    });

    // Inspect primary node of the ring
    loadNodeInspector(validNodeIds[0]);
  }
}

function renderGraph(data) {
  const container = document.getElementById("networkCanvas");

  nodesDataSet = new vis.DataSet(data.nodes);
  edgesDataSet = new vis.DataSet(data.edges);

  const options = {
    nodes: {
      borderWidthSelected: 4,
      shadow: {
        enabled: true,
        color: "rgba(0,0,0,0.5)",
        size: 8,
        x: 2,
        y: 2,
      },
    },
    edges: {
      selectionWidth: 3,
      hoverWidth: 2,
      smooth: {
        type: "continuous",
        roundness: 0.2,
      },
    },
    physics: {
      enabled: physicsEnabled,
      solver: "forceAtlas2Based",
      forceAtlas2Based: {
        gravitationalConstant: -55,
        centralGravity: 0.015,
        springLength: 90,
        springConstant: 0.08,
        damping: 0.45,
        avoidOverlap: 0.6,
      },
      stabilization: {
        iterations: 120,
        updateInterval: 25,
      },
    },
    interaction: {
      hover: true,
      tooltipDelay: 150,
      navigationButtons: true,
      keyboard: false,
    },
  };

  network = new vis.Network(container, { nodes: nodesDataSet, edges: edgesDataSet }, options);

  // Canvas events
  network.on("click", (params) => {
    if (params.nodes.length > 0) {
      const clickedId = params.nodes[0];
      loadNodeInspector(clickedId);
    }
  });

  network.on("hoverNode", () => {
    container.style.cursor = "pointer";
  });
  network.on("blurNode", () => {
    container.style.cursor = "default";
  });
}

function applyFilters() {
  const minRisk = parseFloat(document.getElementById("riskFilter").value);
  const showMetadata = document.getElementById("chkMetadata").checked;

  if (!nodesDataSet || !edgesDataSet) return;

  const filteredNodeIds = new Set();

  allGraphData.nodes.forEach((n) => {
    const isAccount = n.node_type === "ACCOUNT";
    if (!showMetadata && !isAccount) return;
    if (n.risk_score >= minRisk) {
      filteredNodeIds.add(n.id);
    }
  });

  // Update DataSet
  const activeNodes = allGraphData.nodes.filter((n) => filteredNodeIds.has(n.id));
  const activeEdges = allGraphData.edges.filter(
    (e) => filteredNodeIds.has(e.from) && filteredNodeIds.has(e.to)
  );

  nodesDataSet.clear();
  edgesDataSet.clear();
  nodesDataSet.add(activeNodes);
  edgesDataSet.add(activeEdges);
}

function togglePhysics() {
  physicsEnabled = !physicsEnabled;
  network.setOptions({ physics: { enabled: physicsEnabled } });
  const btn = document.getElementById("btnTogglePhysics");
  btn.innerText = physicsEnabled ? "⏸ Pause Physics" : "▶ Resume Physics";
}

async function loadNodeInspector(nodeId) {
  selectedNodeId = nodeId;
  const inspector = document.getElementById("inspectorContent");
  inspector.innerHTML = `<div style="padding: 20px; text-align: center; color: var(--text-muted);">Fetching forensic analysis for ${nodeId}...</div>`;

  try {
    const res = await fetch(`/api/node/${encodeURIComponent(nodeId)}`);
    if (!res.ok) throw new Error("Node forensics not found");
    const data = await res.json();

    renderNodeForensics(data);
  } catch (err) {
    inspector.innerHTML = `<div style="color: var(--accent-rose); padding: 14px;">Error: ${err.message}</div>`;
  }
}

function renderNodeForensics(data) {
  const inspector = document.getElementById("inspectorContent");
  const attr = data.attributes || {};
  const risk = Math.max(attr.risk_score || 0.0, attr.propagated_risk_score || 0.0);
  const isFlagged = attr.is_flagged || risk >= 0.75;

  const riskClass = risk >= 0.7 ? "risk-high" : (risk >= 0.4 ? "risk-med" : "risk-low");
  const riskLabel = risk >= 0.7 ? "CRITICAL RISK" : (risk >= 0.4 ? "MEDIUM RISK" : "LOW RISK");

  let inflowsHtml = "";
  if (data.inbound_transfers.length > 0) {
    data.inbound_transfers.forEach((t) => {
      inflowsHtml += `
        <div class="flow-item inflow">
          <div>
            <div style="font-weight: 600;">+ $${t.amount.toLocaleString()}</div>
            <div style="font-size: 10px; color: var(--text-muted);">${t.from_node}</div>
          </div>
          <button class="btn" style="padding: 2px 6px; font-size: 10px;" onclick="focusNodeId('${t.from_node}')">Inspect</button>
        </div>
      `;
    });
  } else {
    inflowsHtml = `<div style="color: var(--text-muted); font-size: 11px;">No inbound fund transfers recorded.</div>`;
  }

  let outflowsHtml = "";
  if (data.outbound_transfers.length > 0) {
    data.outbound_transfers.forEach((t) => {
      outflowsHtml += `
        <div class="flow-item outflow">
          <div>
            <div style="font-weight: 600;">- $${t.amount.toLocaleString()}</div>
            <div style="font-size: 10px; color: var(--text-muted);">${t.to_node}</div>
          </div>
          <button class="btn" style="padding: 2px 6px; font-size: 10px;" onclick="focusNodeId('${t.to_node}')">Inspect</button>
        </div>
      `;
    });
  } else {
    outflowsHtml = `<div style="color: var(--text-muted); font-size: 11px;">No outbound transfers.</div>`;
  }

  let anchorsHtml = "";
  if (data.linked_anchors.length > 0) {
    data.linked_anchors.forEach((a) => {
      anchorsHtml += `
        <div class="anchor-item">
          <div>
            <div style="font-weight: 600; color: var(--accent-purple); font-size: 11px;">${a.anchor_label}</div>
            <div style="font-size: 10px; color: var(--text-muted);">${a.relationship}</div>
          </div>
          <button class="btn" style="padding: 2px 6px; font-size: 10px;" onclick="focusNodeId('${a.anchor_id}')">Focus</button>
        </div>
      `;
    });
  } else {
    anchorsHtml = `<div style="color: var(--text-muted); font-size: 11px;">No shared metadata anchors.</div>`;
  }

  inspector.innerHTML = `
    <div class="node-profile-card">
      <div class="node-title-row">
        <div>
          <h3>${data.node_id}</h3>
          <span style="font-size: 11px; color: var(--text-secondary);">${attr.holder_name || attr.label || data.node_type}</span>
        </div>
        <span class="badge-risk ${riskClass}">${(risk * 100).toFixed(0)}%</span>
      </div>

      <div style="margin-top: 6px; display: flex; gap: 6px; flex-wrap: wrap;">
        <span class="badge-risk ${riskClass}" style="font-size: 10px;">${riskLabel}</span>
        ${isFlagged ? '<span class="badge-risk risk-high" style="font-size: 10px;">FLAGGED SAR</span>' : ''}
      </div>

      <div class="node-prop-grid">
        <div class="prop-item">
          <div class="prop-label">Base Risk</div>
          <div class="prop-val">${(attr.risk_score || 0.0).toFixed(2)}</div>
        </div>
        <div class="prop-item">
          <div class="prop-label">Diffusion Risk</div>
          <div class="prop-val" style="color: var(--accent-rose);">${(attr.propagated_risk_score || 0.0).toFixed(2)}</div>
        </div>
        <div class="prop-item">
          <div class="prop-label">Total Inflow</div>
          <div class="prop-val" style="color: var(--accent-emerald);">$${data.total_inflow.toLocaleString()}</div>
        </div>
        <div class="prop-item">
          <div class="prop-label">Total Outflow</div>
          <div class="prop-val" style="color: var(--accent-rose);">$${data.total_outflow.toLocaleString()}</div>
        </div>
      </div>
    </div>

    <div class="inspector-section">
      <div class="section-title">Inbound Transfers (${data.inbound_transfers.length})</div>
      <div class="transfer-list">${inflowsHtml}</div>
    </div>

    <div class="inspector-section">
      <div class="section-title">Outbound Transfers (${data.outbound_transfers.length})</div>
      <div class="transfer-list">${outflowsHtml}</div>
    </div>

    <div class="inspector-section">
      <div class="section-title">Linked Anchors (${data.linked_anchors.length})</div>
      <div class="anchor-list">${anchorsHtml}</div>
    </div>
  `;
}

window.focusNodeId = function (nodeId) {
  if (!network || !nodesDataSet.get(nodeId)) return;
  network.selectNodes([nodeId]);
  network.focus(nodeId, { scale: 1.3, animation: true });
  loadNodeInspector(nodeId);
};

async function handleRunRiskDiffusion() {
  const btn = document.getElementById("btnPropagateRisk");
  const oldText = btn.innerText;
  btn.innerText = "⏳ Diffusing...";
  btn.disabled = true;

  try {
    const res = await fetch("/api/propagate-risk", { method: "POST" });
    const result = await res.json();
    console.log("Diffusion finished:", result);

    // Refresh entire dataset
    await loadAllData();
    if (selectedNodeId) {
      loadNodeInspector(selectedNodeId);
    }
  } catch (err) {
    alert("Risk diffusion failed: " + err.message);
  } finally {
    btn.innerText = oldText;
    btn.disabled = false;
  }
}

async function handleResetSim() {
  if (!confirm("Reset simulation feed and re-seed fraud rings?")) return;
  try {
    await fetch("/api/simulate/reset?seed=" + Math.floor(Math.random() * 1000), { method: "POST" });
    await loadAllData();
    document.getElementById("inspectorContent").innerHTML = `
      <div class="empty-inspector">
        <p>Simulation reset. Select any node to inspect.</p>
      </div>
    `;
  } catch (err) {
    alert("Failed to reset simulation: " + err.message);
  }
}

function openSummaryModal() {
  if (!graphSummary) return;
  document.getElementById("narrativeText").innerText = graphSummary.executive_narrative;
  document.getElementById("summaryModal").classList.add("active");
}

function closeSummaryModal() {
  document.getElementById("summaryModal").classList.remove("active");
}

function copyReportText() {
  const text = document.getElementById("narrativeText").innerText;
  navigator.clipboard.writeText(text).then(() => {
    const btn = document.getElementById("btnCopyReport");
    btn.innerText = "✓ Copied!";
    setTimeout(() => (btn.innerText = "📋 Copy Report"), 2000);
  });
}
