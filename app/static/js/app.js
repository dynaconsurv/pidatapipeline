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
  initAFExplorerToggle();
  initInfoToggles();
  fetchSystemVersion();

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
  document.getElementById("btn-run-pull-table")?.addEventListener("click", triggerPullNow);
  document.getElementById("btn-refresh-pulls-table")?.addEventListener("click", loadDashboardData);
  document.getElementById("btn-refresh-logs")?.addEventListener("click", loadLogs);
  document.getElementById("log-filter-category")?.addEventListener("change", loadLogs);

  // Delivery Endpoint & JSON Staging actions
  document.getElementById("btn-copy-delivery-url")?.addEventListener("click", copyDeliveryEndpointUrl);
  document.getElementById("btn-simulate-delivery")?.addEventListener("click", triggerSimulateDelivery);
  document.getElementById("btn-simulate-table")?.addEventListener("click", triggerSimulateDelivery);
  document.getElementById("btn-dispatch-all-pending")?.addEventListener("click", dispatchAllPendingDeliveries);
  document.getElementById("btn-refresh-staging")?.addEventListener("click", loadDashboardData);

  // Staging Purge Modal actions
  document.getElementById("btn-card-clear-staging")?.addEventListener("click", openPurgeDeliveriesModal);
  document.getElementById("btn-clear-staged-deliveries")?.addEventListener("click", openPurgeDeliveriesModal);
  document.getElementById("btn-close-purge-modal")?.addEventListener("click", closePurgeDeliveriesModal);
  document.getElementById("btn-cancel-purge-modal")?.addEventListener("click", closePurgeDeliveriesModal);
  document.getElementById("btn-confirm-purge-deliveries")?.addEventListener("click", handleConfirmPurgeDeliveries);

  // Close purge modal when background clicked
  document.getElementById("modal-purge-deliveries")?.addEventListener("click", (e) => {
    if (e.target.id === "modal-purge-deliveries") {
      closePurgeDeliveriesModal();
    }
  });

  // Delivery JSON Modal controls
  document.getElementById("btn-close-delivery-modal")?.addEventListener("click", closeDeliveryModal);
  document.getElementById("btn-close-delivery-modal-2")?.addEventListener("click", closeDeliveryModal);
  document.getElementById("btn-copy-delivery-json")?.addEventListener("click", copyDeliveryJsonFromModal);
  document.getElementById("btn-modal-dispatch-oracle")?.addEventListener("click", dispatchCurrentModalDelivery);
  document.getElementById("btn-modal-delete-delivery")?.addEventListener("click", deleteCurrentModalDelivery);

  // Close modal when background clicked
  document.getElementById("modal-delivery-json")?.addEventListener("click", (e) => {
    if (e.target.id === "modal-delivery-json") {
      closeDeliveryModal();
    }
  });

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
  // 0. Toggle UI elements based on Active Ingestion Architecture Mode ('endpoint' vs 'pull')
  const mode = data.ingestion_mode || currentSettings?.pipeline?.ingestion_mode || "endpoint";
  const cardPiEndpoint = document.getElementById("card-pi-endpoint");
  const cardPiWebApi = document.getElementById("card-pi-webapi");
  const cardStagingQueue = document.getElementById("card-staging-queue");
  const cardScheduler = document.getElementById("card-scheduler");
  const sectionRecentDeliveries = document.getElementById("section-recent-deliveries");
  const sectionLastPulls = document.getElementById("section-last-pulls");

  if (mode === "pull") {
    if (cardPiEndpoint) cardPiEndpoint.style.display = "none";
    if (cardPiWebApi) cardPiWebApi.style.display = "";
    if (cardStagingQueue) cardStagingQueue.style.display = "none";
    if (cardScheduler) cardScheduler.style.display = "";
    if (sectionRecentDeliveries) sectionRecentDeliveries.style.display = "none";
    if (sectionLastPulls) sectionLastPulls.style.display = "block";
  } else {
    // endpoint mode
    if (cardPiEndpoint) cardPiEndpoint.style.display = "";
    if (cardPiWebApi) cardPiWebApi.style.display = "none";
    if (cardStagingQueue) cardStagingQueue.style.display = "";
    if (cardScheduler) cardScheduler.style.display = "none";
    if (sectionRecentDeliveries) sectionRecentDeliveries.style.display = "block";
    if (sectionLastPulls) sectionLastPulls.style.display = "none";
  }

  // 1. AVEVA PI Delivery Endpoint Card
  const deliv = data.delivery_endpoint || {};
  const delivBadge = document.getElementById("delivery-status-badge");
  const delivTotal = document.getElementById("delivery-total-val");
  const delivLast = document.getElementById("delivery-last-val");
  const delivPath = document.getElementById("delivery-path-val");

  if (delivTotal) delivTotal.textContent = deliv.total_received ?? 0;
  if (delivLast) {
    delivLast.textContent = deliv.last_received_at ? formatTimestamp(deliv.last_received_at) : "No push received yet";
  }
  if (delivBadge) {
    delivBadge.className = "badge badge-success";
    delivBadge.innerHTML = '<span class="badge-dot"></span> Listening';
  }

  // Also support legacy PI status fields if present
  const pi = data.pi_connection || {};
  const piBadge = document.getElementById("pi-status-badge");
  const piLatency = document.getElementById("pi-latency-val");
  const piEndpoint = document.getElementById("pi-endpoint-val");
  const piLastPull = document.getElementById("pi-last-pull-val");
  const piMode = document.getElementById("pi-mode-val");
  const piErrorBox = document.getElementById("pi-error-box");
  const piErrorText = document.getElementById("pi-error-text");

  if (currentSettings && currentSettings.pi_web_api && piEndpoint && piMode) {
    piEndpoint.textContent = currentSettings.pi_web_api.url || "--";
    piEndpoint.title = currentSettings.pi_web_api.url || "";
    piMode.textContent = currentSettings.pi_web_api.simulation_mode ? "Simulation Mode" : "Live PI Server";
  }

  if (piBadge && piLatency && piErrorBox) {
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
    } else if (pi.status === "WARNING") {
      piBadge.className = "badge badge-pending";
      piBadge.innerHTML = '<span class="badge-dot"></span> Mapping Warning';
      piLatency.textContent = pi.latency_ms !== null ? pi.latency_ms : "--";
      piErrorBox.style.display = "block";
      piErrorBox.className = "error-console warning";
      if (piErrorText) piErrorText.textContent = pi.error || pi.message || "PI Web API is online, but configured attribute path does not exist on this server.";
    } else if (pi.status === "PARTIAL_ERROR" || pi.status === "FAILED") {
      piBadge.className = "badge badge-danger";
      piBadge.innerHTML = `<span class="badge-dot"></span> ${pi.status === 'FAILED' ? 'Failed' : 'Partial Error'}`;
      piLatency.textContent = pi.latency_ms !== null ? pi.latency_ms : "--";
      piErrorBox.style.display = "block";
      piErrorBox.className = "error-console danger";
      if (piErrorText) piErrorText.textContent = pi.error || pi.message || "Unknown error connecting to PI Web API";
    }
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
    if (erpAuth) erpAuth.textContent = (currentSettings.oracle_erp.auth_type || "OAuth 2.0").toUpperCase();
    if (erpResource) {
      erpResource.textContent = currentSettings.oracle_erp.resource_endpoint || "--";
      erpResource.title = currentSettings.oracle_erp.resource_endpoint || "";
    }
  }

  if (erpBanner) erpBanner.style.display = "none";

  if (erpBadge && erpHeadline && erpReason) {
    if (erp.status === "PENDING_SETUP") {
      erpBadge.className = "badge badge-pending";
      erpBadge.innerHTML = '<span class="badge-dot"></span> Pending Setup';
      erpHeadline.textContent = "Pending Setup";
      erpHeadline.style.color = "#b45309";
      erpReason.textContent = "Awaiting destination config";
      erpReason.style.color = "#b45309";
      if (erpErrorBox) erpErrorBox.style.display = "none";
    } else if (erp.status === "CONNECTED") {
      erpBadge.className = "badge badge-success";
      erpBadge.innerHTML = '<span class="badge-dot"></span> Connected';
      erpHeadline.textContent = "Connected";
      erpHeadline.style.color = "var(--success)";
      erpReason.textContent = "Online & Authenticated";
      erpReason.style.color = "var(--success)";
      if (erpErrorBox) erpErrorBox.style.display = "none";
    } else if (erp.status === "FAILED") {
      erpBadge.className = "badge badge-danger";
      erpBadge.innerHTML = '<span class="badge-dot"></span> Connection Error';
      erpHeadline.textContent = "Failed";
      erpHeadline.style.color = "var(--danger)";
      erpReason.textContent = erp.message || "Failed";
      erpReason.style.color = "var(--danger)";
      if (erpErrorBox) {
        erpErrorBox.style.display = "block";
        if (erpErrorText) erpErrorText.textContent = erp.error || erp.message || "Error communicating with Oracle ERP Cloud";
      }
    }
  }

  // 3. JSON Staging Queue Card
  const stagingPending = document.getElementById("staging-pending-val");
  const stagingPendingUnit = document.getElementById("staging-pending-unit");
  const stagingTotal = document.getElementById("staging-total-val");
  const stagingBadge = document.getElementById("staging-status-badge");

  const pendingCount = deliv.pending_oracle_count ?? 0;
  const failedCount = deliv.failed_count ?? 0;
  if (stagingPending) stagingPending.textContent = pendingCount;
  if (stagingPendingUnit) {
    if (failedCount > 0) {
      stagingPendingUnit.textContent = `${failedCount} failed (auto-retrying)`;
    } else if (pendingCount > 0) {
      stagingPendingUnit.textContent = "pending setup / retry";
    } else {
      stagingPendingUnit.textContent = "failed / pending (all synced)";
    }
  }
  if (stagingTotal) stagingTotal.textContent = `${deliv.total_received ?? 0} records`;
  if (stagingBadge) {
    if (failedCount > 0) {
      stagingBadge.className = "badge badge-danger";
      stagingBadge.innerHTML = `<span class="badge-dot"></span> ${failedCount} Failed (Retrying)`;
    } else if (pendingCount > 0) {
      stagingBadge.className = "badge badge-pending";
      stagingBadge.innerHTML = '<span class="badge-dot"></span> Pending Setup';
    } else {
      stagingBadge.className = "badge badge-success";
      stagingBadge.innerHTML = '<span class="badge-dot"></span> Auto-Dispatched';
    }
  }

  // Legacy scheduler controls support
  const sched = data.scheduler || {};
  secondsLeft = sched.seconds_remaining || 0;
  updateCountdownDisplay(secondsLeft);

  const schedBadge = document.getElementById("scheduler-badge");
  const schedInterval = document.getElementById("scheduler-interval-val");
  const schedNext = document.getElementById("scheduler-next-val");
  const pauseBtn = document.getElementById("btn-toggle-pause");
  const pauseText = document.getElementById("btn-pause-text");

  if (schedInterval) schedInterval.textContent = `Every ${sched.interval_seconds || 30}s`;
  if (schedNext) schedNext.textContent = sched.next_run_at ? formatTimestamp(sched.next_run_at) : "--";

  if (schedBadge && pauseText) {
    if (sched.is_paused) {
      schedBadge.className = "badge badge-pending";
      schedBadge.innerHTML = '<span class="badge-dot"></span> Paused';
      pauseText.textContent = "Resume";
    } else {
      schedBadge.className = "badge badge-success";
      schedBadge.innerHTML = '<span class="badge-dot"></span> Active';
      pauseText.textContent = "Pause";
    }
  }

  // 4. Last Data Published Card
  const pub = data.last_publish || {};
  const pubBadge = document.getElementById("last-publish-badge");
  const pubCount = document.getElementById("publish-count-val");
  const pubStatus = document.getElementById("publish-status-val");
  const pubTime = document.getElementById("publish-time-val");
  const pubHttp = document.getElementById("publish-http-val");

  if (pubCount) pubCount.textContent = pub.record_count || 0;
  if (pubTime) pubTime.textContent = pub.timestamp ? formatTimestamp(pub.timestamp) : "--";
  if (pubHttp) pubHttp.textContent = pub.http_code ? `HTTP ${pub.http_code}` : (pub.status === "PENDING_SETUP" ? "Pending setup" : "--");

  if (pubBadge && pubStatus) {
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
  }

  // 5. Recent 5 Received Deliveries Table
  renderRecentDeliveriesTable(data.recent_5_deliveries || []);

  // Backward compatibility: render last_5_pulls if element exists
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

