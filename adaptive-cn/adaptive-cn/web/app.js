/**
 * Adaptive CN - Dashboard Controller
 * Dynamic SVG Topology, Live Step-by-Step State, Guided Demo, and Fair Comparison Runner.
 */

const $ = id => document.getElementById(id);

let state = null;
let lastRenderedTopology = null;
let isBusy = false;
let isGuidedDemo = false;
let guidedDemoPhase = 1;
let comparisonData = null;

// Helpers
const display = (val, digits = 1) => (val == null || isNaN(val) ? '—' : Number(val).toFixed(digits));
const routeText = route => (route && route.length ? route.map(s => s.toUpperCase()).join(' → ') : '—');

// Contrast Theme Toggle
const themeToggle = $('theme-toggle');
if (themeToggle) {
  themeToggle.onclick = () => {
    document.body.classList.toggle('high-contrast');
    if (state) render(state);
  };
}

// API Call Wrapper
async function apiControl(payload) {
  try {
    const res = await fetch('/api/control', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json; charset=utf-8' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Control action failed');
    if (data.file) {
      $('error-banner').textContent = `Snapshot saved: ${data.file}`;
      setTimeout(() => { $('error-banner').textContent = ''; }, 4000);
    }
    await refreshState();
  } catch (err) {
    $('error-banner').textContent = err.message;
  }
}

// Button Events
$('start-btn').onclick = () => {
  if (state?.running) {
    apiControl({ action: 'pause' });
  } else {
    apiControl({ action: 'start' });
  }
};

$('reset-btn').onclick = () => {
  isGuidedDemo = false;
  $('guided-banner').style.display = 'none';
  apiControl({ action: 'reset' });
};

$('save-run-btn').onclick = () => apiControl({ action: 'save' });

$('apply-btn').onclick = () => {
  apiControl({
    mode: $('ctrl-mode').value,
    scenario: $('ctrl-scenario').value,
    topology: $('ctrl-topology').value,
    foreground_mbps: parseFloat($('ctrl-fg').value),
    link_capacity: parseFloat($('ctrl-cap').value),
    duration: parseInt($('ctrl-duration').value, 10)
  });
};

$('ctrl-topology').onchange = e => {
  if (state?.running) {
    alert('Cannot change topology while experiment is running. Please pause or reset first.');
    e.target.value = state.topology;
    return;
  }
  apiControl({ topology: e.target.value });
};

$('ctrl-mode').onchange = e => apiControl({ mode: e.target.value });
$('ctrl-scenario').onchange = e => apiControl({ scenario: e.target.value });

// Guided Demo Logic
$('guided-btn').onclick = async () => {
  isGuidedDemo = true;
  guidedDemoPhase = 1;
  $('guided-banner').style.display = 'flex';
  // Configure ideal demonstration scenario
  await apiControl({
    action: 'reset',
    topology: 'diamond',
    mode: 'predictive',
    scenario: 'ramp',
    foreground_mbps: 4.0,
    link_capacity: 10.0,
    duration: 120
  });
  await apiControl({ action: 'start' });
};

$('guided-dismiss').onclick = () => {
  isGuidedDemo = false;
  $('guided-banner').style.display = 'none';
};

