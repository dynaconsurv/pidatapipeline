/**
 * AVEVA PI to Oracle ERP Cloud Data Pipeline - Client-side Controller
 */

// Global State
let currentSettings = null;
let currentMappings = [];
let pollTimer = null;
let countdownTimer = null;
let secondsLeft = 0;
let currentAfPath = "\\";

// Initialize when DOM is ready
document.addEventListener("DOMContentLoaded", () => {
  initNavigation();
  initDashboard();
  initMappings();
  initSettings();
  initAFBrowser();
  initInfoToggles();

  // Start polling dashboard status every 2 seconds
  loadDashboardData();
  pollTimer = setInterval(loadDashboardData, 2000);

  // Local second-by-second countdown ticker
  countdownTimer = setInterval(tickCountdown, 1000);
});

// ============================================================
// 1. NAVIGATION
// ============================================================
function initNavigation() {
  const tabs = document.querySelectorAll(".nav-tab");
  tabs.forEach(tab => {
    tab.addEventListener("click", () => {
      const target = tab.getAttribute("data-tab");
      switchTab(target);
    });
  });

  document.getElementById("btn-goto-settings")?.addEventListener("click", () => {
    switchTab("settings");
  });
}

function switchTab(tabName) {
  document.querySelectorAll(".nav-tab").forEach(t => {
    t.classList.toggle("active", t.getAttribute("data-tab") === tabName);
  });
  document.querySelectorAll(".page-view").forEach(v => {
    v.classList.toggle("active", v.id === `view-${tabName}`);
  });

  if (tabName === "mappings") {
    loadMappings();
    refreshPayloadPreview();
  } else if (tabName === "settings") {
    loadSettingsIntoForm();
  } else if (tabName === "dashboard") {
    loadDashboardData();
  }
}

function initInfoToggles() {
  document.querySelectorAll(".btn-info-trigger").forEach(btn => {
    btn.addEventListener("click", () => {
      const targetId = btn.getAttribute("data-target");
      const card = document.getElementById(targetId);
      if (!card) return;
      const isOpen = card.style.display === "block";
      if (isOpen) {
        card.style.display = "none";
        btn.classList.remove("active");
      } else {
        card.style.display = "block";
        btn.classList.add("active");
      }
    });
  });

  document.querySelectorAll(".info-card-close").forEach(btn => {
    btn.addEventListener("click", () => {
      const targetId = btn.getAttribute("data-close");
      const card = document.getElementById(targetId);
      if (card) {
        card.style.display = "none";
      }
      const trigger = document.querySelector(`.btn-info-trigger[data-target="${targetId}"]`);
      if (trigger) trigger.classList.remove("active");
    });
  });
}

// ============================================================
// 2. DASHBOARD VIEW & MONITORING
// ============================================================
function initDashboard() {
  document.getElementById("btn-run-pull-now")?.addEventListener("click", triggerPullNow);
  document.getElementById("btn-instant-run")?.addEventListener("click", triggerPullNow);
  document.getElementById("btn-test-pi")?.addEventListener("click", testPiConnectionFromDashboard);
  document.getElementById("btn-test-erp")?.addEventListener("click", testErpConnectionFromDashboard);
  document.getElementById("btn-toggle-pause")?.addEventListener("click", togglePauseResume);
  document.getElementById("btn-refresh-dashboard")?.addEventListener("click", loadDashboardData);
  document.getElementById("btn-refresh-logs")?.addEventListener("click", loadLogs);
  document.getElementById("log-filter-category")?.addEventListener("change", loadLogs);

  document.getElementById("btn-view-last-payload")?.addEventListener("click", () => {
    switchTab("mappings");
    const previewEl = document.getElementById("erp-payload-preview-box");
    if (previewEl) previewEl.scrollIntoView({ behavior: "smooth" });
  });
}

async function loadDashboardData() {
  try {
    const res = await fetch("/api/dashboard");
    if (!res.ok) return;
    const data = await res.json();
    renderDashboard(data);
  } catch (err) {
    console.error("Error loading dashboard data:", err);
  }
}