function renderLastPullsTable(triggers) {
  const tbody = document.getElementById("last-pulls-tbody");
  if (!tbody) return;

  if (!triggers || triggers.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="5" style="text-align: center; color: var(--ink-secondary); padding: 2rem;">
          No active telemetry data pulled yet. Ensure attribute mappings are active and click <strong>"Pull Now"</strong> above.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = triggers.map(entry => {
    // Normalization & backward compatibility check
    let tr = entry;
    if (!tr.items && tr.attribute_name) {
      tr = {
        triggered_at: tr.batch_timestamp || tr.timestamp,
        ingested_at: tr.timestamp,
        quality: tr.quality,
        items: [{
          attribute_name: tr.attribute_name,
          meter_tag: tr.meter_tag,
          value: tr.value,
          uom: tr.uom,
          error: tr.error
        }]
      };
    }

    // Quality / Status badge
    let qualityBadge;
    if (tr.quality === "Good") {
      qualityBadge = `<span class="badge badge-success"><span class="badge-dot"></span> Good</span>`;
    } else if (tr.quality === "Partial") {
      qualityBadge = `<span class="badge badge-pending"><span class="badge-dot"></span> Partial</span>`;
    } else if (tr.quality === "Questionable") {
      qualityBadge = `<span class="badge badge-pending"><span class="badge-dot"></span> Questionable</span>`;
    } else {
      qualityBadge = `<span class="badge badge-danger"><span class="badge-dot"></span> ${escapeHtml(tr.quality || 'Failed')}</span>`;
    }

    const items = tr.items || [];

    // Render ERP Meter Tag(s)
    const meterTagsHtml = items.length > 0
      ? items.map(it => `
          <div style="margin: 4px 0;">
            <code style="font-family: var(--font-mono); font-size: 11px; background: var(--bg-subtle); padding: 2px 6px; border-radius: 4px; border: 1px solid var(--border); color: var(--ink-primary); display: inline-block;">
              ${escapeHtml(it.meter_tag || '--')}
            </code>
          </div>
        `).join("")
      : '<span style="color: var(--ink-tertiary);">--</span>';

    // Render Attribute(s) Name & Value
    const attrsHtml = items.length > 0
      ? items.map(it => {
          const hasVal = it.value !== null && it.value !== undefined;
          const valDisplay = hasVal
            ? `<strong style="font-family: var(--font-mono); font-weight: 600; color: var(--ink-primary);">${it.value}</strong> <span style="font-size: 11px; color: var(--ink-secondary);">${escapeHtml(it.uom || '')}</span>`
            : `<span style="color: var(--status-bad); font-size: 11px;">${escapeHtml(it.error || 'N/A')}</span>`;

          return `
            <div style="margin: 4px 0; font-size: 12px; display: flex; align-items: baseline; gap: 8px;">
              <span style="font-weight: 500; color: var(--ink-secondary); min-width: 120px;">${escapeHtml(it.attribute_name)}:</span>
              <span>${valDisplay}</span>
            </div>
          `;
        }).join("")
      : '<span style="color: var(--ink-tertiary);">--</span>';

    return `
      <tr>
        <td style="font-family: var(--font-mono); font-size: 11px; white-space: nowrap; color: var(--ink-primary); font-weight: 500; vertical-align: top; padding-top: 12px;">
          ${formatTimestamp(tr.triggered_at)}
        </td>
        <td style="font-family: var(--font-mono); font-size: 11px; white-space: nowrap; color: var(--ink-secondary); vertical-align: top; padding-top: 12px;">
          ${formatTimestamp(tr.ingested_at || tr.triggered_at)}
        </td>
        <td style="vertical-align: top; padding-top: 9px;">
          ${meterTagsHtml}
        </td>
        <td style="vertical-align: top; padding-top: 9px;">
          ${attrsHtml}
        </td>
        <td style="vertical-align: top; padding-top: 12px; white-space: nowrap;">
          ${qualityBadge}
        </td>
      </tr>
    `;
  }).join("");
}

// ============================================================
// RECENT 5 RECEIVED DELIVERIES TABLE & MODAL ACTIONS
// ============================================================
let currentInspectedDelivery = null;

function renderRecentDeliveriesTable(deliveries) {
  const tbody = document.getElementById("recent-deliveries-tbody");
  if (!tbody) return;

  if (!deliveries || deliveries.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="5" style="text-align: center; color: var(--ink-secondary); padding: 2.5rem 1rem;">
          <div style="font-weight: 500; font-size: 13px; color: var(--ink-primary); margin-bottom: 6px;">
            Waiting for data from PI AF Notifications
          </div>
          <div style="font-size: 12px; color: var(--ink-secondary); margin-bottom: 12px;">
            Configure your PI AF Notification Delivery Endpoint to POST to <code style="font-family: var(--font-mono); font-size: 11px;">/api/v1/delivery</code>, or simulate a test push below:
          </div>
          <div style="display: inline-flex; gap: 8px;">
            <button type="button" class="btn btn-primary btn-sm" onclick="triggerSimulateDelivery()">
              + Simulate Sample Push
            </button>
            <button type="button" class="btn btn-secondary btn-sm" onclick="copyDeliveryEndpointUrl()">
              Copy Endpoint URL
            </button>
          </div>
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = deliveries.map(deliv => {
    // 1. Received At
    const timeFormatted = formatTimestamp(deliv.received_at);
    const clientIp = deliv.client_ip || "Unknown";
    const shortId = deliv.delivery_id || "";

    // 2. Notification / Target
    const notifName = escapeHtml(deliv.notification_name || "PI Notification");
    const eventType = escapeHtml(deliv.event_type || "Update");
    const targetPath = escapeHtml(deliv.target_path || "--");

    // 3. Attributes & Values
    const attrs = deliv.attributes_summary || [];
    let attrsHtml = "";
    if (attrs.length === 0) {
      if (deliv.event_type === "Test Ping" || (!deliv.raw_payload || Object.keys(deliv.raw_payload).length === 0)) {
        attrsHtml = `<span class="badge badge-info" style="font-size: 11px; padding: 2px 7px;"><span class="badge-dot"></span> Test Notification Ping (Empty Payload)</span>`;
      } else {
        attrsHtml = `<span style="color: var(--ink-tertiary); font-size: 11px;">No attributes parsed</span>`;
      }
    } else {
      const displayAttrs = attrs.slice(0, 3);
      const remaining = attrs.length - displayAttrs.length;
      attrsHtml = displayAttrs.map(a => {
        // Defensive unwrap: if an old record has an array of Items, unroll them cleanly
        if (Array.isArray(a.value)) {
          return a.value.map(it => {
            const subName = it.Name || it.name || it.Attribute || it.attribute || "Item";
            const subVal = it.Value !== undefined ? it.Value : (it.value !== undefined ? it.value : JSON.stringify(it));
            const subUom = it.UOM || it.uom ? ` ${escapeHtml(it.UOM || it.uom)}` : "";
            return `
              <div style="margin: 3px 0; font-size: 12px; display: flex; align-items: baseline; gap: 6px;">
                <span style="font-weight: 500; color: var(--ink-secondary); min-width: 120px;">${escapeHtml(subName)}:</span>
                <strong style="font-family: var(--font-mono); font-weight: 600; color: var(--ink-primary);">${escapeHtml(String(subVal))}</strong>
                <span style="font-size: 11px; color: var(--ink-tertiary);">${subUom}</span>
              </div>
            `;
          }).join("");
        }

        let valStr = "N/A";
        if (a.value !== null && a.value !== undefined) {
          if (typeof a.value === "object") {
            try {
              valStr = JSON.stringify(a.value);
            } catch (e) {
              valStr = String(a.value);
            }
          } else {
            valStr = String(a.value);
          }
        }
        const uom = a.uom ? ` ${escapeHtml(a.uom)}` : "";
        return `
          <div style="margin: 3px 0; font-size: 12px; display: flex; align-items: baseline; gap: 6px;">
            <span style="font-weight: 500; color: var(--ink-secondary); min-width: 120px;">${escapeHtml(a.name)}:</span>
            <strong style="font-family: var(--font-mono); font-weight: 600; color: var(--ink-primary);">${escapeHtml(valStr)}</strong>
            <span style="font-size: 11px; color: var(--ink-tertiary);">${uom}</span>
          </div>
        `;
      }).join("");

      if (remaining > 0) {
        attrsHtml += `
          <div style="font-size: 11px; color: var(--ink-tertiary); margin-top: 2px;">
            +${remaining} more attribute(s)...
          </div>
        `;
      }
    }

    // 4. Staging Status badge
    let statusBadge = "";
    if (deliv.oracle_status === "DISPATCHED") {
      statusBadge = `<span class="badge badge-success" title="Successfully dispatched to Oracle ERP"><span class="badge-dot"></span> Dispatched to Oracle</span>`;
    } else if (deliv.oracle_status === "FAILED") {
      const retryCount = deliv.retry_count || 0;
      const retryLabel = retryCount > 0 ? `Failed (Retry #${retryCount})` : `Failed (Retry Queued)`;
      const errMsg = escapeHtml(deliv.oracle_dispatch?.message || deliv.oracle_dispatch?.error || "Dispatch failed. Will retry on next scheduled interval.");
      statusBadge = `<span class="badge badge-danger" title="${errMsg}"><span class="badge-dot"></span> ${retryLabel}</span>`;
    } else if (deliv.oracle_status === "PENDING_SETUP") {
      statusBadge = `<span class="badge badge-pending" title="Oracle ERP credentials pending setup in Settings"><span class="badge-dot"></span> Pending Setup</span>`;
    } else {
      statusBadge = `<span class="badge badge-pending" title="Held in JSON staging"><span class="badge-dot"></span> Staged in JSON</span>`;
    }

    // 5. Actions
    return `
      <tr>
        <td style="vertical-align: top; padding-top: 12px;">
          <div style="font-family: var(--font-mono); font-size: 11px; font-weight: 500; color: var(--ink-primary); white-space: nowrap;">
            ${timeFormatted}
          </div>
          <div style="font-size: 11px; color: var(--ink-secondary); margin-top: 2px; font-family: var(--font-mono);">
            ${escapeHtml(clientIp)}
          </div>
          <div style="font-size: 10px; color: var(--ink-tertiary); font-family: var(--font-mono); margin-top: 2px;">
            #${escapeHtml(shortId.slice(-10))}
          </div>
        </td>
        <td style="vertical-align: top; padding-top: 12px;">
          <div style="display: flex; align-items: center; gap: 6px;">
            <strong style="font-size: 12px; color: var(--ink-primary);">${notifName}</strong>
            <span class="badge badge-info" style="font-size: 10px; padding: 1px 5px;">${eventType}</span>
          </div>
          <div style="font-size: 11px; color: var(--ink-secondary); font-family: var(--font-mono); margin-top: 4px; word-break: break-all;">
            ${targetPath}
          </div>
          <div style="font-size: 11px; color: var(--ink-tertiary); margin-top: 2px;">
            ${deliv.attribute_count || attrs.length} attribute(s)
          </div>
        </td>
        <td style="vertical-align: top; padding-top: 10px;">
          ${attrsHtml}
        </td>
        <td style="vertical-align: top; padding-top: 12px; white-space: nowrap;">
          ${statusBadge}
          <div style="font-size: 10px; color: var(--ink-tertiary); margin-top: 4px; font-family: var(--font-mono);">
            received_deliveries.json
          </div>
        </td>
        <td style="vertical-align: top; padding-top: 10px; text-align: right; white-space: nowrap;">
          <div style="display: flex; flex-direction: column; gap: 6px; align-items: flex-end;">
            <div style="display: flex; gap: 4px;">
              <button type="button" class="btn btn-secondary btn-sm" onclick="inspectDelivery('${escapeHtml(deliv.delivery_id)}')">
                Inspect
              </button>
              <button type="button" class="btn btn-danger btn-sm" onclick="deleteDeliveryRecord('${escapeHtml(deliv.delivery_id)}')" title="Delete this delivery from data/received_deliveries.json">
                Delete
              </button>
            </div>
            ${deliv.oracle_status !== "DISPATCHED" ? `
              <button type="button" class="btn btn-outline btn-sm" onclick="dispatchSingleDelivery('${escapeHtml(deliv.delivery_id)}')">
                Send to Oracle
              </button>
            ` : `
              <span style="font-size: 11px; color: var(--status-good); display: inline-flex; align-items: center; gap: 3px;">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor"><polyline points="20 6 9 17 4 12"></polyline></svg> Dispatched
              </span>
            `}
          </div>
        </td>
      </tr>
    `;
  }).join("");
}

async function copyDeliveryEndpointUrl() {
  const fullUrl = `${window.location.origin}/api/v1/delivery`;
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(fullUrl);
    } else {
      const tmp = document.createElement("textarea");
      tmp.value = fullUrl;
      document.body.appendChild(tmp);
      tmp.select();
      document.execCommand("copy");
      document.body.removeChild(tmp);
    }
    showToast(`Copied Endpoint URL to clipboard: ${fullUrl}`, "success");
  } catch (err) {
    showToast(`Delivery URL: ${fullUrl}`, "info");
  }
}