function updateGuidedDemo(s) {
  if (!isGuidedDemo) return;
  $('guided-banner').style.display = 'flex';
  const t = s.tick;
  
  if (t < 12) {
    guidedDemoPhase = 1;
    $('guided-step-badge').textContent = 'Phase 1 / 5';
    $('guided-step-title').textContent = 'Normal Baseline Traffic';
    $('guided-step-desc').textContent = `Transferring foreground stream (4 Mbps) along initial path ${routeText(s.route)}. Network utilization is low.`;
  } else if (t < 25) {
    guidedDemoPhase = 2;
    $('guided-step-badge').textContent = 'Phase 2 / 5';
    $('guided-step-title').textContent = 'Background Traffic Ramping Up';
    $('guided-step-desc').textContent = 'Competing background traffic on link S2-S4 is steadily increasing toward capacity.';
  } else if (t < 35) {
    guidedDemoPhase = 3;
    $('guided-step-badge').textContent = 'Phase 3 / 5';
    $('guided-step-title').textContent = 'Model Warm-up & 5s Forecast Active';
    $('guided-step-desc').textContent = 'The 10-sample observation window is filled. The model detects impending congestion risk before severe drops.';
  } else if (t < 50) {
    guidedDemoPhase = 4;
    $('guided-step-badge').textContent = 'Phase 4 / 5';
    $('guided-step-title').textContent = 'Congestion Avoidance Reroute';
    $('guided-step-desc').textContent = `Controller rerouted traffic to ${routeText(s.route)} to bypass the congested bottleneck link.`;
  } else {
    guidedDemoPhase = 5;
    $('guided-step-badge').textContent = 'Phase 5 / 5';
    $('guided-step-title').textContent = 'Traffic Stabilized';
    $('guided-step-desc').textContent = 'Foreground traffic is fully protected on the alternate path with zero packet loss.';
  }
}

// Comparison Modal Logic
$('compare-btn').onclick = () => {
  $('comparison-modal').style.display = 'flex';
};

$('comparison-close-btn').onclick = () => {
  $('comparison-modal').style.display = 'none';
};

$('run-comparison-exec').onclick = async () => {
  const statusEl = $('comparison-status');
  statusEl.textContent = 'Running benchmark (Static, Reactive, Predictive)...';
  $('run-comparison-exec').disabled = true;

  try {
    const res = await fetch('/api/comparison/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json; charset=utf-8' },
      body: JSON.stringify({
        duration: parseInt($('ctrl-duration').value || '60', 10),
        scenario: $('ctrl-scenario').value,
        topology: $('ctrl-topology').value,
        seed: 42
      })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Comparison failed');
    comparisonData = data;
    renderComparisonTable(data);
    statusEl.textContent = `Completed 3 benchmark runs under '${data.scenario}' scenario.`;
    $('export-comp-csv').style.display = 'inline-block';
    $('export-comp-json').style.display = 'inline-block';
  } catch (err) {
    statusEl.textContent = `Error: ${err.message}`;
  } finally {
    $('run-comparison-exec').disabled = false;
  }
};

function renderComparisonTable(data) {
  $('comparison-results').style.display = 'block';
  const tbody = $('comparison-tbody');
  tbody.replaceChildren();

  const results = data.results || {};
  const order = ['static', 'reactive', 'predictive'];

  for (const m of order) {
    const row = results[m];
    if (!row) continue;
    const tr = document.createElement('tr');

    const badgeClass = m;
    const title = m.charAt(0).toUpperCase() + m.slice(1);

    tr.innerHTML = `
      <td><span class="strategy-badge ${badgeClass}">${title}</span></td>
      <td>${display(row.mean_latency_ms)} ms</td>
      <td>${display(row.mean_throughput_mbps, 2)} Mbps</td>
      <td>${display(row.mean_loss_percent, 2)}%</td>
      <td>${row.route_changes}</td>
      <td>${row.congested_samples}s</td>
    `;
    tbody.appendChild(tr);
  }
}