function renderDashboard(data) {
  // 1. AVEVA PI Connection Card
  const pi = data.pi_connection || {};
  const piBadge = document.getElementById("pi-status-badge");
  const piLatency = document.getElementById("pi-latency-val");
  const piEndpoint = document.getElementById("pi-endpoint-val");
  const piLastPull = document.getElementById("pi-last-pull-val");
  const piMode = document.getElementById("pi-mode-val");
  const piErrorBox = document.getElementById("pi-error-box");
  const piErrorText = document.getElementById("pi-error-text");

  if (currentSettings && currentSettings.pi_web_api) {
    piEndpoint.textContent = currentSettings.pi_web_api.url || "--";
    piEndpoint.title = currentSettings.pi_web_api.url || "";
    piMode.textContent = currentSettings.pi_web_api.simulation_mode ? "Simulation Mode" : "Live PI Server";
  }

  if (pi.status === "CONNECTED") {
    piBadge.className = "badge badge-success";
    piBadge.innerHTML = '<span class="badge-dot"></span> Connected';
    piLatency.textContent = pi.latency_ms !== null ? pi.latency_ms : "--";
    piErrorBox.style.display = "none";
  } else if (pi.status === "SIMULATED") {
    piBadge.className = "badge badge-info";
    piBadge.innerHTML = '<span class="badge-dot"></span> Simulated Demo';
    piLatency.textContent = pi.latency_ms !== null ? pi.latency_ms : "--";
    piErrorBox.style.display = "none";
  } else if (pi.status === "PARTIAL_ERROR" || pi.status === "FAILED") {
    piBadge.className = "badge badge-danger";
    piBadge.innerHTML = `<span class="badge-dot"></span> ${pi.status === 'FAILED' ? 'Failed' : 'Partial Error'}`;
    piLatency.textContent = "--";
    piErrorBox.style.display = "block";
    piErrorText.textContent = pi.error || pi.message || "Unknown error connecting to PI Web API";
  } else {
    piBadge.className = "badge badge-pending";
    piBadge.innerHTML = '<span class="badge-dot"></span> Checking';
  }

  if (pi.last_check) {
    piLastPull.textContent = formatTimestamp(pi.last_check);
  }

  // 2. Oracle ERP Cloud Connection Card
  const erp = data.oracle_erp_connection || {};
  const erpBanner = document.getElementById("dashboard-erp-banner");
  const erpBadge = document.getElementById("erp-status-badge");
  const erpHeadline = document.getElementById("erp-status-headline");
  const erpAuth = document.getElementById("erp-auth-val");
  const erpResource = document.getElementById("erp-resource-val");
  const erpReason = document.getElementById("erp-reason-val");
  const erpErrorBox = document.getElementById("erp-error-box");
  const erpErrorText = document.getElementById("erp-error-text");

  if (currentSettings && currentSettings.oracle_erp) {
    erpAuth.textContent = currentSettings.oracle_erp.auth_type.toUpperCase();
    erpResource.textContent = currentSettings.oracle_erp.resource_endpoint || "--";
    erpResource.title = currentSettings.oracle_erp.resource_endpoint || "";
  }

  if (erpBanner) erpBanner.style.display = "none";

  if (erp.status === "PENDING_SETUP") {
    erpBadge.className = "badge badge-pending";
    erpBadge.innerHTML = '<span class="badge-dot"></span> Pending Setup';
    erpHeadline.textContent = "Pending Setup";
    erpHeadline.style.color = "#b45309";
    erpReason.textContent = "Awaiting destination config";
    erpReason.style.color = "#b45309";
    erpErrorBox.style.display = "none";
  } else if (erp.status === "CONNECTED") {
    erpBanner.style.display = "none";
    erpBadge.className = "badge badge-success";
    erpBadge.innerHTML = '<span class="badge-dot"></span> Connected';
    erpHeadline.textContent = "Connected";
    erpHeadline.style.color = "var(--success)";
    erpReason.textContent = "Online & Authenticated";
    erpReason.style.color = "var(--success)";
    erpErrorBox.style.display = "none";
  } else if (erp.status === "FAILED") {
    erpBanner.style.display = "none";
    erpBadge.className = "badge badge-danger";
    erpBadge.innerHTML = '<span class="badge-dot"></span> Connection Error';
    erpHeadline.textContent = "Failed";
    erpHeadline.style.color = "var(--danger)";
    erpReason.textContent = erp.message || "Failed";
    erpReason.style.color = "var(--danger)";
    erpErrorBox.style.display = "block";
    erpErrorText.textContent = erp.error || erp.message || "Error communicating with Oracle ERP Cloud";
  }

  // 3. Scheduler & Countdown Card
  const sched = data.scheduler || {};
  secondsLeft = sched.seconds_remaining || 0;
  updateCountdownDisplay(secondsLeft);

  const schedBadge = document.getElementById("scheduler-badge");
  const schedInterval = document.getElementById("scheduler-interval-val");
  const schedNext = document.getElementById("scheduler-next-val");
  const pauseBtn = document.getElementById("btn-toggle-pause");
  const pauseText = document.getElementById("btn-pause-text");

  schedInterval.textContent = `Every ${sched.interval_seconds || 30}s`;
  schedNext.textContent = sched.next_run_at ? formatTimestamp(sched.next_run_at) : "--";

  if (sched.is_paused) {
    schedBadge.className = "badge badge-pending";
    schedBadge.innerHTML = '<span class="badge-dot"></span> Paused';
    pauseText.textContent = "Resume";
  } else {
    schedBadge.className = "badge badge-success";
    schedBadge.innerHTML = '<span class="badge-dot"></span> Active';
    pauseText.textContent = "Pause";
  }

  // 4. Last Data Published Card
  const pub = data.last_publish || {};
  const pubBadge = document.getElementById("last-publish-badge");
  const pubCount = document.getElementById("publish-count-val");
  const pubStatus = document.getElementById("publish-status-val");
  const pubTime = document.getElementById("publish-time-val");
  const pubHttp = document.getElementById("publish-http-val");

  pubCount.textContent = pub.record_count || 0;
  pubTime.textContent = pub.timestamp ? formatTimestamp(pub.timestamp) : "--";
  pubHttp.textContent = pub.http_code ? `HTTP ${pub.http_code}` : (pub.status === "PENDING_SETUP" ? "Pending setup" : "--");

  if (pub.status === "PENDING_SETUP") {
    pubBadge.className = "badge badge-pending";
    pubBadge.innerHTML = '<span class="badge-dot"></span> Pending Setup';
    pubStatus.textContent = "Pending connection setup";
    pubStatus.style.color = "#b45309";
  } else if (pub.status === "SUCCESS") {
    pubBadge.className = "badge badge-success";
    pubBadge.innerHTML = '<span class="badge-dot"></span> Published';
    pubStatus.textContent = "Successfully Dispatched";
    pubStatus.style.color = "var(--success)";
  } else if (pub.status === "FAILED") {
    pubBadge.className = "badge badge-danger";
    pubBadge.innerHTML = '<span class="badge-dot"></span> Failed';
    pubStatus.textContent = "Publish Rejected / Failed";
    pubStatus.style.color = "var(--danger)";
  }

  // 5. Last 5 Data Pulls Table
  renderLastPullsTable(data.last_5_pulls || []);

  // 6. Logs Box
  loadLogs();
}

function tickCountdown() {
  if (secondsLeft > 0) {
    secondsLeft--;
    updateCountdownDisplay(secondsLeft);
  }
}

function updateCountdownDisplay(sec) {
  const clock = document.getElementById("countdown-clock");
  if (!clock) return;
  const mins = Math.floor(sec / 60);
  const remainderSec = sec % 60;
  clock.textContent = `${String(mins).padStart(2, '0')}:${String(remainderSec).padStart(2, '0')}`;
}