async function triggerSimulateDelivery() {
  showToast("Simulating PI AF Notification push delivery...", "info");
  try {
    const res = await fetch("/api/deliveries/simulate", { method: "POST" });
    const data = await res.json();
    if (data.success) {
      showToast("Simulated delivery received and staged into data/received_deliveries.json!", "success");
      await loadDashboardData();
    } else {
      showToast("Failed to simulate delivery: " + (data.message || "Unknown error"), "danger");
    }
  } catch (err) {
    showToast("Error simulating delivery: " + err.message, "danger");
  }
}

async function dispatchAllPendingDeliveries() {
  showToast("Forwarding pending staged deliveries to Oracle ERP Cloud...", "info");
  try {
    const res = await fetch("/api/deliveries/dispatch-pending", { method: "POST" });
    const data = await res.json();
    if (data.success) {
      const r = data.result || {};
      if (r.total_pending === 0) {
        showToast("No pending deliveries in staging queue.", "info");
      } else {
        showToast(`Forwarded: ${r.dispatched} dispatched, ${r.failed} failed out of ${r.total_pending} pending.`, "success");
      }
      await loadDashboardData();
    } else {
      showToast("Failed forwarding to Oracle ERP: " + (data.message || "Unknown error"), "danger");
    }
  } catch (err) {
    showToast("Error forwarding deliveries: " + err.message, "danger");
  }
}