$('export-comp-csv').onclick = () => {
  if (!comparisonData) return;
  const rows = [
    ['strategy', 'mean_latency_ms', 'mean_throughput_mbps', 'mean_loss_percent', 'route_changes', 'congested_seconds', 'scenario', 'topology', 'duration_seconds']
  ];
  for (const [m, r] of Object.entries(comparisonData.results)) {
    rows.push([m, r.mean_latency_ms, r.mean_throughput_mbps, r.mean_loss_percent, r.route_changes, r.congested_samples, comparisonData.scenario, comparisonData.topology, comparisonData.duration_seconds]);
  }
  const csvContent = 'data:text/csv;charset=utf-8,' + rows.map(e => e.join(',')).join('\n');
  const encodedUri = encodeURI(csvContent);
  const link = document.createElement('a');
  link.setAttribute('href', encodedUri);
  link.setAttribute('download', `cn-comparison-${comparisonData.scenario}.csv`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
};

$('export-comp-json').onclick = () => {
  if (!comparisonData) return;
  const jsonContent = 'data:application/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(comparisonData, null, 2));
  const link = document.createElement('a');
  link.setAttribute('href', jsonContent);
  link.setAttribute('download', `cn-comparison-${comparisonData.scenario}.json`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
};

// Canvas Chart Renderer
function drawChart(canvasId, rows, field, strokeColor, multiplier = 1, unit = '') {
  const c = $(canvasId);
  if (!c) return;
  const dpr = window.devicePixelRatio || 1;
  const w = c.clientWidth || 300;
  const h = 130;
  c.width = w * dpr;
  c.height = h * dpr;
  const ctx = c.getContext('2d');
  ctx.scale(dpr, dpr);

  const values = rows.map(r => (r[field] == null ? null : r[field] * multiplier));
  const valid = values.filter(v => v != null);

  ctx.strokeStyle = '#e2e8f0';
  ctx.fillStyle = '#64748b';
  ctx.font = '10px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';

  const maxVal = valid.length ? Math.max(1, Math.max(...valid) * 1.15) : 10;

  for (let i = 0; i < 4; i++) {
    const y = 14 + (i * (h - 32)) / 3;
    ctx.beginPath();
    ctx.moveTo(38, y);
    ctx.lineTo(w, y);
    ctx.stroke();
    ctx.fillText((maxVal * (1 - i / 3)).toFixed(0), 4, y + 3);
  }

  if (!valid.length) {
    ctx.fillStyle = '#94a3b8';
    ctx.font = '12px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
    ctx.fillText('Awaiting measurements', 50, 72);
    return;
  }

  // Draw line
  ctx.beginPath();
  let isDrawing = false;
  values.forEach((v, i) => {
    if (v == null) {
      isDrawing = false;
      return;
    }
    const x = 40 + (i * (w - 46)) / Math.max(1, values.length - 1);
    const y = 14 + (1 - v / maxVal) * (h - 32);
    if (!isDrawing) {
      ctx.moveTo(x, y);
      isDrawing = true;
    } else {
      ctx.lineTo(x, y);
    }
  });
  ctx.strokeStyle = strokeColor;
  ctx.lineWidth = 2.2;
  ctx.stroke();
}

// SVG Topology Builder
function renderTopologySVG(topoMeta, linksData, appliedRoute) {
  const svg = $('topo-svg');
  if (!svg || !topoMeta) return;

  const layout = topoMeta.layout;
  svg.setAttribute('viewBox', layout.viewBox || '0 0 740 340');
  svg.replaceChildren();

  const showAnim = $('ctrl-animation')?.checked;
  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const activeLinkKeys = new Set();
  if (appliedRoute && appliedRoute.length > 1) {
    for (let i = 0; i < appliedRoute.length - 1; i++) {
      activeLinkKeys.add([appliedRoute[i], appliedRoute[i + 1]].sort().join('-'));
    }
  }

  // 1. Control Plane Lines (from Controller to Switches)
  const ctrlPos = layout.controller || { x: 165, y: 16 };
  const ctrlGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
  ctrlGroup.setAttribute('class', 'control-plane-links');

  for (const swName of topoMeta.switches) {
    const swPos = layout.switches[swName];
    if (swPos) {
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', ctrlPos.x);
      line.setAttribute('y1', ctrlPos.y + 12);
      line.setAttribute('x2', swPos.x);
      line.setAttribute('y2', swPos.y - 26);
      line.setAttribute('class', 'svg-control-link');
      ctrlGroup.appendChild(line);
    }
  }
  svg.appendChild(ctrlGroup);

  // 2. Host Attachment Links
  const hostLinksGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
  hostLinksGroup.setAttribute('class', 'host-links');

  for (const [hid, hmeta] of Object.entries(layout.hosts)) {
    const swPos = layout.switches[hmeta.attach];
    if (swPos) {
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', hmeta.x + 22);
      line.setAttribute('y1', hmeta.y + 16);
      line.setAttribute('x2', swPos.x);
      line.setAttribute('y2', swPos.y);
      line.setAttribute('class', 'svg-host-link');
      hostLinksGroup.appendChild(line);
    }
  }
  svg.appendChild(hostLinksGroup);

  // 3. Inter-switch Traffic Links
  const linksGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
  linksGroup.setAttribute('class', 'data-links');

  const linkMap = {};
  for (const l of linksData) linkMap[l.id] = l;

  for (const linkDef of topoMeta.links) {
    const swA = layout.switches[linkDef.source];
    const swB = layout.switches[linkDef.target];
    if (!swA || !swB) continue;

    const lid = linkDef.id;
    const lData = linkMap[lid] || { utilization: 0, tx_mbps: 0, offered_mbps: 0, capacity_mbps: linkDef.capacity_mbps };
    const isActive = activeLinkKeys.has(lid);

    const path = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    path.setAttribute('id', `svg-link-${lid}`);
    path.setAttribute('x1', swA.x);
    path.setAttribute('y1', swA.y);
    path.setAttribute('x2', swB.x);
    path.setAttribute('y2', swB.y);

    let color = '#16a34a';
    if (lData.utilization >= 0.85) color = '#dc2626';
    else if (lData.utilization >= 0.65) color = '#d97706';

    path.style.stroke = color;

    let cls = 'svg-link';
    if (isActive) cls += ' active-path';
    if (isActive && showAnim && !prefersReducedMotion) cls += ' svg-link-animated';
    path.setAttribute('class', cls);

    path.onclick = () => showInspector(lData, 'link');
    linksGroup.appendChild(path);

    // Link label
    const midX = (swA.x + swB.x) / 2;
    const midY = (swA.y + swB.y) / 2 - 8;
    const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    text.setAttribute('x', midX);
    text.setAttribute('y', midY);
    text.setAttribute('class', 'svg-link-label');
    text.textContent = `${display(lData.utilization * 100, 0)}% · ${display(lData.tx_mbps, 1)}M`;
    linksGroup.appendChild(text);
  }
  svg.appendChild(linksGroup);

  // 4. Switches
  const switchesGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
  switchesGroup.setAttribute('class', 'switches');

  for (const swName of topoMeta.switches) {
    const pos = layout.switches[swName];
    if (!pos) continue;

    const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    g.setAttribute('class', 'svg-switch');
    g.setAttribute('transform', `translate(${pos.x}, ${pos.y})`);

    const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    circle.setAttribute('r', '25');

    const txt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    txt.textContent = swName.toUpperCase();

    g.appendChild(circle);
    g.appendChild(txt);
    g.onclick = () => showInspector({ name: swName.toUpperCase(), type: 'switch', topo: topoMeta.name }, 'switch');
    switchesGroup.appendChild(g);
  }
  svg.appendChild(switchesGroup);

  // 5. Hosts
  const hostsGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
  hostsGroup.setAttribute('class', 'hosts');

  for (const [hid, hmeta] of Object.entries(layout.hosts)) {
    const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    g.setAttribute('class', 'svg-host');
    g.setAttribute('transform', `translate(${hmeta.x}, ${hmeta.y})`);

    const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    rect.setAttribute('width', '50');
    rect.setAttribute('height', '32');
    rect.setAttribute('rx', '6');

    const txt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    txt.setAttribute('x', '25');
    txt.setAttribute('y', '16');
    txt.textContent = hid.toUpperCase();

    g.appendChild(rect);
    g.appendChild(txt);
    g.onclick = () => showInspector(topoMeta.hosts[hid] || { id: hid }, 'host');
    hostsGroup.appendChild(g);
  }
  svg.appendChild(hostsGroup);

  // 6. External Controller & Engine Labels
  const extGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
  extGroup.setAttribute('class', 'svg-external');

  // Controller Box
  const cG = document.createElementNS('http://www.w3.org/2000/svg', 'g');
  cG.setAttribute('transform', `translate(${ctrlPos.x - 70}, ${ctrlPos.y})`);
  const cRect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
  cRect.setAttribute('width', '140');
  cRect.setAttribute('height', '24');
  const cTxt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
  cTxt.setAttribute('x', '70');
  cTxt.setAttribute('y', '12');
  cTxt.textContent = 'SDN CONTROLLER';
  cG.appendChild(cRect);
  cG.appendChild(cTxt);
  extGroup.appendChild(cG);

  // Engine Box
  const engPos = layout.engine || { x: 535, y: 16 };
  const eG = document.createElementNS('http://www.w3.org/2000/svg', 'g');
  eG.setAttribute('transform', `translate(${engPos.x - 75}, ${engPos.y})`);
  const eRect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
  eRect.setAttribute('width', '150');
  eRect.setAttribute('height', '24');
  const eTxt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
  eTxt.setAttribute('x', '75');
  eTxt.setAttribute('y', '12');
  eTxt.textContent = 'AI PREDICTOR';
  eG.appendChild(eRect);
  eG.appendChild(eTxt);
  extGroup.appendChild(eG);

  svg.appendChild(extGroup);
}

// Inspector Popup
function showInspector(item, type) {
  const card = $('inspector-card');
  const grid = $('inspector-grid');
  const title = $('inspector-title');
  if (!card || !grid) return;

  grid.replaceChildren();

  if (type === 'link') {
    title.textContent = `Link Details: ${item.id ? item.id.toUpperCase().replace('-', ' ↔ ') : 'Link'}`;
    const cells = [
      { label: 'Link Capacity', val: `${display(item.capacity_mbps)} Mbps` },
      { label: 'Offered Load', val: `${display(item.offered_mbps)} Mbps (${display((item.offered_load || 0) * 100, 0)}%)` },
      { label: 'Transmitted Rate', val: `${display(item.tx_mbps)} Mbps` },
      { label: 'Link Utilization', val: `${display(item.utilization * 100, 1)}%` },
      { label: '5-Sample Forecast', val: item.forecast != null ? `${display(item.forecast * 100, 0)}%` : 'Warming up' },
      { label: 'Congestion Risk', val: item.risk != null ? `${display(item.risk * 100, 0)}%` : '—' },
      { label: 'Base Delay', val: `${display(item.base_delay_ms)} ms` }
    ];
    for (const c of cells) {
      const el = document.createElement('div');
      el.className = 'inspector-cell';
      el.innerHTML = `<small>${c.label}</small><strong>${c.val}</strong>`;
      grid.appendChild(el);
    }
  } else if (type === 'switch') {
    title.textContent = `SDN Switch: ${item.name}`;
    const el = document.createElement('div');
    el.className = 'inspector-cell';
    el.innerHTML = `<small>Protocol</small><strong>OpenFlow 1.3</strong>`;
    grid.appendChild(el);
  } else if (type === 'host') {
    title.textContent = `Host: ${item.label || item.id || 'Host'}`;
    const cells = [
      { label: 'IP Address', val: item.ip || '10.0.0.x' },
      { label: 'Attached Switch', val: (item.switch || 's1').toUpperCase() },
      { label: 'Role', val: item.role || 'Host' }
    ];
    for (const c of cells) {
      const el = document.createElement('div');
      el.className = 'inspector-cell';
      el.innerHTML = `<small>${c.label}</small><strong>${c.val}</strong>`;
      grid.appendChild(el);
    }
  }
  card.style.display = 'block';
}

$('inspector-close').onclick = () => {
  $('inspector-card').style.display = 'none';
};

// Main State Rendering
function render(s) {
  state = s;
  const isMininet = s.source === 'mininet';

  // 1. Header Badges
  $('source-badge').textContent = isMininet ? 'MININET • PACKET NETWORK' : 'SIMULATION • DEMO';
  $('connection-dot').style.background = s.stale ? '#d97706' : '#16a34a';
  $('connection-status').textContent = s.stale ? 'Waiting for telemetry' : isMininet ? 'OpenFlow Connected' : s.running ? 'Running' : 'Paused';

  // 2. Start / Pause Button
  $('start-btn').disabled = isMininet;
  $('reset-btn').disabled = isMininet;
  $('ctrl-scenario').disabled = isMininet;
  $('ctrl-fg').disabled = isMininet;
  $('ctrl-cap').disabled = isMininet;
  $('ctrl-duration').disabled = isMininet;
  $('start-btn-label').textContent = s.running ? 'Pause experiment' : 'Start experiment';

  // 3. Status Pills
  $('elapsed-pill').textContent = `Elapsed: ${s.tick}s / ${s.duration_seconds ? s.duration_seconds + 's' : '∞'}`;
  $('route-pill').textContent = `Route: ${routeText(s.applied_route || s.route)}`;
  $('traffic-pill').textContent = `Traffic: ${display(s.traffic_mbps)} Mbps`;

  // 4. Source Notice
  $('notice-text').textContent = isMininet
    ? 'Mininet mode: Link utilization is gathered from live OpenFlow 1.3 switch port byte counters. Latency is measured by ping; throughput and loss are gathered via iperf3.'
    : 'Analytical simulation mode: Traffic demand and QoS metrics are calculated from network queuing equations. The prediction engine uses our Ridge autoregressive model with empirical residual calibration.';

  // 5. Live Step-by-Step State Panel
  $('current-state-badge').textContent = s.status_title || 'Running';
  $('state-headline').textContent = s.status_title || 'State Update';
  $('state-narrative').textContent = s.status_detail || 'System running.';

  // Warmup Progress
  if (s.warmup_progress) {
    const wp = s.warmup_progress;
    $('warmup-label').textContent = `Model Observations: ${wp.current} of ${wp.required} samples`;
    $('warmup-percent').textContent = `${wp.percent}%`;
    $('warmup-fill').style.width = `${wp.percent}%`;
  }

  // Routing Decision Details
  if (s.last_decision) {
    $('decision-text').textContent = s.last_decision.explanation || 'Routing path evaluated.';
  }

  // Prediction Horizon
  if (s.horizon_info) {
    $('horizon-title').textContent = s.horizon_info.label;
  }

  // 6. Metrics Stats Cards
  $('latency-val').textContent = display(s.metrics.latency_ms);
  $('loss-val').textContent = display(s.metrics.loss_percent, 2);
  $('throughput-val').textContent = display(s.metrics.throughput_mbps, 2);

  const risks = s.links.map(l => l.risk).filter(r => r != null);
  $('risk-val').textContent = risks.length ? `${display(Math.max(...risks) * 100, 0)}%` : 'Warming up';

  // 7. Topology Controls & Info
  $('ctrl-mode').value = s.mode;
  $('ctrl-scenario').value = s.scenario;
  $('ctrl-topology').value = s.topology;
  $('ctrl-fg').value = s.foreground_mbps || 4.0;
  $('topo-title').textContent = s.topology_meta ? s.topology_meta.name : 'Topology';
  $('topo-tick-badge').textContent = `${s.tick} samples`;

  // 8. Active Route Card
  $('requested-route').textContent = routeText(s.route);
  $('applied-route').textContent = routeText(s.applied_route);

  // 9. Dynamic SVG Topology
  if (s.topology_meta) {
    renderTopologySVG(s.topology_meta, s.links, s.applied_route || s.route);
  }

  // 10. Links Prediction Cards
  const linksContainer = $('links-container');
  linksContainer.replaceChildren();

  for (const l of s.links) {
    const row = document.createElement('div');
    row.className = 'link-row';

    let color = '#16a34a';
    if (l.utilization >= 0.85) color = '#dc2626';
    else if (l.utilization >= 0.65) color = '#d97706';

    const top = document.createElement('div');
    top.className = 'link-row-top';
    top.innerHTML = `
      <strong>${l.id.toUpperCase().replace('-', ' ↔ ')}</strong>
      <span>${display(l.utilization * 100, 0)}% utilized · ${display(l.tx_mbps)} Mbps</span>
    `;

    const bar = document.createElement('div');
    bar.className = 'bar';
    const fill = document.createElement('div');
    fill.className = 'bar-fill';
    fill.style.width = `${Math.min(100, l.utilization * 100)}%`;
    fill.style.background = color;
    bar.appendChild(fill);

    const footer = document.createElement('div');
    footer.className = 'link-row-footer';

    let riskClass = 'low';
    if (l.risk >= 0.7) riskClass = 'high';
    else if (l.risk >= 0.4) riskClass = 'medium';

    const forecastStr = l.forecast != null ? `Forecast: ${display(l.forecast * 100, 0)}%` : l.prediction_status || 'Warming up';
    const riskStr = l.risk != null ? `<span class="risk-tag ${riskClass}">Risk: ${display(l.risk * 100, 0)}%</span>` : '';

    footer.innerHTML = `<span>${forecastStr}</span> ${riskStr}`;

    row.appendChild(top);
    row.appendChild(bar);
    row.appendChild(footer);
    linksContainer.appendChild(row);
  }

  // 11. Model Info & Provenance
  if (s.model) {
    $('model-provenance-text').textContent = `${s.model.model || 'Ridge Autoregressive Predictor'}. Training source: ${s.model.provenance || 'Synthetic benchmark'}.`;
    const mGrid = $('model-metrics-grid');
    mGrid.replaceChildren();

    const mCells = [
      { label: 'Holdout RMSE', val: s.model.rmse != null ? `${display(s.model.rmse * 100, 2)}%` : '—' },
      { label: 'Holdout MAE', val: s.model.mae != null ? `${display(s.model.mae * 100, 2)}%` : '—' },
      { label: 'Threshold F1 Score', val: s.model.f1 != null ? display(s.model.f1, 3) : '—' },
      { label: 'Training Samples', val: s.model.train_samples ? s.model.train_samples.toLocaleString() : '—' }
    ];

    for (const c of mCells) {
      const cellEl = document.createElement('div');
      cellEl.className = 'model-metric-cell';
      cellEl.innerHTML = `<small>${c.label}</small><strong>${c.val}</strong>`;
      mGrid.appendChild(cellEl);
    }
  }

  // 12. Charts
  $('provenance-label').textContent = s.metric_provenance || 'Analytical simulation';
  drawChart('chart-latency', s.history, 'latency_ms', '#0284c7', 1, 'ms');
  drawChart('chart-util', s.history, 'max_utilization', '#d97706', 100, '%');
  drawChart('chart-throughput', s.history, 'throughput_mbps', '#16a34a', 1, 'Mbps');

  // 13. Events Timeline
  const eventsContainer = $('events-container');
  eventsContainer.replaceChildren();

  if (!s.events || !s.events.length) {
    const p = document.createElement('p');
    p.className = 'muted';
    p.textContent = s.tick < 10 ? 'Collecting observations. Routing changes require at least 10 samples warm-up.' : 'No route changes occurred. Current path remains optimal.';
    eventsContainer.appendChild(p);
  } else {
    for (const ev of s.events) {
      const item = document.createElement('div');
      item.className = 'event-item';
      item.innerHTML = `
        <span class="event-time">t=${ev.tick}s</span>
        <span class="event-route">${routeText(ev.old)} &rarr; ${routeText(ev.new)}</span>
        <span class="event-detail">${ev.reason} &bull; ${ev.status}</span>
      `;
      eventsContainer.appendChild(item);
    }
  }

  // 14. Guided Demo Progress
  updateGuidedDemo(s);
}

// Polling Loop
async function refreshState() {
  if (isBusy) return;
  isBusy = true;
  try {
    const res = await fetch('/api/state');
    if (!res.ok) throw new Error('Backend server unavailable');
    const data = await res.json();
    render(data);
  } catch (err) {
    $('connection-status').textContent = 'Disconnected';
    $('connection-dot').style.background = '#dc2626';
    $('error-banner').textContent = err.message;
  } finally {
    isBusy = false;
  }
}

// Initial Load & Window Listeners
refreshState();
setInterval(refreshState, 1000);
window.addEventListener('resize', () => {
  if (state) render(state);
});