function renderLastPullsTable(items) {
  const tbody = document.getElementById("last-pulls-tbody");
  if (!tbody) return;

  if (items.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="8" style="text-align: center; color: var(--text-muted); padding: 2rem;">
          No data pulled yet. Click <strong>"Pull Now"</strong> above to test ingestion.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = items.map(item => {
    const isGood = item.quality === "Good";
    const qualityBadge = isGood
      ? `<span class="badge badge-success"><span class="badge-dot"></span> Good</span>`
      : `<span class="badge badge-danger"><span class="badge-dot"></span> ${escapeHtml(item.quality || 'Bad')}</span>`;

    const valFormatted = item.value !== null && item.value !== undefined
      ? `${item.value} <span style="font-size: 11px; color: var(--ink-secondary);">${item.uom || ''}</span>`
      : `<span style="color: var(--status-bad); font-size: 11px;">${item.error || 'N/A'}</span>`;

    return `
      <tr>
        <td><span style="font-weight: 500;">${escapeHtml(item.attribute_name || 'Tag')}</span></td>
        <td><span class="path-code" title="${escapeHtml(item.full_path || '')}">${escapeHtml(item.full_path || '--')}</span></td>
        <td><span class="val-badge">${valFormatted}</span></td>
        <td style="color: var(--ink-secondary);">${escapeHtml(item.uom || '--')}</td>
        <td style="font-family: var(--font-mono); font-size: 11px; color: var(--ink-secondary);">${formatTimestamp(item.timestamp)}</td>
        <td>${qualityBadge}</td>
        <td><code style="font-size: 11px; color: var(--ink-primary);">${escapeHtml(item.meter_tag || item.attribute_name || '--')}</code></td>
        <td style="font-size: 11px; color: var(--ink-secondary);">${formatTimestamp(item.batch_timestamp || item.timestamp)}</td>
      </tr>
    `;
  }).join("");
}

async function triggerPullNow() {
  showToast("Triggering telemetry pull...", "info");
  try {
    const res = await fetch("/api/pipeline/run-now", { method: "POST" });
    const data = await res.json();
    if (data.success) {
      showToast("Telemetry pull cycle completed.", "success");
      loadDashboardData();
    } else {
      showToast("Data pull encountered an issue.", "danger");
    }
  } catch (e) {
    showToast("Error triggering pipeline: " + e.message, "danger");
  }
}

async function togglePauseResume() {
  const isCurrentlyPaused = document.getElementById("btn-pause-text").textContent === "Resume";
  const endpoint = isCurrentlyPaused ? "/api/pipeline/resume" : "/api/pipeline/pause";
  try {
    await fetch(endpoint, { method: "POST" });
    showToast(isCurrentlyPaused ? "Scheduler resumed." : "Scheduler paused.", "info");
    loadDashboardData();
  } catch (e) {
    showToast("Failed to update scheduler state.", "danger");
  }
}

async function testPiConnectionFromDashboard() {
  showToast("Testing AVEVA PI Web API connection...", "info");
  try {
    const res = await fetch("/api/settings/test-pi", { method: "POST" });
    const result = await res.json();
    if (result.success) {
      showToast(`PI Connection Successful (${result.latency_ms}ms)`, "success");
    } else {
      showToast(`PI Connection Failed: ${result.message}`, "danger");
    }
    loadDashboardData();
  } catch (e) {
    showToast("PI Test Failed: " + e.message, "danger");
  }
}

async function testErpConnectionFromDashboard() {
  showToast("Validating Oracle ERP Cloud connection & token...", "info");
  try {
    const res = await fetch("/api/settings/test-erp", { method: "POST" });
    const result = await res.json();
    if (result.status === "PENDING_SETUP") {
      showToast("Oracle ERP is in 'Pending connection setup' state. Configure credentials in Settings.", "warning");
    } else if (result.success) {
      showToast(`Connected to Oracle ERP Cloud (${result.latency_ms}ms)`, "success");
    } else {
      showToast(`ERP Test Failed: ${result.message}`, "danger");
    }
    loadDashboardData();
  } catch (e) {
    showToast("ERP Test error: " + e.message, "danger");
  }
}

async function loadLogs() {
  const catEl = document.getElementById("log-filter-category");
  const cat = catEl ? catEl.value : "ALL";
  try {
    const res = await fetch(`/api/logs?category=${cat}&limit=40`);
    const logs = await res.json();
    const box = document.getElementById("activity-logs-box");
    if (!box) return;

    if (logs.length === 0) {
      box.textContent = "No log records found.";
      return;
    }

    box.innerHTML = logs.map(l => {
      let color = "var(--ink-primary)";
      if (l.level === "ERROR") color = "var(--status-bad)";
      else if (l.level === "WARNING") color = "var(--status-warn)";
      else if (l.level === "SUCCESS") color = "var(--status-good)";

      const timeStr = l.timestamp ? l.timestamp.substring(11, 19) : "";
      return `<div style="margin-bottom: 4px; color: ${color};">
        <span style="color: var(--ink-secondary);">[${timeStr}]</span> 
        <span style="font-weight: 500;">[${l.category}] [${l.level}]</span> 
        ${escapeHtml(l.message)}
        ${l.details ? `<div style="color: var(--ink-secondary); font-size: 11px; margin-left: 16px;">${escapeHtml(typeof l.details === 'string' ? l.details : JSON.stringify(l.details))}</div>` : ''}
      </div>`;
    }).join("");
  } catch (e) {
    console.error("Failed to load logs:", e);
  }
}

// ============================================================
// 3. ATTRIBUTE MAPPINGS VIEW
// ============================================================
function initMappings() {
  document.getElementById("btn-add-mapping-modal")?.addEventListener("click", () => openMappingModal());
  document.getElementById("btn-close-modal")?.addEventListener("click", closeMappingModal);
  document.getElementById("btn-cancel-modal")?.addEventListener("click", closeMappingModal);
  document.getElementById("mapping-form")?.addEventListener("submit", handleSaveMappingModal);
  document.getElementById("btn-save-all-mappings")?.addEventListener("click", saveMappingsToServer);
  document.getElementById("btn-load-sample-templates")?.addEventListener("click", loadSamplePresets);
  document.getElementById("btn-refresh-payload-preview")?.addEventListener("click", refreshPayloadPreview);

  // Auto-compose full path when AF Server, Database, Element, or Attribute change in modal
  ["modal-af-server", "modal-af-database", "modal-element-path", "modal-attr-name"].forEach(id => {
    document.getElementById(id)?.addEventListener("input", autoComposeFullPath);
  });
}

async function loadMappings() {
  try {
    const res = await fetch("/api/mappings");
    currentMappings = await res.json();
    renderMappingsTable();
  } catch (e) {
    console.error("Error loading mappings:", e);
  }
}

function renderMappingsTable() {
  const tbody = document.getElementById("mappings-table-tbody");
  const countBadge = document.getElementById("mappings-count-badge");
  if (!tbody) return;

  countBadge.textContent = currentMappings.length;

  if (currentMappings.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="8" style="text-align: center; color: var(--text-muted); padding: 2rem;">
          No attribute mappings defined yet. Click <strong>"Add New Mapping"</strong> or <strong>"Load Preset Templates"</strong> to get started.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = currentMappings.map((m, idx) => {
    const scaleRound = `×${m.scale_factor || 1.0}, ${m.round_decimals ?? 2} dec`;
    return `
      <tr>
        <td>
          <input type="checkbox" ${m.enabled ? 'checked' : ''} onchange="toggleMappingActive(${idx}, this.checked)" style="width: 16px; height: 16px; cursor: pointer;">
        </td>
        <td><strong>${escapeHtml(m.attribute_name || '')}</strong></td>
        <td><span class="path-code" title="${escapeHtml(m.full_path || '')}">${escapeHtml(m.full_path || '')}</span></td>
        <td><code>${escapeHtml(m.meter_tag || m.attribute_name || '')}</code></td>
        <td><code>${escapeHtml(m.target_field || 'readingValue')}</code></td>
        <td>${escapeHtml(m.uom || '--')}</td>
        <td style="font-size: 0.78rem; color: #64748b;">${scaleRound}</td>
        <td style="text-align: right;">
          <button class="btn btn-secondary btn-sm" onclick="editMapping(${idx})" style="padding: 0.2rem 0.5rem; margin-right: 0.3rem;">Edit</button>
          <button class="btn btn-danger btn-sm" onclick="deleteMapping(${idx})" style="padding: 0.2rem 0.5rem;">Delete</button>
        </td>
      </tr>
    `;
  }).join("");
}

function toggleMappingActive(idx, isChecked) {
  if (currentMappings[idx]) {
    currentMappings[idx].enabled = isChecked;
    refreshPayloadPreview();
  }
}

function editMapping(idx) {
  const m = currentMappings[idx];
  if (!m) return;
  openMappingModal(m, idx);
}

function deleteMapping(idx) {
  if (confirm(`Remove mapping for "${currentMappings[idx]?.attribute_name}"?`)) {
    currentMappings.splice(idx, 1);
    renderMappingsTable();
    saveMappingsToServer();
    refreshPayloadPreview();
  }
}

function openMappingModal(mapping = null, index = -1) {
  const modal = document.getElementById("mapping-modal");
  const title = document.getElementById("modal-title");
  modal.classList.add("active");

  if (mapping) {
    title.textContent = "Edit Attribute Mapping";
    document.getElementById("modal-mapping-id").value = index;
    document.getElementById("modal-attr-name").value = mapping.attribute_name || "";
    document.getElementById("modal-af-server").value = mapping.af_server || "PISRV01";
    document.getElementById("modal-af-database").value = mapping.af_database || "Plant_Operations";
    document.getElementById("modal-element-path").value = mapping.element_path || "";
    document.getElementById("modal-full-path").value = mapping.full_path || "";
    document.getElementById("modal-target-tag").value = mapping.meter_tag || "";
    document.getElementById("modal-target-field").value = mapping.target_field || "readingValue";
    document.getElementById("modal-uom").value = mapping.uom || "";
    document.getElementById("modal-scale").value = mapping.scale_factor ?? 1.0;
    document.getElementById("modal-decimals").value = mapping.round_decimals ?? 2;
    document.getElementById("modal-enabled").checked = mapping.enabled ?? true;
  } else {
    title.textContent = "Add Attribute Mapping";
    document.getElementById("modal-mapping-id").value = "-1";
    document.getElementById("mapping-form").reset();
    document.getElementById("modal-af-server").value = currentSettings?.pi_web_api?.af_server || "PISRV01";
    document.getElementById("modal-af-database").value = currentSettings?.pi_web_api?.af_database || "Plant_Operations";
    document.getElementById("modal-target-field").value = "readingValue";
    document.getElementById("modal-scale").value = "1.0";
    document.getElementById("modal-decimals").value = "2";
    document.getElementById("modal-enabled").checked = true;
  }
}

function closeMappingModal() {
  document.getElementById("mapping-modal").classList.remove("active");
}

function autoComposeFullPath() {
  const srv = document.getElementById("modal-af-server").value.trim();
  const db = document.getElementById("modal-af-database").value.trim();
  const elem = document.getElementById("modal-element-path").value.trim();
  const attr = document.getElementById("modal-attr-name").value.trim();

  if (srv && db && attr) {
    let full = `\\\\${srv}\\${db}`;
    if (elem) full += `\\${elem}`;
    full += `|${attr}`;
    document.getElementById("modal-full-path").value = full;
  }
}

function handleSaveMappingModal(e) {
  e.preventDefault();
  const editIdx = parseInt(document.getElementById("modal-mapping-id").value, 10);

  const newMapping = {
    id: editIdx >= 0 ? currentMappings[editIdx].id : `map-${Date.now()}`,
    attribute_name: document.getElementById("modal-attr-name").value.trim(),
    af_server: document.getElementById("modal-af-server").value.trim(),
    af_database: document.getElementById("modal-af-database").value.trim(),
    element_path: document.getElementById("modal-element-path").value.trim(),
    full_path: document.getElementById("modal-full-path").value.trim(),
    web_id: editIdx >= 0 ? currentMappings[editIdx].web_id : "",
    target_field: document.getElementById("modal-target-field").value.trim() || "readingValue",
    meter_tag: document.getElementById("modal-target-tag").value.trim(),
    target_tag_field: "meterCode",
    data_type: "number",
    transformation: "direct",
    scale_factor: parseFloat(document.getElementById("modal-scale").value) || 1.0,
    round_decimals: parseInt(document.getElementById("modal-decimals").value, 10) || 2,
    uom: document.getElementById("modal-uom").value.trim(),
    enabled: document.getElementById("modal-enabled").checked
  };

  if (editIdx >= 0) {
    currentMappings[editIdx] = newMapping;
  } else {
    currentMappings.push(newMapping);
  }

  closeMappingModal();
  renderMappingsTable();
  saveMappingsToServer();
  refreshPayloadPreview();
  showToast("Attribute mapping updated.", "success");
}

async function saveMappingsToServer() {
  try {
    const res = await fetch("/api/mappings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(currentMappings)
    });
    if (res.ok) {
      showToast("Mappings saved to config/mappings.json", "success");
    }
  } catch (e) {
    showToast("Failed to save mappings: " + e.message, "danger");
  }
}

function loadSamplePresets() {
  if (confirm("Load standard industrial asset telemetry presets (Boiler, Turbine, Generator, Pumps)?")) {
    currentMappings = [
      {
        id: "map-blr-temp",
        name: "Boiler 101 Steam Temperature",
        attribute_name: "Steam Temperature",
        af_server: "PISRV01",
        af_database: "Plant_Operations",
        element_path: "Unit 1\\Boilers\\Boiler-101",
        full_path: "\\\\PISRV01\\Plant_Operations\\Unit 1\\Boilers\\Boiler-101|Steam Temperature",
        target_field: "readingValue",
        meter_tag: "BLR101_STM_TEMP",
        target_tag_field: "meterCode",
        scale_factor: 1.0,
        round_decimals: 2,
        uom: "deg C",
        enabled: true
      },
      {
        id: "map-blr-press",
        name: "Boiler 101 Steam Pressure",
        attribute_name: "Steam Pressure",
        af_server: "PISRV01",
        af_database: "Plant_Operations",
        element_path: "Unit 1\\Boilers\\Boiler-101",
        full_path: "\\\\PISRV01\\Plant_Operations\\Unit 1\\Boilers\\Boiler-101|Steam Pressure",
        target_field: "readingValue",
        meter_tag: "BLR101_STM_PRESS",
        target_tag_field: "meterCode",
        scale_factor: 1.0,
        round_decimals: 2,
        uom: "bar",
        enabled: true
      },
      {
        id: "map-turb-flow",
        name: "Turbine Feedwater Flow Rate",
        attribute_name: "Feedwater Flow",
        af_server: "PISRV01",
        af_database: "Plant_Operations",
        element_path: "Unit 1\\Turbines\\Turbine-TG01",
        full_path: "\\\\PISRV01\\Plant_Operations\\Unit 1\\Turbines\\Turbine-TG01|Feedwater Flow",
        target_field: "readingValue",
        meter_tag: "TG01_FEED_FLOW",
        target_tag_field: "meterCode",
        scale_factor: 1.0,
        round_decimals: 1,
        uom: "m3/h",
        enabled: true
      },
      {
        id: "map-gen-pwr",
        name: "Generator Active Power Output",
        attribute_name: "Active Power",
        af_server: "PISRV01",
        af_database: "Plant_Operations",
        element_path: "Unit 1\\Generators\\Gen-01",
        full_path: "\\\\PISRV01\\Plant_Operations\\Unit 1\\Generators\\Gen-01|Active Power",
        target_field: "readingValue",
        meter_tag: "GEN01_ACT_PWR",
        target_tag_field: "meterCode",
        scale_factor: 1.0,
        round_decimals: 3,
        uom: "MW",
        enabled: true
      },
      {
        id: "map-pmp-vib",
        name: "Cooling Pump 2A Vibration",
        attribute_name: "Vibration Overall",
        af_server: "PISRV01",
        af_database: "Plant_Operations",
        element_path: "Utilities\\Pumps\\Pump-2A",
        full_path: "\\\\PISRV01\\Plant_Operations\\Utilities\\Pumps\\Pump-2A|Vibration Overall",
        target_field: "readingValue",
        meter_tag: "PMP2A_VIB_RMS",
        target_tag_field: "meterCode",
        scale_factor: 1.0,
        round_decimals: 2,
        uom: "mm/s",
        enabled: true
      }
    ];

    renderMappingsTable();
    saveMappingsToServer();
    refreshPayloadPreview();
    showToast("Loaded industrial telemetry presets.", "success");
  }
}

async function refreshPayloadPreview() {
  const box = document.getElementById("erp-payload-preview-box");
  if (!box) return;
  box.textContent = "Constructing payload preview...";
  try {
    const res = await fetch("/api/mappings/preview");
    const json = await res.json();
    box.textContent = JSON.stringify(json, null, 2);
  } catch (e) {
    box.textContent = "Error generating preview: " + e.message;
  }
}

// ============================================================
// 4. AF HIERARCHY TREE EXPLORER
// ============================================================
function initAFBrowser() {
  document.getElementById("btn-af-browse-root")?.addEventListener("click", () => browseAFPath("\\"));
  document.getElementById("btn-af-nav-up")?.addEventListener("click", navAFUpLevel);
}

async function browseAFPath(path) {
  currentAfPath = path;
  document.getElementById("af-current-path-display").value = path;
  const container = document.getElementById("af-browser-nodes");
  container.innerHTML = `<div style="padding: 0.5rem; color: #64748b;">Loading ${escapeHtml(path)}...</div>`;

  try {
    const res = await fetch(`/api/pi/browse?path=${encodeURIComponent(path)}`);
    const data = await res.json();
    const items = data.items || [];

    if (items.length === 0) {
      container.innerHTML = `<div style="padding: 0.5rem; color: #94a3b8;">No child elements or attributes found at this path.</div>`;
      return;
    }

    container.innerHTML = items.map(item => {
      const isAttr = item.type === "Attribute";
      const icon = isAttr
        ? `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="color: var(--primary);"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline></svg>`
        : `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="color: #f59e0b;"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>`;

      return `
        <div class="tree-node" onclick="handleAFNodeClick('${escapeHtml(item.path)}', '${escapeHtml(item.name)}', ${isAttr}, '${escapeHtml(item.uom || '')}')">
          ${icon}
          <span style="font-weight: 500;">${escapeHtml(item.name)}</span>
          <span style="color: #94a3b8; font-size: 0.72rem; margin-left: auto;">${escapeHtml(item.type)} ${item.uom ? `(${item.uom})` : ''}</span>
          ${isAttr ? `<button class="btn btn-outline btn-sm" style="font-size: 0.7rem; padding: 0.1rem 0.4rem;" onclick="event.stopPropagation(); quickAddFromAF('${escapeHtml(item.path)}', '${escapeHtml(item.name)}', '${escapeHtml(item.uom || '')}')">+ Map</button>` : ''}
        </div>
      `;
    }).join("");
  } catch (e) {
    container.innerHTML = `<div style="padding: 0.5rem; color: var(--danger);">Failed to browse AF: ${e.message}</div>`;
  }
}

window.handleAFNodeClick = function(path, name, isAttr, uom) {
  if (isAttr) {
    quickAddFromAF(path, name, uom);
  } else {
    browseAFPath(path);
  }
};

window.quickAddFromAF = function(path, name, uom) {
  // Parse elements from path: \\Server\DB\Elem1\Elem2|Attr
  let server = "PISRV01";
  let db = "Plant_Operations";
  let elemPath = "";

  if (path.startsWith("\\\\")) {
    const parts = path.substring(2).split("\\");
    if (parts.length > 0) server = parts[0];
    if (parts.length > 1) db = parts[1];
    if (parts.length > 2) {
      const rest = parts.slice(2).join("\\");
      const pipeIdx = rest.indexOf("|");
      elemPath = pipeIdx >= 0 ? rest.substring(0, pipeIdx) : rest;
    }
  }

  const cleanTag = name.toUpperCase().replace(/[^A-Z0-9]/g, "_");
  openMappingModal({
    attribute_name: name,
    af_server: server,
    af_database: db,
    element_path: elemPath,
    full_path: path,
    meter_tag: cleanTag,
    target_field: "readingValue",
    uom: uom || "",
    scale_factor: 1.0,
    round_decimals: 2,
    enabled: true
  });
};

function navAFUpLevel() {
  if (!currentAfPath || currentAfPath === "\\" || currentAfPath === "/") return;
  const parts = currentAfPath.split("\\").filter(Boolean);
  if (parts.length <= 1) {
    browseAFPath("\\");
  } else {
    parts.pop();
    browseAFPath("\\\\" + parts.join("\\"));
  }
}

// ============================================================
// 5. SETTINGS VIEW
// ============================================================
function initSettings() {
  document.getElementById("btn-save-settings")?.addEventListener("click", handleSaveSettings);
  document.getElementById("btn-test-pi-settings")?.addEventListener("click", handleTestPiSettings);
  document.getElementById("btn-test-erp-settings")?.addEventListener("click", handleTestErpSettings);

  document.getElementById("setting-pi-auth-type")?.addEventListener("change", handlePiAuthChange);
  document.getElementById("setting-erp-auth-type")?.addEventListener("change", handleErpAuthChange);

  initMockERPSimulator();

  loadSettingsIntoForm();
}

async function loadSettingsIntoForm() {
  try {
    const res = await fetch("/api/settings");
    currentSettings = await res.json();

    const pi = currentSettings.pi_web_api || {};
    const erp = currentSettings.oracle_erp || {};
    const pipe = currentSettings.pipeline || {};

    // PI Settings
    document.getElementById("setting-pi-url").value = pi.url || "";
    document.getElementById("setting-pi-auth-type").value = pi.auth_type || "basic";
    document.getElementById("setting-pi-username").value = pi.username || "";
    document.getElementById("setting-pi-password").value = pi.password || "";
    document.getElementById("setting-pi-bearer").value = pi.bearer_token || "";
    document.getElementById("setting-pi-af-server").value = pi.af_server || "PISRV01";
    document.getElementById("setting-pi-af-db").value = pi.af_database || "Plant_Operations";
    document.getElementById("setting-pi-verify-ssl").checked = !!pi.verify_ssl;
    document.getElementById("setting-pi-simulation").checked = !!pi.simulation_mode;

    // ERP Settings
    document.getElementById("setting-erp-enabled").checked = !!erp.enabled;
    document.getElementById("setting-erp-auth-type").value = erp.auth_type || "oauth2";
    document.getElementById("setting-erp-base-url").value = erp.base_url || "";
    document.getElementById("setting-erp-token-url").value = erp.token_url || "";
    document.getElementById("setting-erp-client-id").value = erp.client_id || "";
    document.getElementById("setting-erp-client-secret").value = erp.client_secret || "";
    document.getElementById("setting-erp-scope").value = erp.scope || "urn:opc:resource:consumer::all";
    document.getElementById("setting-erp-username").value = erp.username || "";
    document.getElementById("setting-erp-password").value = erp.password || "";
    document.getElementById("setting-erp-bearer-token").value = erp.bearer_token || "";
    document.getElementById("setting-erp-resource-endpoint").value = erp.resource_endpoint || "/fscmRestApi/resources/11.13.18.05/standardReceipts";
    document.getElementById("setting-erp-http-method").value = erp.http_method || "POST";
    document.getElementById("setting-erp-dry-run").checked = !!erp.dry_run;

    // Pipeline Settings
    document.getElementById("setting-pipeline-interval").value = pipe.interval_seconds || 30;

    handlePiAuthChange();
    handleErpAuthChange();

    await refreshMockERPStatus();
  } catch (e) {
    console.error("Error loading settings:", e);
  }
}

// ============================================================
// LOCAL ORACLE ERP CLOUD MOCK SIMULATOR CONTROLLER
// ============================================================
function initMockERPSimulator() {
  const btnStart = document.getElementById("btn-start-mock-erp");
  const btnStop = document.getElementById("btn-stop-mock-erp");
  const btnAutofill = document.getElementById("btn-autofill-mock-erp");
  const btnViewTxns = document.getElementById("btn-view-mock-txns");

  btnStart?.addEventListener("click", handleStartMockERP);
  btnStop?.addEventListener("click", handleStopMockERP);
  btnAutofill?.addEventListener("click", handleAutofillMockERP);
  btnViewTxns?.addEventListener("click", handleToggleMockTxns);
}

async function refreshMockERPStatus() {
  try {
    const res = await fetch("/api/mock-erp/status");
    if (!res.ok) return;
    const status = await res.json();

    const badge = document.getElementById("mock-erp-status-badge");
    const statusText = document.getElementById("mock-erp-status-text");
    const btnStart = document.getElementById("btn-start-mock-erp");
    const btnStop = document.getElementById("btn-stop-mock-erp");
    const txnsCount = document.getElementById("mock-txns-count");

    if (badge && statusText) {
      if (status.running) {
        badge.className = "badge badge-success";
        statusText.textContent = `Running (Port ${status.port})`;
      } else {
        badge.className = "badge badge-pending";
        statusText.textContent = "Stopped";
      }
    }

    if (btnStart) btnStart.style.display = status.running ? "none" : "inline-flex";
    if (btnStop) btnStop.style.display = status.running ? "inline-flex" : "none";
    if (txnsCount) txnsCount.textContent = status.transactions_count || 0;

    return status;
  } catch (e) {
    console.warn("Could not fetch mock ERP status:", e);
  }
}

async function handleStartMockERP() {
  try {
    const res = await fetch("/api/mock-erp/start", { method: "POST" });
    const data = await res.json();
    await refreshMockERPStatus();
    showToast(`Oracle ERP Cloud Simulator online on port ${data.port || 8080}`, "success");
  } catch (e) {
    showToast("Failed to start Oracle ERP simulator: " + e.message, "danger");
  }
}

async function handleStopMockERP() {
  try {
    const res = await fetch("/api/mock-erp/stop", { method: "POST" });
    await refreshMockERPStatus();
    showToast("Oracle ERP Cloud Simulator stopped.", "info");
  } catch (e) {
    showToast("Failed to stop Oracle ERP simulator: " + e.message, "danger");
  }
}

async function handleAutofillMockERP() {
  try {
    // 1. Start mock ERP server if not already running
    await fetch("/api/mock-erp/start", { method: "POST" });

    // 2. Apply mock configuration to settings.json
    const res = await fetch("/api/mock-erp/apply-to-settings", { method: "POST" });
    if (!res.ok) throw new Error("Server returned HTTP " + res.status);

    // 3. Reload settings into form so all input fields are updated
    await loadSettingsIntoForm();
    await refreshMockERPStatus();

    showToast("Mock ERP credentials filled & activated!", "success");

    // 4. Automatically trigger ERP connection test so the user immediately sees the green handshake
    setTimeout(handleTestErpSettings, 400);
  } catch (e) {
    showToast("Error configuring mock ERP settings: " + e.message, "danger");
  }
}

async function handleToggleMockTxns() {
  const preview = document.getElementById("mock-erp-transactions-preview");
  if (!preview) return;

  if (preview.style.display === "none" || !preview.style.display) {
    preview.style.display = "block";
    preview.textContent = "Loading received transactions...";
    try {
      const res = await fetch("/api/mock-erp/transactions");
      const data = await res.json();
      if (!data.items || data.items.length === 0) {
        preview.textContent = "No transactions received yet. Trigger a Pipeline Run from the Dashboard to dispatch telemetry.";
      } else {
        preview.textContent = JSON.stringify(data.items, null, 2);
      }
    } catch (e) {
      preview.textContent = "Failed to load transactions: " + e.message;
    }
  } else {
    preview.style.display = "none";
  }
}

function handlePiAuthChange() {
  const type = document.getElementById("setting-pi-auth-type").value;
  document.getElementById("group-pi-username").style.display = (type === "basic" || type === "kerberos") ? "flex" : "none";
  document.getElementById("group-pi-password").style.display = (type === "basic" || type === "kerberos") ? "flex" : "none";
  document.getElementById("group-pi-bearer").style.display = (type === "bearer") ? "flex" : "none";
}

function handleErpAuthChange() {
  const type = document.getElementById("setting-erp-auth-type").value;
  document.querySelectorAll(".erp-oauth-field").forEach(el => el.style.display = (type === "oauth2") ? "flex" : "none");
  document.querySelectorAll(".erp-basic-field").forEach(el => el.style.display = (type === "basic") ? "flex" : "none");
  document.querySelectorAll(".erp-bearer-field").forEach(el => el.style.display = (type === "bearer") ? "flex" : "none");
}

function collectSettingsFromForm() {
  return {
    pi_web_api: {
      url: document.getElementById("setting-pi-url").value.trim(),
      auth_type: document.getElementById("setting-pi-auth-type").value,
      username: document.getElementById("setting-pi-username").value.trim(),
      password: document.getElementById("setting-pi-password").value,
      bearer_token: document.getElementById("setting-pi-bearer").value.trim(),
      verify_ssl: document.getElementById("setting-pi-verify-ssl").checked,
      simulation_mode: document.getElementById("setting-pi-simulation").checked,
      af_server: document.getElementById("setting-pi-af-server").value.trim(),
      af_database: document.getElementById("setting-pi-af-db").value.trim(),
      timeout_seconds: 10
    },
    oracle_erp: {
      enabled: document.getElementById("setting-erp-enabled").checked,
      auth_type: document.getElementById("setting-erp-auth-type").value,
      base_url: document.getElementById("setting-erp-base-url").value.trim(),
      token_url: document.getElementById("setting-erp-token-url").value.trim(),
      client_id: document.getElementById("setting-erp-client-id").value.trim(),
      client_secret: document.getElementById("setting-erp-client-secret").value,
      scope: document.getElementById("setting-erp-scope").value.trim(),
      username: document.getElementById("setting-erp-username").value.trim(),
      password: document.getElementById("setting-erp-password").value,
      bearer_token: document.getElementById("setting-erp-bearer-token").value.trim(),
      resource_endpoint: document.getElementById("setting-erp-resource-endpoint").value.trim(),
      http_method: document.getElementById("setting-erp-http-method").value,
      dry_run: document.getElementById("setting-erp-dry-run").checked,
      custom_headers: {
        "Content-Type": "application/vnd.oracle.adf.resourceitem+json",
        "REST-Framework-Version": "4"
      },
      timeout_seconds: 15
    },
    pipeline: {
      interval_seconds: parseInt(document.getElementById("setting-pipeline-interval").value, 10) || 30,
      auto_start: true,
      max_history_items: 100
    }
  };
}

async function handleSaveSettings() {
  const newSettings = collectSettingsFromForm();
  try {
    const res = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(newSettings)
    });
    if (res.ok) {
      currentSettings = newSettings;
      showToast("Settings successfully saved to config/settings.json!", "success");
      loadDashboardData();
    } else {
      showToast("Error saving settings.", "danger");
    }
  } catch (e) {
    showToast("Save settings error: " + e.message, "danger");
  }
}