async function inspectDelivery(deliveryId) {
  try {
    const res = await fetch(`/api/deliveries/${deliveryId}`);
    if (!res.ok) {
      showToast("Failed to load delivery record", "danger");
      return;
    }
    const data = await res.json();
    currentInspectedDelivery = data;

    const modal = document.getElementById("modal-delivery-json");
    const titleEl = document.getElementById("modal-delivery-title");
    const subEl = document.getElementById("modal-delivery-subtitle");
    const jsonEl = document.getElementById("modal-delivery-json-content");
    const metaEl = document.getElementById("modal-delivery-meta");
    const dispatchBtn = document.getElementById("btn-modal-dispatch-oracle");

    if (titleEl) titleEl.textContent = `PI Delivery: ${data.notification_name || "Notification"}`;
    if (subEl) subEl.textContent = `ID: ${data.delivery_id} · Received: ${formatTimestamp(data.received_at)} from ${data.client_ip || "Unknown"}`;
    if (jsonEl) jsonEl.textContent = JSON.stringify(data.raw_payload || data, null, 2);
    if (metaEl) {
      metaEl.innerHTML = `Status: <strong>${data.oracle_status}</strong> · Attributes: <strong>${data.attribute_count || 0}</strong>`;
    }
    if (dispatchBtn) {
      dispatchBtn.style.display = data.oracle_status === "DISPATCHED" ? "none" : "inline-block";
    }

    if (modal) modal.classList.add("active");
  } catch (err) {
    showToast("Error inspecting delivery: " + err.message, "danger");
  }
}