async function handleTestPiSettings() {
  const cfg = collectSettingsFromForm().pi_web_api;
  const box = document.getElementById("pi-test-result-box");
  box.style.display = "block";
  box.innerHTML = "Testing connection to AVEVA PI Web API endpoint...";

  try {
    const res = await fetch("/api/settings/test-pi", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cfg)
    });
    const result = await res.json();
    if (result.success) {
      box.className = "error-console";
      box.innerHTML = `<span style="color: var(--success); font-weight: bold;">✓ ${escapeHtml(result.message)}</span>\nLatency: ${result.latency_ms}ms\nHTTP Status: ${result.status_code}\n${JSON.stringify(result.details, null, 2)}`;
    } else {
      box.className = "error-console danger";
      box.innerHTML = `<span style="color: var(--danger); font-weight: bold;">✕ Connection Test Failed</span>\nMessage: ${escapeHtml(result.message)}\nError: ${escapeHtml(result.error || '')}`;
    }
  } catch (e) {
    box.className = "error-console danger";
    box.innerHTML = `Request Exception: ${escapeHtml(e.message)}`;
  }
}

async function handleTestErpSettings() {
  const cfg = collectSettingsFromForm().oracle_erp;
  const box = document.getElementById("erp-test-result-box");
  box.style.display = "block";
  box.innerHTML = "Validating Oracle ERP Cloud connection & token handshake...";

  try {
    const res = await fetch("/api/settings/test-erp", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cfg)
    });
    const result = await res.json();
    if (result.status === "PENDING_SETUP") {
      box.className = "error-console";
      box.innerHTML = `<span style="color: #f59e0b; font-weight: bold;">⚠ PENDING CONNECTION SETUP</span>\n${escapeHtml(result.message)}\n\nInstructions: When your Oracle Cloud ERP administrator provides your POD Base URL and OAuth Client Credentials, fill them above and toggle "Enable Oracle ERP Cloud Transmission".`;
    } else if (result.success) {
      box.className = "error-console";
      box.innerHTML = `<span style="color: var(--success); font-weight: bold;">✓ ${escapeHtml(result.message)}</span>\nLatency: ${result.latency_ms}ms\nEndpoint: ${escapeHtml(cfg.base_url + cfg.resource_endpoint)}\nResponse:\n${JSON.stringify(result.details, null, 2)}`;
    } else {
      box.className = "error-console danger";
      box.innerHTML = `<span style="color: var(--danger); font-weight: bold;">✕ Oracle ERP Handshake Failed</span>\nMessage: ${escapeHtml(result.message)}\nError Details:\n${escapeHtml(result.error || '')}`;
    }
  } catch (e) {
    box.className = "error-console danger";
    box.innerHTML = `Request Exception: ${escapeHtml(e.message)}`;
  }
}

// ============================================================
// 6. UTILITIES & TOASTS
// ============================================================
function showToast(message, type = "info") {
  const container = document.getElementById("toast-container");
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.textContent = message;

  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transition = "opacity 0.3s ease";
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

function formatTimestamp(isoStr) {
  if (!isoStr) return "--";
  try {
    const d = new Date(isoStr);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) + " " + d.toLocaleDateString([], { month: 'short', day: 'numeric' });
  } catch (e) {
    return isoStr;
  }
}

function escapeHtml(str) {
  if (typeof str !== "string") return String(str ?? "");
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