function closeDeliveryModal() {
  const modal = document.getElementById("modal-delivery-json");
  if (modal) modal.classList.remove("active");
}

function copyDeliveryJsonFromModal() {
  const jsonEl = document.getElementById("modal-delivery-json-content");
  if (!jsonEl) return;
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(jsonEl.textContent);
    } else {
      const tmp = document.createElement("textarea");
      tmp.value = jsonEl.textContent;
      document.body.appendChild(tmp);
      tmp.select();
      document.execCommand("copy");
      document.body.removeChild(tmp);
    }
    showToast("Raw JSON copied to clipboard!", "success");
  } catch (err) {
    showToast("Failed to copy JSON", "danger");
  }
}

async function dispatchCurrentModalDelivery() {
  if (!currentInspectedDelivery) return;
  const id = currentInspectedDelivery.delivery_id;
  await dispatchSingleDelivery(id);
  closeDeliveryModal();
}

async function dispatchSingleDelivery(deliveryId) {
  showToast(`Dispatching delivery ${deliveryId} to Oracle ERP Cloud...`, "info");
  try {
    const res = await fetch(`/api/deliveries/${deliveryId}/dispatch`, { method: "POST" });
    const data = await res.json();
    if (data.success) {
      const result = data.result || {};
      if (result.status === "DISPATCHED") {
        showToast("Successfully dispatched to Oracle ERP Cloud!", "success");
      } else if (result.status === "PENDING_SETUP") {
        showToast("Oracle ERP is in PENDING_SETUP mode. Record held staged in JSON.", "info");
      } else {
        showToast("Oracle ERP dispatch failed: " + (result.message || "Unknown error"), "danger");
      }
      await loadDashboardData();
    } else {
      showToast("Dispatch failed: " + (data.message || "Unknown error"), "danger");
    }
  } catch (err) {
    showToast("Error dispatching delivery: " + err.message, "danger");
  }
}

// ------------------------------------------------------------
// Delivery Record Deletion & Staging Purge Functions
// ------------------------------------------------------------
window.deleteDeliveryRecord = async function(deliveryId) {
  if (!confirm(`Are you sure you want to delete delivery record #${deliveryId}?\n\nThis will permanently remove it from data/received_deliveries.json.`)) {
    return;
  }
  showToast(`Deleting delivery ${deliveryId}...`, "info");
  try {
    const res = await fetch(`/api/deliveries/${encodeURIComponent(deliveryId)}`, { method: "DELETE" });
    const data = await res.json();
    if (res.ok && data.success) {
      showToast("Delivery record successfully deleted from JSON storage.", "success");
      if (currentInspectedDelivery && currentInspectedDelivery.delivery_id === deliveryId) {
        closeDeliveryModal();
      }
      await loadDashboardData();
    } else {
      showToast("Failed to delete delivery: " + (data.detail || data.message || "Unknown error"), "danger");
    }
  } catch (err) {
    showToast("Error deleting delivery: " + err.message, "danger");
  }
};

async function deleteCurrentModalDelivery() {
  if (!currentInspectedDelivery) return;
  const id = currentInspectedDelivery.delivery_id;
  await deleteDeliveryRecord(id);
}

function openPurgeDeliveriesModal() {
  const modal = document.getElementById("modal-purge-deliveries");
  if (modal) modal.classList.add("active");
}

function closePurgeDeliveriesModal() {
  const modal = document.getElementById("modal-purge-deliveries");
  if (modal) modal.classList.remove("active");
}

async function handleConfirmPurgeDeliveries() {
  const selectedOption = document.querySelector('input[name="purge-deliveries-option"]:checked')?.value || "PENDING";
  let filterDesc = "pending/failed test deliveries";
  if (selectedOption === "ALL") filterDesc = "ALL staged deliveries";
  else if (selectedOption === "DISPATCHED") filterDesc = "all successfully dispatched deliveries";

  showToast(`Purging ${filterDesc}...`, "info");
  try {
    const res = await fetch(`/api/deliveries?filter=${encodeURIComponent(selectedOption)}`, { method: "DELETE" });
    const data = await res.json();
    if (res.ok && data.success) {
      showToast(`Purged ${data.deleted_count} staged deliveries from data/received_deliveries.json.`, "success");
      closePurgeDeliveriesModal();
      await loadDashboardData();
    } else {
      showToast("Purge failed: " + (data.detail || data.message || "Unknown error"), "danger");
    }
  } catch (err) {
    showToast("Error purging deliveries: " + err.message, "danger");
  }
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

function initAFExplorerToggle() {
  const btn = document.getElementById("btn-toggle-af-explorer");
  const section = document.getElementById("af-explorer-section");
  const text = document.getElementById("btn-toggle-af-explorer-text");
  if (!btn || !section) return;

  btn.addEventListener("click", () => {
    const isHidden = section.style.display === "none" || !section.style.display;
    if (isHidden) {
      section.style.display = "block";
      if (text) text.textContent = "Hide AF Explorer";
      btn.classList.remove("btn-secondary");
      btn.classList.add("btn-primary");
      const currentVal = document.getElementById("af-current-path-display")?.value;
      if (!currentVal || currentVal === "\\") {
        browseAFPath("\\");
      }
    } else {
      section.style.display = "none";
      if (text) text.textContent = "Show AF Explorer";
      btn.classList.remove("btn-primary");
      btn.classList.add("btn-secondary");
    }
  });
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

  // Ingestion Mode Toggle Listeners
  document.querySelectorAll('input[name="setting-ingestion-mode"]').forEach(radio => {
    radio.addEventListener("change", handleIngestionModeChange);
  });

  // Guide Action Buttons
  document.getElementById("btn-guide-copy-url")?.addEventListener("click", copyDeliveryEndpointUrl);
  document.getElementById("btn-guide-copy-url-2")?.addEventListener("click", copyDeliveryEndpointUrl);
  document.getElementById("btn-guide-simulate-push")?.addEventListener("click", triggerSimulateDelivery);

  initMockERPSimulator();
  initUpdatesController();

  // Data Storage & Production Pre-Flight Cleanup Listeners
  document.getElementById("btn-purge-deliveries-pending")?.addEventListener("click", () => handlePurgeDeliveriesQuick("PENDING"));
  document.getElementById("btn-purge-deliveries-all")?.addEventListener("click", () => handlePurgeDeliveriesQuick("ALL"));
  document.getElementById("btn-purge-pull-history")?.addEventListener("click", () => handlePurgeStorageTarget("pull_history", "PI Pull History"));
  document.getElementById("btn-purge-publish-history")?.addEventListener("click", () => handlePurgeStorageTarget("publish_history", "ERP Publish History"));
  document.getElementById("btn-purge-logs")?.addEventListener("click", () => handlePurgeStorageTarget("logs", "Activity Logs"));
  document.getElementById("btn-preflight-purge-all")?.addEventListener("click", handlePreflightPurgeAll);

  loadSettingsIntoForm();
}

function handleIngestionModeChange() {
  const selectedMode = document.querySelector('input[name="setting-ingestion-mode"]:checked')?.value || "endpoint";
  const guideContainer = document.getElementById("container-pi-endpoint-guide");
  const webapiContainer = document.getElementById("container-pi-webapi-settings");
  const cardEndpoint = document.getElementById("mode-card-endpoint");
  const cardPull = document.getElementById("mode-card-pull");

  if (selectedMode === "endpoint") {
    if (guideContainer) guideContainer.style.display = "block";
    if (webapiContainer) webapiContainer.style.display = "none";
    if (cardEndpoint) {
      cardEndpoint.style.border = "2px solid var(--ink-primary)";
      cardEndpoint.style.boxShadow = "0 1px 3px rgba(0,0,0,0.06)";
    }
    if (cardPull) {
      cardPull.style.border = "1px solid var(--border)";
      cardPull.style.boxShadow = "none";
    }
  } else {
    if (guideContainer) guideContainer.style.display = "none";
    if (webapiContainer) webapiContainer.style.display = "block";
    if (cardPull) {
      cardPull.style.border = "2px solid var(--ink-primary)";
      cardPull.style.boxShadow = "0 1px 3px rgba(0,0,0,0.06)";
    }
    if (cardEndpoint) {
      cardEndpoint.style.border = "1px solid var(--border)";
      cardEndpoint.style.boxShadow = "none";
    }
  }
}

async function loadSettingsIntoForm() {
  try {
    const res = await fetch("/api/settings");
    currentSettings = await res.json();

    const pi = currentSettings.pi_web_api || {};
    const erp = currentSettings.oracle_erp || {};
    const pipe = currentSettings.pipeline || {};

    // Ingestion Mode Selection
    const mode = pipe.ingestion_mode || "endpoint";
    const radioToSelect = document.getElementById(`mode-radio-${mode}`);
    if (radioToSelect) {
      radioToSelect.checked = true;
    }
    handleIngestionModeChange();

    // Auto-update URLs in guide
    const currentOrigin = window.location.origin;
    const fullDeliveryUrl = `${currentOrigin}/api/v1/delivery`;
    const guideInput = document.getElementById("guide-endpoint-url-input");
    const guideTableUrl = document.getElementById("guide-table-url");
    if (guideInput) guideInput.value = fullDeliveryUrl;
    if (guideTableUrl) guideTableUrl.textContent = fullDeliveryUrl;

    // PI Settings
    document.getElementById("setting-pi-url").value = pi.url || "";
    document.getElementById("setting-pi-auth-type").value = pi.auth_type || "basic";
    document.getElementById("setting-pi-username").value = pi.username || "";
    document.getElementById("setting-pi-password").value = pi.password || "";
    document.getElementById("setting-pi-bearer").value = pi.bearer_token || "";
    document.getElementById("setting-pi-token-url").value = pi.token_url || "";
    document.getElementById("setting-pi-client-id").value = pi.client_id || "";
    document.getElementById("setting-pi-client-secret").value = pi.client_secret || "";
    document.getElementById("setting-pi-scope").value = pi.scope || "";
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
    const autoDispatchEl = document.getElementById("setting-pipeline-auto-dispatch");
    if (autoDispatchEl) autoDispatchEl.checked = pipe.auto_dispatch !== undefined ? pipe.auto_dispatch : true;

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

// ============================================================
// SYSTEM UPDATES & PATCH MANAGEMENT (NO GIT REQUIRED)
// ============================================================
let latestReleaseInfo = null;

function initUpdatesController() {
  document.getElementById("btn-check-updates")?.addEventListener("click", handleCheckUpdates);
  document.getElementById("btn-apply-update")?.addEventListener("click", handleApplyUpdate);
  document.getElementById("input-offline-patch")?.addEventListener("change", handleUploadOfflinePatch);
  document.getElementById("btn-restart-app-action")?.addEventListener("click", handleManualRestartPrompt);
  document.getElementById("btn-top-restart-server")?.addEventListener("click", handleManualRestartPrompt);

  fetchSystemVersion();
}

function handleManualRestartPrompt() {
  if (confirm("Restart the application server process now?\n\nThe server will cleanly reboot and the dashboard will reconnect automatically in a few seconds.")) {
    triggerServerRestart();
  }
}

async function fetchSystemVersion() {
  try {
    const res = await fetch("/api/system/version");
    if (!res.ok) return;
    const data = await res.json();
    const verBadge = document.getElementById("system-version-text");
    const headerBadge = document.getElementById("app-header-version");
    if (verBadge) verBadge.textContent = `v${data.version}`;
    if (headerBadge) headerBadge.textContent = `v${data.version}`;
  } catch (e) {
    console.warn("Could not fetch system version:", e);
  }
}

async function handleCheckUpdates() {
  const box = document.getElementById("update-status-box");
  const applyBtn = document.getElementById("btn-apply-update");
  const applyText = document.getElementById("btn-apply-update-text");
  if (!box) return;

  box.style.display = "block";
  box.textContent = "Checking GitHub Releases for new versions...";
  if (applyBtn) applyBtn.style.display = "none";

  try {
    const res = await fetch("/api/system/updates/check");
    const data = await res.json();
    latestReleaseInfo = data;

    if (data.update_available) {
      box.innerHTML = `<span style="color: var(--success); font-weight: 600;">✓ Update Available: v${escapeHtml(data.latest_version)}</span>\nRelease: ${escapeHtml(data.release_name)}\nPublished: ${formatTimestamp(data.published_at)}\nSize: ${data.asset_size_kb || '--'} KB\n\nRelease Notes:\n${escapeHtml(data.release_notes)}`;
      if (applyBtn) {
        applyBtn.style.display = "inline-flex";
        if (applyText) applyText.textContent = `Install Patch (v${data.latest_version})`;
      }
      showToast(`New version v${data.latest_version} available!`, "info");
    } else if (data.error) {
      box.innerHTML = `<span style="color: var(--danger); font-weight: 600;">✕ Update Check Notice</span>\n${escapeHtml(data.error)}`;
    } else {
      box.innerHTML = `<span style="color: var(--ink-primary); font-weight: 500;">✓ ${escapeHtml(data.message)}</span>\nInstalled Version: v${escapeHtml(data.current_version)}`;
    }
  } catch (e) {
    box.textContent = "Failed to connect to update service: " + e.message;
  }
}

async function handleApplyUpdate() {
  if (!confirm("Download and install patch for PIDataPipeline?\n\nYour existing configuration (config/) and data records (data/) will be strictly preserved, and an automatic rollback backup will be created.")) {
    return;
  }

  const box = document.getElementById("update-status-box");
  const applyBtn = document.getElementById("btn-apply-update");
  if (applyBtn) applyBtn.disabled = true;
  if (box) {
    box.style.display = "block";
    box.textContent = "Downloading patch and applying updates... Please wait.";
  }

  try {
    const res = await fetch("/api/system/updates/apply", { method: "POST" });
    const result = await res.json();

    if (res.ok && result.success) {
      box.innerHTML = `<span style="color: var(--success); font-weight: 600;">✓ ${escapeHtml(result.message)}</span>\n\nBackup created at:\n${escapeHtml(result.backup_path || '')}\n\n<div style="margin-top: 10px; display: flex; align-items: center; gap: 10px;"><button type="button" class="btn btn-primary btn-sm" onclick="triggerServerRestart()"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" style="width:14px;height:14px;"><polyline points="1 4 1 10 7 10"></polyline><polyline points="23 20 23 14 17 14"></polyline><path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15"></path></svg> Restart Server Now (1-Click)</button><span style="font-size: 11px; color: var(--ink-muted);">Or run stop.bat & start.bat manually</span></div>`;
      showToast("Patch installed successfully! Please restart server.", "success");
      fetchSystemVersion();
      if (applyBtn) applyBtn.style.display = "none";
    } else {
      box.innerHTML = `<span style="color: var(--danger); font-weight: 600;">✕ Failed to apply update</span>\n${escapeHtml(result.detail || result.error || 'Unknown error')}`;
      showToast("Failed to apply update", "danger");
    }
  } catch (e) {
    if (box) box.textContent = "Update error: " + e.message;
    showToast("Update error: " + e.message, "danger");
  } finally {
    if (applyBtn) applyBtn.disabled = false;
  }
}

async function handleUploadOfflinePatch(e) {
  const file = e.target.files?.[0];
  if (!file) return;

  if (!confirm(`Upload and apply offline patch "${file.name}"?\n\nYour existing configuration and data will be strictly preserved.`)) {
    e.target.value = "";
    return;
  }

  const box = document.getElementById("update-status-box");
  if (box) {
    box.style.display = "block";
    box.textContent = `Uploading and applying patch from ${file.name}... Please wait.`;
  }

  try {
    const arrayBuffer = await file.arrayBuffer();
    const res = await fetch("/api/system/updates/upload-patch", {
      method: "POST",
      headers: { "Content-Type": "application/octet-stream" },
      body: arrayBuffer
    });

    const result = await res.json();
    if (res.ok && result.success) {
      if (box) {
        box.innerHTML = `<span style="color: var(--success); font-weight: 600;">✓ ${escapeHtml(result.message)}</span>\nFiles updated: ${result.files_updated}\nBackup created at:\n${escapeHtml(result.backup_path || '')}\n\n<div style="margin-top: 10px; display: flex; align-items: center; gap: 10px;"><button type="button" class="btn btn-primary btn-sm" onclick="triggerServerRestart()"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" style="width:14px;height:14px;"><polyline points="1 4 1 10 7 10"></polyline><polyline points="23 20 23 14 17 14"></polyline><path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15"></path></svg> Restart Server Now (1-Click)</button><span style="font-size: 11px; color: var(--ink-muted);">Or run stop.bat & start.bat manually</span></div>`;
      }
      showToast("Offline patch installed successfully!", "success");
      fetchSystemVersion();
    } else {
      if (box) {
        box.innerHTML = `<span style="color: var(--danger); font-weight: 600;">✕ Patch installation failed</span>\n${escapeHtml(result.detail || result.error || 'Unknown error')}`;
      }
      showToast("Patch installation failed.", "danger");
    }
  } catch (err) {
    if (box) box.textContent = "Upload error: " + err.message;
    showToast("Upload error: " + err.message, "danger");
  } finally {
    e.target.value = "";
  }
}

async function triggerServerRestart() {
  const box = document.getElementById("update-status-box");
  if (box) {
    box.style.display = "block";
    box.innerHTML = `<span style="color: #f59e0b; font-weight: 600;">⟳ Restarting server...</span>\nServer is shutting down and relaunching with the updated code.\nReconnecting automatically in a few seconds...`;
    box.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
  showToast("Restarting server...", "info");

  try {
    await fetch("/api/system/restart", { method: "POST" });
  } catch (e) {
    // Network disconnect is expected when server process terminates
  }

  setTimeout(() => {
    let attempts = 0;
    const pollInterval = setInterval(async () => {
      attempts++;
      try {
        const res = await fetch("/api/system/version?t=" + Date.now());
        if (res.ok) {
          const data = await res.json();
          clearInterval(pollInterval);
          if (box) {
            box.innerHTML = `<span style="color: var(--success); font-weight: 600;">✓ Reconnected to server v${data.version}!</span>\nReloading dashboard...`;
          }
          showToast(`Server reconnected successfully (v${data.version})!`, "success");
          setTimeout(() => window.location.reload(), 800);
        }
      } catch (e) {
        if (attempts >= 25) {
          clearInterval(pollInterval);
          if (box) {
            box.innerHTML = `<span style="color: var(--danger); font-weight: 600;">Auto-reconnect timed out.</span>\nIf the server hasn't restarted yet, please run start.bat manually.`;
          }
        }
      }
    }, 1000);
  }, 2500);
}
window.triggerServerRestart = triggerServerRestart;

function handlePiAuthChange() {
  const type = document.getElementById("setting-pi-auth-type").value;
  const userGroup = document.getElementById("group-pi-username");
  const passGroup = document.getElementById("group-pi-password");
  const bearerGroup = document.getElementById("group-pi-bearer");
  const oauthFields = document.querySelectorAll(".pi-oauth-field");
  const userInput = document.getElementById("setting-pi-username");
  const userHelp = document.getElementById("help-pi-username");

  userGroup.style.display = (type === "basic" || type === "kerberos") ? "flex" : "none";
  passGroup.style.display = (type === "basic" || type === "kerberos") ? "flex" : "none";
  bearerGroup.style.display = (type === "bearer") ? "flex" : "none";
  oauthFields.forEach(el => el.style.display = (type === "oauth2") ? "flex" : "none");

  if (type === "kerberos") {
    if (userInput) userInput.placeholder = "Leave blank for Windows SSO, or DOMAIN\\username";
    if (userHelp) userHelp.innerHTML = "Leave blank for <strong>Windows Single Sign-On (SSO)</strong>, or specify <code>DOMAIN\\username</code>.";
  } else if (type === "basic") {
    if (userInput) userInput.placeholder = "DOMAIN\\username or username@domain.com";
    if (userHelp) userHelp.innerHTML = "For Basic Auth: specify <code>DOMAIN\\username</code> or <code>username@domain.com</code>.";
  }
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
      token_url: document.getElementById("setting-pi-token-url") ? document.getElementById("setting-pi-token-url").value.trim() : "",
      client_id: document.getElementById("setting-pi-client-id") ? document.getElementById("setting-pi-client-id").value.trim() : "",
      client_secret: document.getElementById("setting-pi-client-secret") ? document.getElementById("setting-pi-client-secret").value : "",
      scope: document.getElementById("setting-pi-scope") ? document.getElementById("setting-pi-scope").value.trim() : "",
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
      ingestion_mode: document.querySelector('input[name="setting-ingestion-mode"]:checked')?.value || "endpoint",
      auto_dispatch: document.getElementById("setting-pipeline-auto-dispatch") ? document.getElementById("setting-pipeline-auto-dispatch").checked : true,
      auto_start: currentSettings?.pipeline?.auto_start !== undefined ? currentSettings.pipeline.auto_start : true,
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
      let text = `<span style="color: var(--success); font-weight: bold;">✓ ${escapeHtml(result.message)}</span>\nLatency: ${result.latency_ms}ms\nHTTP Status: ${result.status_code}`;
      if (result.endpoint_tested) {
        text += `\nVerified Endpoint: ${escapeHtml(result.endpoint_tested)}`;
      }
      if (result.normalized_url && result.normalized_url !== cfg.url) {
        text += `\n\n[Auto-Detected URL]: Automatically updated base URL to: ${escapeHtml(result.normalized_url)}`;
        document.getElementById("setting-pi-url").value = result.normalized_url;
        showToast("PI Web API URL updated to " + result.normalized_url, "info");
      }
      if (result.recommended_auth && result.recommended_auth !== cfg.auth_type) {
        const recLabel = result.recommended_auth === "kerberos" ? "Windows Integrated (Kerberos / NTLM / SSO)" : result.recommended_auth;
        text += `\n\n[Auto-Detected Auth]: Server accepted '${escapeHtml(recLabel)}'. Updated authentication dropdown. Remember to click 'Save Settings'.`;
        document.getElementById("setting-pi-auth-type").value = result.recommended_auth;
        handlePiAuthChange();
        showToast("PI Auth Method updated to " + recLabel, "info");
      }
      if (result.details) {
        text += `\n\nResponse:\n${JSON.stringify(result.details, null, 2)}`;
      }
      box.innerHTML = text;
    } else {
      box.className = "error-console danger";
      let text = `<span style="color: var(--danger); font-weight: bold;">✕ Connection Test Failed</span>\nMessage: ${escapeHtml(result.message)}`;
      if (result.status_code) {
        text += `\nHTTP Status: ${result.status_code}`;
      }
      if (result.endpoint_tested) {
        text += `\nTested Endpoint: ${escapeHtml(result.endpoint_tested)}`;
      }
      text += `\n\n${escapeHtml(result.error || '')}`;

      if (result.recommended_auth) {
        let recLabel = "Basic Authentication";
        if (result.recommended_auth === "kerberos") recLabel = "Windows Integrated (Kerberos / NTLM)";
        else if (result.recommended_auth === "bearer") recLabel = "Bearer Token";
        else if (result.recommended_auth === "oauth2") recLabel = "OAuth 2.0 (Client Credentials)";
        text += `\n\n<button type="button" id="btn-switch-recommended-auth" class="btn btn-primary btn-sm" style="margin-top: 8px;">Switch to ${escapeHtml(recLabel)}</button>`;
      }

      box.innerHTML = text;

      if (result.recommended_auth) {
        document.getElementById("btn-switch-recommended-auth")?.addEventListener("click", async () => {
          document.getElementById("setting-pi-auth-type").value = result.recommended_auth;
          handlePiAuthChange();
          if (result.recommended_auth === "bearer") {
            document.getElementById("setting-pi-bearer")?.focus();
            showToast("Switched to Bearer Token mode. Paste your Bearer token and click Save/Test.", "info");
          } else if (result.recommended_auth === "oauth2") {
            document.getElementById("setting-pi-token-url")?.focus();
            showToast("Switched to OAuth 2.0 mode. Enter your Token URL, Client ID, and Secret.", "info");
          } else {
            await handleSaveSettings();
            handleTestPiSettings();
          }
        });
      }
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

// ------------------------------------------------------------
// Storage Files Cleanup & Production Pre-Flight Handlers
// ------------------------------------------------------------
async function handlePurgeDeliveriesQuick(filter) {
  const isPendingOnly = filter === "PENDING";
  const promptMsg = isPendingOnly
    ? "Are you sure you want to purge all pending/failed test deliveries from data/received_deliveries.json?\n\nThis guarantees un-dispatched test readings are never forwarded to live Oracle ERP Cloud."
    : "Are you sure you want to purge ALL records from data/received_deliveries.json?\n\nThis will completely reset the staging queue.";

  if (!confirm(promptMsg)) return;

  showToast("Purging staged deliveries...", "info");
  try {
    const res = await fetch(`/api/deliveries?filter=${filter}`, { method: "DELETE" });
    const data = await res.json();
    if (res.ok && data.success) {
      showToast(`Purged ${data.deleted_count} deliveries from data/received_deliveries.json.`, "success");
      await loadDashboardData();
    } else {
      showToast("Purge failed: " + (data.detail || data.message || "Unknown error"), "danger");
    }
  } catch (err) {
    showToast("Error purging deliveries: " + err.message, "danger");
  }
}

async function handlePurgeStorageTarget(target, label) {
  if (!confirm(`Are you sure you want to clear ${label} (data/${target}.json)?\n\nThis operational data will be permanently cleared. Settings and mappings are preserved.`)) {
    return;
  }

  showToast(`Clearing ${label}...`, "info");
  try {
    const res = await fetch("/api/storage/clear", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target: target })
    });
    const data = await res.json();
    if (res.ok && data.success) {
      showToast(`${label} cleared (${data.deleted_count} records removed).`, "success");
      await loadDashboardData();
    } else {
      showToast("Clear failed: " + (data.detail || data.message || "Unknown error"), "danger");
    }
  } catch (err) {
    showToast("Error clearing storage: " + err.message, "danger");
  }
}

async function handlePreflightPurgeAll() {
  const confirmMsg = "⚠️ PRODUCTION PRE-FLIGHT PURGE CONFIRMATION\n\n" +
    "Are you sure you want to purge all operational test data?\n\n" +
    "This will wipe:\n" +
    "• Staged PI Deliveries (data/received_deliveries.json)\n" +
    "• PI Web API Pull History (data/pull_history.json)\n" +
    "• Oracle ERP Publish History (data/publish_history.json)\n\n" +
    "✓ Your connection settings (config/settings.json) and attribute mappings (config/mappings.json) will be safely PRESERVED.\n\n" +
    "Click OK to proceed with the Pre-Flight Purge.";

  if (!confirm(confirmMsg)) return;

  showToast("Executing Production Pre-Flight Purge...", "info");
  try {
    const res = await fetch("/api/storage/clear", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target: "all" })
    });
    const data = await res.json();
    if (res.ok && data.success) {
      const r = data.results || {};
      showToast(`Pre-flight purge complete! Purged: ${r.deliveries_deleted ?? 0} deliveries, ${r.pulls_deleted ?? 0} pulls, ${r.publishes_deleted ?? 0} publishes.`, "success");
      await loadDashboardData();
    } else {
      showToast("Pre-flight purge failed: " + (data.detail || data.message || "Unknown error"), "danger");
    }
  } catch (err) {
    showToast("Error during pre-flight purge: " + err.message, "danger");
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
