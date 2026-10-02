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
  initHistory();
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
  } else if (tabName === "history") {
    loadHistoryDeliveries();
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

function initHistory() {
  document.getElementById("btn-simulate-history")?.addEventListener("click", async () => {
    await triggerSimulateDelivery();
    if (document.getElementById("view-history")?.classList.contains("active")) {
      await loadHistoryDeliveries(true);
    }
  });
  document.getElementById("btn-purge-history")?.addEventListener("click", openPurgeDeliveriesModal);
  document.getElementById("btn-refresh-history")?.addEventListener("click", () => loadHistoryDeliveries(false));

  // Search input & clear button
  const searchInput = document.getElementById("history-search-input");
  const clearSearchBtn = document.getElementById("btn-clear-history-search");
  searchInput?.addEventListener("input", () => {
    historySearchQuery = searchInput.value.trim();
    if (clearSearchBtn) clearSearchBtn.style.display = searchInput.value ? "block" : "none";
    historyCurrentPage = 1;
    applyHistoryFilterAndRender();
  });
  clearSearchBtn?.addEventListener("click", () => {
    if (searchInput) searchInput.value = "";
    historySearchQuery = "";
    if (clearSearchBtn) clearSearchBtn.style.display = "none";
    historyCurrentPage = 1;
    applyHistoryFilterAndRender();
    searchInput?.focus();
  });

  // Endpoint filter (Oracle / J5)
  document.getElementById("history-filter-endpoint")?.addEventListener("change", (e) => {
    historyEndpointFilter = e.target.value;
    historyCurrentPage = 1;
    applyHistoryFilterAndRender();
  });

  // Attribute filter
  document.getElementById("history-filter-attribute")?.addEventListener("change", (e) => {
    historyAttributeFilter = e.target.value;
    historyCurrentPage = 1;
    applyHistoryFilterAndRender();
  });

  // Value filter
  document.getElementById("history-filter-value")?.addEventListener("input", (e) => {
    historyValueFilter = e.target.value.trim();
    historyCurrentPage = 1;
    applyHistoryFilterAndRender();
  });

  // Status filter
  document.getElementById("history-filter-status")?.addEventListener("change", (e) => {
    historyStatusFilter = e.target.value;
    historyCurrentPage = 1;
    applyHistoryFilterAndRender();
  });

  // Reset filters
  document.getElementById("btn-reset-history-filters")?.addEventListener("click", resetHistoryFilters);

  // Pagination controls
  document.getElementById("history-btn-prev")?.addEventListener("click", () => changeHistoryPage(historyCurrentPage - 1));
  document.getElementById("history-btn-next")?.addEventListener("click", () => changeHistoryPage(historyCurrentPage + 1));
}

async function loadDashboardData() {
  try {
    const res = await fetch("/api/dashboard");
    if (!res.ok) return;
    const data = await res.json();
    renderDashboard(data);
    if (document.getElementById("view-history")?.classList.contains("active")) {
      loadHistoryDeliveries(false);
    }
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
    const authType = currentSettings.oracle_erp.auth_type;
    const authDisplay = (authType === "none" || authType === "no_auth" || authType === "open") ? "ORDS Direct (No Auth)" : (authType || "OAuth 2.0").toUpperCase();
    if (erpAuth) erpAuth.textContent = authDisplay;
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

function getDeliveryEndpoints(deliv) {
  if (!deliv) return ["ORACLE"];
  const eps = new Set();

  // 1. Direct target_types from oracle_dispatch
  if (deliv.oracle_dispatch?.target_types && Array.isArray(deliv.oracle_dispatch.target_types)) {
    for (const t of deliv.oracle_dispatch.target_types) {
      const u = String(t).toUpperCase();
      if (u.includes("J5")) eps.add("J5");
      if (u.includes("ORACLE")) eps.add("ORACLE");
    }
  }

  // 2. Dispatches array
  if (deliv.oracle_dispatch?.dispatches && Array.isArray(deliv.oracle_dispatch.dispatches)) {
    for (const d of deliv.oracle_dispatch.dispatches) {
      const tt = String(d.target_type || "").toUpperCase();
      const ep = String(d.target_endpoint || "").toLowerCase();
      if (tt === "J5" || ep.includes("hxgnsmartcloud") || ep.includes("purchaseorder")) eps.add("J5");
      if (tt === "ORACLE" || ep.includes("oracle") || ep.includes("/ords/")) eps.add("ORACLE");
    }
  }

  // 3. Fallback to target_endpoint URL
  const epUrl = String(deliv.oracle_dispatch?.target_endpoint || deliv.oracle_dispatch?.endpoint_url || "").toLowerCase();
  if (epUrl.includes("hxgnsmartcloud") || epUrl.includes("purchaseorder")) eps.add("J5");
  if (epUrl.includes("oracle") || epUrl.includes("/ords/")) eps.add("ORACLE");

  // 4. Attributes / Mappings
  if (Array.isArray(deliv.attributes_summary)) {
    for (const a of deliv.attributes_summary) {
      const aUrl = String(a.target_endpoint_url || "").toLowerCase();
      if (aUrl.includes("hxgnsmartcloud") || aUrl.includes("purchaseorder")) eps.add("J5");
      if (aUrl.includes("oracle") || aUrl.includes("/ords/")) eps.add("ORACLE");

      if (Array.isArray(currentMappings) && currentMappings.length > 0) {
        const m = currentMappings.find(cm =>
          (cm.attribute_name && a.name && cm.attribute_name.toLowerCase() === a.name.toLowerCase()) ||
          (cm.tag && a.tag && cm.tag.toLowerCase() === a.tag.toLowerCase())
        );
        if (m) {
          const mType = String(m.target_type || "").toUpperCase();
          const mUrl = String(m.target_endpoint_url || "").toLowerCase();
          if (mType === "J5" || mUrl.includes("hxgnsmartcloud") || mUrl.includes("purchaseorder")) eps.add("J5");
          else eps.add("ORACLE");
        }
      }
    }
  }

  if (eps.size === 0) {
    eps.add("ORACLE");
  }

  return Array.from(eps);
}

function renderDeliveryRowHtml(deliv) {
  // 1. Received At
  const timeFormatted = formatTimestamp(deliv.received_at);
  const clientIp = deliv.client_ip || "Unknown";
  const shortId = deliv.delivery_id || "";

  // 2. Notification / Target
  const notifName = escapeHtml(deliv.notification_name || "PI Notification");
  const eventType = escapeHtml(deliv.event_type || "Update");
  const targetPath = escapeHtml(deliv.target_path || "--");
  const eps = getDeliveryEndpoints(deliv);
  const endpointBadges = eps.map(ep => {
    if (ep === "J5") {
      return `<span class="badge" style="font-size: 10px; padding: 1px 6px; background: rgba(99, 102, 241, 0.12); color: #4f46e5; border: 1px solid rgba(99, 102, 241, 0.3);"><span class="badge-dot" style="background:#6366f1;"></span> J5</span>`;
    } else {
      return `<span class="badge badge-info" style="font-size: 10px; padding: 1px 6px;"><span class="badge-dot"></span> Oracle</span>`;
    }
  }).join(" ");

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
    const targets = deliv.oracle_dispatch?.target_types || [];
    const targetLabel = targets.length > 0 ? targets.join(" & ") : "Endpoint";
    statusBadge = `<span class="badge badge-success" title="Successfully dispatched to ${escapeHtml(targetLabel)}"><span class="badge-dot"></span> Dispatched (${escapeHtml(targetLabel)})</span>`;
  } else if (deliv.oracle_status === "FAILED") {
    const retryCount = deliv.retry_count || 0;
    const retryLabel = retryCount > 0 ? `Failed (Retry #${retryCount})` : `Failed (Retry Queued)`;
    const errMsg = escapeHtml(deliv.oracle_dispatch?.message || deliv.oracle_dispatch?.error || "Dispatch failed. Will retry on next scheduled interval.");
    statusBadge = `<span class="badge badge-danger" title="${errMsg}"><span class="badge-dot"></span> ${retryLabel}</span>`;
  } else if (deliv.oracle_status === "PENDING_SETUP") {
    statusBadge = `<span class="badge badge-pending" title="Endpoint credentials pending setup in Settings"><span class="badge-dot"></span> Pending Setup</span>`;
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
        <div style="display: flex; align-items: center; gap: 6px; flex-wrap: wrap;">
          <strong style="font-size: 12px; color: var(--ink-primary);">${notifName}</strong>
          <span class="badge badge-info" style="font-size: 10px; padding: 1px 5px;">${eventType}</span>
          ${endpointBadges}
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
          <div style="display: flex; gap: 4px; flex-wrap: wrap; justify-content: flex-end;">
            ${deliv.oracle_dispatch ? `
              <button type="button" class="btn btn-primary btn-sm" onclick="showOracleResponseModal('${escapeHtml(deliv.delivery_id)}')" title="View exact response returned from destination endpoint (Oracle / J5)" style="font-size: 11px; padding: 3px 8px; display: inline-flex; align-items: center; gap: 4px;">
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"></path><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"></path></svg>
                Endpoint Response
              </button>
            ` : ''}
            <button type="button" class="btn btn-secondary btn-sm" onclick="inspectDelivery('${escapeHtml(deliv.delivery_id)}')">
              Inspect
            </button>
            <button type="button" class="btn btn-danger btn-sm" onclick="deleteDeliveryRecord('${escapeHtml(deliv.delivery_id)}')" title="Delete this delivery from data/received_deliveries.json">
              Delete
            </button>
          </div>
          ${deliv.oracle_status !== "DISPATCHED" ? `
            <button type="button" class="btn btn-outline btn-sm" onclick="dispatchSingleDelivery('${escapeHtml(deliv.delivery_id)}')">
              Send to Endpoint
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
}

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

  tbody.innerHTML = deliveries.map(deliv => renderDeliveryRowHtml(deliv)).join("");
}

// ============================================================
// HISTORICAL DATA TABLE WITH PAGINATION (10 rows per page)
// & MULTI-CRITERIA FILTERING (Search, Endpoint, Attribute, Value, Status)
// ============================================================
let historyAllDeliveries = [];
let historyFilteredDeliveries = [];
let historyCurrentPage = 1;
const HISTORY_PAGE_SIZE = 10;
let historyStatusFilter = "ALL";
let historyEndpointFilter = "ALL";
let historyAttributeFilter = "ALL";
let historyValueFilter = "";
let historySearchQuery = "";

async function loadHistoryDeliveries(resetPage = false) {
  const tbody = document.getElementById("history-deliveries-tbody");
  if (!tbody) return;

  if (resetPage) {
    historyCurrentPage = 1;
  }

  // Ensure attribute mappings are loaded for accurate endpoint resolution
  if (!currentMappings || currentMappings.length === 0) {
    try {
      const mapRes = await fetch("/api/mappings");
      if (mapRes.ok) {
        currentMappings = await mapRes.json();
      }
    } catch (e) {}
  }

  try {
    const res = await fetch("/api/deliveries?limit=0");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    historyAllDeliveries = Array.isArray(data) ? data : [];
    populateHistoryAttributeOptions();
    applyHistoryFilterAndRender();
  } catch (err) {
    tbody.innerHTML = `
      <tr>
        <td colspan="5" style="text-align: center; color: var(--danger); padding: 24px;">
          Failed to load historical deliveries: ${escapeHtml(err.message)}
        </td>
      </tr>
    `;
  }
}

function populateHistoryAttributeOptions() {
  const select = document.getElementById("history-filter-attribute");
  if (!select) return;
  const currentVal = select.value || "ALL";

  const attrSet = new Set();
  for (const deliv of historyAllDeliveries) {
    if (Array.isArray(deliv.attributes_summary)) {
      for (const a of deliv.attributes_summary) {
        if (a.name && typeof a.name === "string") attrSet.add(a.name.trim());
        else if (a.tag && typeof a.tag === "string") attrSet.add(a.tag.trim());
      }
    }
  }

  const sorted = Array.from(attrSet).filter(Boolean).sort((a, b) => a.localeCompare(b));
  select.innerHTML = `<option value="ALL">All Attributes (${sorted.length})</option>` +
    sorted.map(name => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`).join("");

  if (sorted.includes(currentVal)) {
    select.value = currentVal;
    historyAttributeFilter = currentVal;
  } else {
    select.value = "ALL";
    historyAttributeFilter = "ALL";
  }
}

function matchValue(actualVal, filterVal) {
  if (filterVal === undefined || filterVal === null || filterVal.trim() === "") return true;
  if (actualVal === undefined || actualVal === null) return false;

  const filterStr = filterVal.trim();
  const actualStr = String(actualVal).trim();

  // Numeric comparison operator: >, >=, <, <=, =, ==
  const compMatch = filterStr.match(/^([><]=?|==?)\s*(-?\d+(?:\.\d+)?)$/);
  if (compMatch) {
    const op = compMatch[1];
    const targetNum = parseFloat(compMatch[2]);
    const actualNum = parseFloat(actualStr);
    if (!isNaN(actualNum) && !isNaN(targetNum)) {
      if (op === ">") return actualNum > targetNum;
      if (op === ">=") return actualNum >= targetNum;
      if (op === "<") return actualNum < targetNum;
      if (op === "<=") return actualNum <= targetNum;
      if (op === "=" || op === "==") return Math.abs(actualNum - targetNum) < 1e-6;
    }
  }

  return actualStr.toLowerCase().includes(filterStr.toLowerCase());
}

function matchAttributeValue(attr, filterVal) {
  if (!attr) return false;
  if (matchValue(attr.value, filterVal)) return true;
  if (attr.limit !== undefined && attr.limit !== null && matchValue(attr.limit, filterVal)) return true;
  if (attr.results !== undefined && attr.results !== null && matchValue(attr.results, filterVal)) return true;
  if (attr.uom !== undefined && attr.uom !== null && matchValue(attr.uom, filterVal)) return true;
  return false;
}

function getDeliverySearchText(deliv) {
  const parts = [];

  // Column 1: Received At & Metadata
  parts.push(deliv.delivery_id || "");
  parts.push(deliv.client_ip || "");
  parts.push(deliv.received_at || "");
  parts.push(formatTimestamp(deliv.received_at));

  // Column 2: Notification & Target Path
  parts.push(deliv.notification_name || "");
  parts.push(deliv.event_type || "");
  parts.push(deliv.target_path || "");

  // Column 4 & Endpoints: Status & Destination Endpoints
  parts.push(deliv.oracle_status || "");
  const eps = getDeliveryEndpoints(deliv);
  parts.push(...eps);
  if (eps.includes("ORACLE")) parts.push("oracle ords erp");
  if (eps.includes("J5")) parts.push("j5 hexagon smart cloud purchaseorder");

  if (deliv.oracle_dispatch) {
    parts.push(deliv.oracle_dispatch.target_endpoint || "");
    parts.push(deliv.oracle_dispatch.endpoint_url || "");
    parts.push(deliv.oracle_dispatch.message || "");
    parts.push(deliv.oracle_dispatch.error || "");
    if (Array.isArray(deliv.oracle_dispatch.target_types)) {
      parts.push(...deliv.oracle_dispatch.target_types);
    }
  }

  // Column 3: Attributes & Values
  if (Array.isArray(deliv.attributes_summary)) {
    for (const a of deliv.attributes_summary) {
      parts.push(a.name || "");
      parts.push(a.tag || "");
      parts.push(a.description || "");
      parts.push(String(a.value ?? ""));
      parts.push(a.uom || "");
      parts.push(String(a.limit ?? ""));
      parts.push(String(a.results ?? ""));
      parts.push(a.quality || "");
      if (a.target_endpoint_url) parts.push(a.target_endpoint_url);
    }
  }

  if (deliv.raw_payload && typeof deliv.raw_payload === "object") {
    try {
      parts.push(JSON.stringify(deliv.raw_payload));
    } catch (e) {}
  }

  return parts.join(" ").toLowerCase();
}

function updateHistoryFilterBadge() {
  const badgeEl = document.getElementById("history-filter-badge");
  if (!badgeEl) return;

  const isFiltering = (
    historyStatusFilter !== "ALL" ||
    historyEndpointFilter !== "ALL" ||
    historyAttributeFilter !== "ALL" ||
    Boolean(historyValueFilter) ||
    Boolean(historySearchQuery)
  );

  if (isFiltering) {
    badgeEl.innerHTML = `
      <span class="badge" style="font-size: 11px; padding: 2px 8px; background: rgba(59, 130, 246, 0.12); color: var(--primary); border: 1px solid rgba(59, 130, 246, 0.3);">
        <span class="badge-dot"></span> Filtered: ${historyFilteredDeliveries.length} of ${historyAllDeliveries.length}
      </span>
    `;
  } else {
    badgeEl.innerHTML = `<span style="color: var(--ink-tertiary); font-size: 11px;">Total: ${historyAllDeliveries.length} deliveries</span>`;
  }
}

function resetHistoryFilters() {
  historySearchQuery = "";
  historyEndpointFilter = "ALL";
  historyAttributeFilter = "ALL";
  historyValueFilter = "";
  historyStatusFilter = "ALL";

  const searchInput = document.getElementById("history-search-input");
  if (searchInput) searchInput.value = "";
  const clearBtn = document.getElementById("btn-clear-history-search");
  if (clearBtn) clearBtn.style.display = "none";

  const endpointSelect = document.getElementById("history-filter-endpoint");
  if (endpointSelect) endpointSelect.value = "ALL";

  const attrSelect = document.getElementById("history-filter-attribute");
  if (attrSelect) attrSelect.value = "ALL";

  const valInput = document.getElementById("history-filter-value");
  if (valInput) valInput.value = "";

  const statusSelect = document.getElementById("history-filter-status");
  if (statusSelect) statusSelect.value = "ALL";

  historyCurrentPage = 1;
  applyHistoryFilterAndRender();
}
window.resetHistoryFilters = resetHistoryFilters;

function applyHistoryFilterAndRender() {
  const statusSelect = document.getElementById("history-filter-status");
  historyStatusFilter = statusSelect ? statusSelect.value : "ALL";

  const endpointSelect = document.getElementById("history-filter-endpoint");
  historyEndpointFilter = endpointSelect ? endpointSelect.value : "ALL";

  const attrSelect = document.getElementById("history-filter-attribute");
  historyAttributeFilter = attrSelect ? attrSelect.value : "ALL";

  const valInput = document.getElementById("history-filter-value");
  historyValueFilter = valInput ? valInput.value.trim() : "";

  const searchInput = document.getElementById("history-search-input");
  historySearchQuery = searchInput ? searchInput.value.trim() : "";

  const clearBtn = document.getElementById("btn-clear-history-search");
  if (clearBtn) clearBtn.style.display = historySearchQuery ? "block" : "none";

  const searchTerms = historySearchQuery ? historySearchQuery.toLowerCase().split(/\s+/).filter(Boolean) : [];

  historyFilteredDeliveries = historyAllDeliveries.filter(deliv => {
    // 1. Status Filter
    if (historyStatusFilter !== "ALL") {
      const delivStatus = (deliv.oracle_status || "").toUpperCase();
      if (delivStatus !== historyStatusFilter.toUpperCase()) {
        return false;
      }
    }

    // 2. Endpoint Filter (Oracle / J5)
    if (historyEndpointFilter !== "ALL") {
      const endpoints = getDeliveryEndpoints(deliv);
      if (!endpoints.includes(historyEndpointFilter.toUpperCase())) {
        return false;
      }
    }

    // 3. Attribute & Value Filter
    const attrs = deliv.attributes_summary || [];
    if (historyAttributeFilter !== "ALL") {
      const targetAttr = historyAttributeFilter.trim().toLowerCase();
      const matchingAttrs = attrs.filter(a => {
        const aName = (a.name || "").trim().toLowerCase();
        const aTag = (a.tag || "").trim().toLowerCase();
        return aName === targetAttr || aTag === targetAttr;
      });

      if (matchingAttrs.length === 0) {
        return false;
      }

      if (historyValueFilter) {
        const valueMatches = matchingAttrs.some(a => matchAttributeValue(a, historyValueFilter));
        if (!valueMatches) return false;
      }
    } else if (historyValueFilter) {
      let anyMatch = false;
      if (attrs.length > 0) {
        anyMatch = attrs.some(a => matchAttributeValue(a, historyValueFilter));
      } else if (deliv.raw_payload) {
        anyMatch = matchValue(JSON.stringify(deliv.raw_payload), historyValueFilter);
      }
      if (!anyMatch) return false;
    }

    // 4. Cross-column Search
    if (searchTerms.length > 0) {
      const textBlob = getDeliverySearchText(deliv);
      const matchesAll = searchTerms.every(term => textBlob.includes(term));
      if (!matchesAll) return false;
    }

    return true;
  });

  updateHistoryFilterBadge();

  const totalPages = Math.ceil(historyFilteredDeliveries.length / HISTORY_PAGE_SIZE) || 1;
  if (historyCurrentPage > totalPages) {
    historyCurrentPage = totalPages;
  }
  if (historyCurrentPage < 1) {
    historyCurrentPage = 1;
  }

  renderHistoryTable();
  renderHistoryPagination();
}

function renderHistoryTable() {
  const tbody = document.getElementById("history-deliveries-tbody");
  if (!tbody) return;

  if (historyFilteredDeliveries.length === 0) {
    const isFiltering = (
      historyStatusFilter !== "ALL" ||
      historyEndpointFilter !== "ALL" ||
      historyAttributeFilter !== "ALL" ||
      Boolean(historyValueFilter) ||
      Boolean(historySearchQuery)
    );

    tbody.innerHTML = `
      <tr>
        <td colspan="5" style="text-align: center; color: var(--ink-secondary); padding: 2.5rem 1rem;">
          <div style="font-weight: 500; font-size: 13px; color: var(--ink-primary); margin-bottom: 6px;">
            ${isFiltering ? "No delivery records match the current filters" : "No historical delivery records found"}
          </div>
          <div style="font-size: 12px; color: var(--ink-secondary); margin-bottom: 14px;">
            ${isFiltering 
              ? "Try adjusting or clearing your search query, endpoint, attribute, or status filter." 
              : "No deliveries have been received at <code>/api/v1/delivery</code> yet."}
          </div>
          <div style="display: flex; gap: 8px; justify-content: center; align-items: center;">
            ${isFiltering ? `
              <button type="button" class="btn btn-secondary btn-sm" onclick="resetHistoryFilters()">
                Reset All Filters
              </button>
            ` : ""}
            <button type="button" class="btn btn-primary btn-sm" onclick="triggerSimulateDelivery()">
              + Simulate Sample Push
            </button>
          </div>
        </td>
      </tr>
    `;
    return;
  }

  const startIndex = (historyCurrentPage - 1) * HISTORY_PAGE_SIZE;
  const endIndex = Math.min(startIndex + HISTORY_PAGE_SIZE, historyFilteredDeliveries.length);
  const pageSlice = historyFilteredDeliveries.slice(startIndex, endIndex);

  tbody.innerHTML = pageSlice.map(deliv => renderDeliveryRowHtml(deliv)).join("");
}

function renderHistoryPagination() {
  const infoEl = document.getElementById("history-pagination-info");
  const prevBtn = document.getElementById("history-btn-prev");
  const nextBtn = document.getElementById("history-btn-next");
  const pageNumsEl = document.getElementById("history-page-numbers");

  const totalRecords = historyFilteredDeliveries.length;
  const totalPages = Math.ceil(totalRecords / HISTORY_PAGE_SIZE) || 1;

  if (infoEl) {
    if (totalRecords === 0) {
      infoEl.innerHTML = "No deliveries found";
    } else {
      const start = (historyCurrentPage - 1) * HISTORY_PAGE_SIZE + 1;
      const end = Math.min(historyCurrentPage * HISTORY_PAGE_SIZE, totalRecords);
      infoEl.innerHTML = `Showing <strong>${start}</strong> to <strong>${end}</strong> of <strong>${totalRecords}</strong> deliveries (Page ${historyCurrentPage} of ${totalPages})`;
    }
  }

  if (prevBtn) {
    prevBtn.disabled = (historyCurrentPage <= 1);
  }
  if (nextBtn) {
    nextBtn.disabled = (historyCurrentPage >= totalPages);
  }

  if (pageNumsEl) {
    let pagesToDisplay = [];
    if (totalPages <= 7) {
      for (let i = 1; i <= totalPages; i++) pagesToDisplay.push(i);
    } else {
      pagesToDisplay.push(1);
      let left = Math.max(2, historyCurrentPage - 1);
      let right = Math.min(totalPages - 1, historyCurrentPage + 1);
      if (left > 2) pagesToDisplay.push("...");
      for (let i = left; i <= right; i++) pagesToDisplay.push(i);
      if (right < totalPages - 1) pagesToDisplay.push("...");
      pagesToDisplay.push(totalPages);
    }

    pageNumsEl.innerHTML = pagesToDisplay.map(p => {
      if (p === "...") {
        return `<span style="padding: 4px 6px; color: var(--ink-tertiary); font-size: 12px;">...</span>`;
      }
      const isActive = (p === historyCurrentPage);
      const btnClass = isActive ? "btn btn-primary btn-sm" : "btn btn-secondary btn-sm";
      return `<button type="button" class="${btnClass}" onclick="changeHistoryPage(${p})" style="min-width: 30px; padding: 4px 8px; font-size: 12px; font-weight: ${isActive ? '600' : '400'};">${p}</button>`;
    }).join("");
  }
}

function changeHistoryPage(newPage) {
  const totalPages = Math.ceil(historyFilteredDeliveries.length / HISTORY_PAGE_SIZE) || 1;
  if (newPage < 1) newPage = 1;
  if (newPage > totalPages) newPage = totalPages;
  historyCurrentPage = newPage;
  renderHistoryTable();
  renderHistoryPagination();
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
    const oracleBtn = document.getElementById("btn-modal-view-oracle");

    if (titleEl) titleEl.textContent = `PI Delivery: ${data.notification_name || "Notification"}`;
    if (subEl) subEl.textContent = `ID: ${data.delivery_id} · Received: ${formatTimestamp(data.received_at)} from ${data.client_ip || "Unknown"}`;
    if (jsonEl) jsonEl.textContent = JSON.stringify(data.raw_payload || data, null, 2);
    if (metaEl) {
      metaEl.innerHTML = `Status: <strong>${data.oracle_status}</strong> · Attributes: <strong>${data.attribute_count || 0}</strong>`;
    }
    if (dispatchBtn) {
      dispatchBtn.style.display = data.oracle_status === "DISPATCHED" ? "none" : "inline-block";
    }
    if (oracleBtn) {
      if (data.oracle_dispatch) {
        oracleBtn.style.display = "inline-block";
        oracleBtn.onclick = () => {
          closeDeliveryModal();
          showOracleResponseModal(data.delivery_id);
        };
      } else {
        oracleBtn.style.display = "none";
      }
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
// Oracle ORDS Response Inspection Modal
// ------------------------------------------------------------
let currentOracleModalDelivery = null;

async function showOracleResponseModal(deliveryId) {
  try {
    const res = await fetch(`/api/deliveries/${deliveryId}`);
    if (!res.ok) {
      showToast("Failed to load delivery record", "danger");
      return;
    }
    const data = await res.json();
    currentOracleModalDelivery = data;

    const modal = document.getElementById("modal-oracle-response");
    const titleEl = document.getElementById("modal-oracle-title");
    const subEl = document.getElementById("modal-oracle-subtitle");
    const bannerEl = document.getElementById("modal-oracle-status-banner");
    const containerEl = document.getElementById("modal-oracle-tables-container");
    const rawJsonEl = document.getElementById("modal-oracle-raw-json");
    const metaEl = document.getElementById("modal-oracle-meta");
    const sendAgainBtn = document.getElementById("btn-oracle-modal-send-again");

    if (titleEl) {
      titleEl.textContent = `Endpoint Response: ${data.notification_name || "PI Delivery"}`;
    }
    if (subEl) {
      subEl.textContent = `Delivery ID: #${(data.delivery_id || "").slice(-10)} · Received: ${formatTimestamp(data.received_at)} · Client: ${data.client_ip || "Unknown"}`;
    }

    const disp = data.oracle_dispatch || {};
    const dispatches = disp.dispatches || [];
    const isSuccess = (data.oracle_status === "DISPATCHED" || disp.status === "DISPATCHED" || disp.status === "SUCCESS");
    const httpCode = disp.http_code || (dispatches[0]?.http_code) || "--";
    const targetEndpoint = disp.target_endpoint || dispatches[0]?.target_endpoint || "--";

    // 1. Status Banner
    if (bannerEl) {
      const bannerBg = isSuccess ? "rgba(16, 185, 129, 0.08)" : "rgba(239, 68, 68, 0.08)";
      const bannerBorder = isSuccess ? "rgba(16, 185, 129, 0.3)" : "rgba(239, 68, 68, 0.3)";
      const badgeClass = isSuccess ? "badge-success" : (disp.status === "PENDING_SETUP" ? "badge-pending" : "badge-danger");
      const badgeText = isSuccess ? `HTTP ${httpCode} Dispatched` : (disp.status === "PENDING_SETUP" ? "Pending Setup" : `HTTP ${httpCode} Failed`);

      bannerEl.style.background = bannerBg;
      bannerEl.style.borderColor = bannerBorder;
      bannerEl.style.borderRadius = "var(--radius)";
      bannerEl.style.padding = "10px 14px";
      bannerEl.style.border = "1px solid " + bannerBorder;
      bannerEl.style.display = "flex";
      bannerEl.style.justifyContent = "space-between";
      bannerEl.style.alignItems = "center";
      bannerEl.style.flexWrap = "wrap";
      bannerEl.style.gap = "8px";

      bannerEl.innerHTML = `
        <div style="display: flex; align-items: center; gap: 8px;">
          <span class="badge ${badgeClass}" style="font-size: 11px; padding: 3px 8px;">
            <span class="badge-dot"></span> ${badgeText}
          </span>
          <span style="font-size: 12px; color: var(--ink-primary); font-weight: 500;">
            ${escapeHtml(disp.message || "No dispatch message")}
          </span>
        </div>
        <div style="font-size: 11px; color: var(--ink-secondary); font-family: var(--font-mono);">
          Dispatched: ${disp.dispatched_at ? formatTimestamp(disp.dispatched_at) : "--"}
        </div>
      `;
    }

    // 2. Response / Comparison Table(s)
    let itemsToRender = [];
    if (dispatches.length > 0) {
      itemsToRender = dispatches;
    } else if (disp.erp_response) {
      itemsToRender = [{
        attribute_name: data.attributes_summary?.[0]?.name || data.notification_name || "Attribute",
        target_endpoint: targetEndpoint,
        status: isSuccess ? "SUCCESS" : "FAILED",
        http_code: httpCode,
        payload: disp.payload || (data.attributes_summary?.[0] ? {
          tag: data.attributes_summary[0].tag || data.attributes_summary[0].name,
          description: data.attributes_summary[0].description,
          value: data.attributes_summary[0].value,
          limit: data.attributes_summary[0].limit,
          results: data.attributes_summary[0].results,
          uom: data.attributes_summary[0].uom,
          timestamp: data.attributes_summary[0].timestamp
        } : {}),
        response: disp.erp_response
      }];
    }

    if (containerEl) {
      if (itemsToRender.length === 0) {
        containerEl.innerHTML = `
          <div style="text-align: center; padding: 24px; color: var(--ink-secondary); font-size: 12px;">
            No endpoint response has been recorded yet for this delivery.
            ${data.oracle_status !== "DISPATCHED" ? '<div style="margin-top: 8px;"><button class="btn btn-primary btn-sm" onclick="dispatchCurrentOracleModalDelivery()">Send to Endpoint Now</button></div>' : ''}
          </div>
        `;
      } else {
        containerEl.innerHTML = itemsToRender.map((it, idx) => {
          const isJ5 = (it.target_type === 'j5' || (it.target_endpoint && it.target_endpoint.toLowerCase().includes('hxgnsmartcloud')));
          const payload = it.payload || {};
          const response = it.response || {};

          // --- J5 Inbound Message Response Layout ---
          if (isJ5) {
            const isItemSuccess = it.status === "SUCCESS";
            const itemBadgeClass = isItemSuccess ? "badge-success" : "badge-danger";
            const statusText = isItemSuccess ? `HTTP ${it.http_code || 200} Accepted` : `HTTP ${it.http_code || 500} Failed`;

            const payloadEntries = [
              { label: "Tag / Key", val: payload.tag || payload.messageTag || "--" },
              { label: "Reading Value", val: payload.value ?? payload.readingValue ?? "--" },
              { label: "Timestamp", val: payload.timestamp || "--" },
              { label: "Description", val: payload.description || "--" },
              { label: "UOM", val: payload.uom || "--" },
              { label: "Limit", val: (payload.limit !== undefined && payload.limit !== null && payload.limit !== "") ? payload.limit : "--" },
              { label: "Results", val: payload.results || "--" }
            ];

            const payloadRowsHtml = payloadEntries.map(e => `
              <tr>
                <td style="font-weight: 500; color: var(--ink-secondary); font-size: 11px; width: 110px; white-space: nowrap; padding: 3px 6px;">${escapeHtml(e.label)}</td>
                <td style="font-size: 11px; padding: 3px 6px;"><code style="font-family: var(--font-mono); color: var(--ink-primary);">${escapeHtml(String(e.val))}</code></td>
              </tr>
            `).join("");

            let responseBodyHtml = "";
            if (typeof response === "string" && response.trim().length > 0) {
              responseBodyHtml = `<div style="font-family: var(--font-mono); font-size: 11px; white-space: pre-wrap; word-break: break-all; color: var(--ink-primary);">${escapeHtml(response)}</div>`;
            } else if (response && typeof response === "object" && Object.keys(response).length > 0) {
              responseBodyHtml = `<pre style="margin: 0; font-family: var(--font-mono); font-size: 11px; white-space: pre-wrap; word-break: break-all; max-height: 160px; overflow-y: auto; color: var(--ink-primary);">${escapeHtml(JSON.stringify(response, null, 2))}</pre>`;
            } else if (it.error) {
              responseBodyHtml = `<div style="color: #dc2626; font-size: 11px; font-weight: 500;">${escapeHtml(it.error)}</div>`;
            } else {
              responseBodyHtml = `<div style="color: var(--ink-tertiary); font-style: italic; font-size: 11px;">(Empty body returned with HTTP ${it.http_code || 200} OK)</div>`;
            }

            return `
              <div style="background: var(--bg-surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 12px; margin-bottom: 12px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 6px;">
                  <div style="display: flex; align-items: center; gap: 8px;">
                    <span class="badge" style="font-size: 10px; padding: 2px 7px; background: rgba(99, 102, 241, 0.12); color: #4f46e5; border: 1px solid rgba(99, 102, 241, 0.3);">
                      <span class="badge-dot" style="background:#6366f1;"></span> J5 Hexagon Smart Cloud
                    </span>
                    <strong style="font-size: 12px; color: var(--ink-primary);">${escapeHtml(it.attribute_name || `Attribute #${idx+1}`)}</strong>
                  </div>
                  <div style="display: flex; align-items: center; gap: 8px;">
                    <span class="badge ${itemBadgeClass}" style="font-size: 10px; padding: 2px 7px;">
                      <span class="badge-dot"></span> ${statusText}
                    </span>
                  </div>
                </div>
                <div style="font-size: 11px; color: var(--ink-secondary); font-family: var(--font-mono); margin-bottom: 8px; word-break: break-all;">
                  Endpoint: <span style="color: var(--ink-primary);">${escapeHtml(it.target_endpoint || targetEndpoint)}</span>
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 8px;">
                  <div style="background: var(--bg-subtle); border: 1px solid var(--border); border-radius: 4px; padding: 8px;">
                    <div style="font-size: 11px; font-weight: 600; color: var(--ink-secondary); margin-bottom: 6px;">Sent Telemetry Payload:</div>
                    <table class="data-table" style="font-size: 11px; margin: 0; background: transparent; width: 100%;">
                      <tbody>${payloadRowsHtml}</tbody>
                    </table>
                  </div>
                  <div style="background: var(--bg-subtle); border: 1px solid var(--border); border-radius: 4px; padding: 8px;">
                    <div style="font-size: 11px; font-weight: 600; color: var(--ink-secondary); margin-bottom: 6px;">J5 Server Response:</div>
                    ${responseBodyHtml}
                  </div>
                </div>
              </div>
            `;
          }

          // --- Oracle ORDS Comparison Layout ---
          const links = response.links || [];
          const fields = [
            { key: "tag", label: "Tag / Meter ID" },
            { key: "description", label: "Description" },
            { key: "value", label: "Reading Value" },
            { key: "uom", label: "Unit of Measure (UOM)" },
            { key: "limit", label: "Operating Limit" },
            { key: "results", label: "Analysis Results" },
            { key: "timestamp", label: "Timestamp (UTC Zulu)" }
          ];

          const rowsHtml = fields.map(f => {
            const pVal = payload[f.key] !== undefined && payload[f.key] !== null ? String(payload[f.key]) : "";
            const rVal = response[f.key] !== undefined ? response[f.key] : null;
            const rValStr = rVal !== null && rVal !== undefined ? String(rVal) : null;

            let statusBadge = "";
            let rValDisplay = "";

            if (rValStr !== null) {
              rValDisplay = `<code style="font-family: var(--font-mono); font-weight: 600; color: var(--ink-primary);">${escapeHtml(rValStr)}</code>`;
              if (pVal !== "" && pVal === rValStr) {
                statusBadge = `<span class="badge badge-success" style="font-size: 10px; padding: 1px 6px;"><span class="badge-dot"></span> Saved &amp; Verified</span>`;
              } else {
                statusBadge = `<span class="badge badge-info" style="font-size: 10px; padding: 1px 6px;"><span class="badge-dot"></span> Recorded</span>`;
              }
            } else {
              rValDisplay = `<span style="color: #dc2626; font-style: italic; font-weight: 500; font-family: var(--font-mono);">null</span>`;
              if (pVal !== "") {
                statusBadge = `<span class="badge badge-warning" style="font-size: 10px; padding: 1px 6px; background: #fef3c7; color: #92400e; border: 1px solid #fde68a;"><span class="badge-dot" style="background:#f59e0b;"></span> Returned NULL</span>`;
              } else {
                statusBadge = `<span class="badge badge-pending" style="font-size: 10px; padding: 1px 6px;">Empty</span>`;
              }
            }

            const pValDisplay = pVal !== "" ? `<code style="font-family: var(--font-mono); font-size: 11px; color: var(--ink-primary);">${escapeHtml(pVal)}</code>` : `<span style="color: var(--ink-tertiary); font-style: italic;">(None)</span>`;

            return `
              <tr>
                <td style="font-weight: 500; color: var(--ink-secondary); font-size: 12px; white-space: nowrap;">
                  ${escapeHtml(f.label)}
                </td>
                <td style="font-size: 12px;">
                  ${pValDisplay}
                </td>
                <td style="font-size: 12px;">
                  ${rValDisplay}
                </td>
                <td style="text-align: right; white-space: nowrap;">
                  ${statusBadge}
                </td>
              </tr>
            `;
          }).join("");

          let linksHtml = "";
          if (Array.isArray(links) && links.length > 0) {
            linksHtml = `
              <div style="margin-top: 10px; padding-top: 8px; border-top: 1px dashed var(--border); font-size: 11px;">
                <div style="font-weight: 600; color: var(--ink-secondary); margin-bottom: 4px;">Oracle Resource Links:</div>
                <div style="display: flex; flex-direction: column; gap: 3px;">
                  ${links.map(l => `
                    <div style="display: flex; gap: 6px; align-items: baseline;">
                      <span class="badge badge-secondary" style="font-size: 9px; padding: 1px 5px; font-family: var(--font-mono); text-transform: uppercase;">${escapeHtml(l.rel || "link")}</span>
                      <a href="${escapeHtml(l.href)}" target="_blank" rel="noopener noreferrer" style="color: var(--brand); text-decoration: none; word-break: break-all; font-family: var(--font-mono); font-size: 11px;">
                        ${escapeHtml(l.href)}
                      </a>
                    </div>
                  `).join("")}
                </div>
              </div>
            `;
          }

          return `
            <div style="background: var(--bg-surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 12px; margin-bottom: 12px;">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 6px;">
                <div style="display: flex; align-items: center; gap: 8px;">
                  <span class="badge badge-info" style="font-size: 10px; padding: 2px 7px;">
                    <span class="badge-dot"></span> Oracle ORDS
                  </span>
                  <strong style="font-size: 12px; color: var(--ink-primary);">${escapeHtml(it.attribute_name || `Attribute #${idx+1}`)}</strong>
                </div>
                <div style="font-size: 11px; color: var(--ink-secondary); font-family: var(--font-mono);">
                  Endpoint: <span style="color: var(--ink-primary);">${escapeHtml(it.target_endpoint || targetEndpoint)}</span>
                </div>
              </div>
              <div class="table-responsive">
                <table class="data-table" style="font-size: 11px; margin: 0;">
                  <thead>
                    <tr>
                      <th style="width: 140px;">Property</th>
                      <th>Sent Payload (PI &rarr; Pipeline)</th>
                      <th>Echoed by Oracle ORDS</th>
                      <th style="width: 130px; text-align: right;">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    ${rowsHtml}
                  </tbody>
                </table>
              </div>
              ${linksHtml}
            </div>
          `;
        }).join("");
      }
    }

    // 3. Raw Response JSON
    if (rawJsonEl) {
      const rawData = disp.erp_response || disp;
      rawJsonEl.textContent = typeof rawData === "string" ? rawData : JSON.stringify(rawData, null, 2);
    }

    // 4. Meta & Buttons
    if (metaEl) {
      const hasJ5 = itemsToRender.some(it => it.target_type === 'j5' || (it.target_endpoint && it.target_endpoint.toLowerCase().includes('hxgnsmartcloud')));
      const hasOracle = itemsToRender.some(it => it.target_type !== 'j5' && (!it.target_endpoint || !it.target_endpoint.toLowerCase().includes('hxgnsmartcloud')));
      let sysLabel = "Oracle ORDS REST API";
      if (hasJ5 && hasOracle) sysLabel = "Oracle ORDS & Hexagon J5 Cloud";
      else if (hasJ5) sysLabel = "Hexagon J5 Cloud Inbound API (Basic Auth)";
      metaEl.innerHTML = `Dispatched via <strong>${escapeHtml(sysLabel)}</strong> · HTTP Code: <strong>${httpCode}</strong>`;
    }
    if (sendAgainBtn) {
      sendAgainBtn.style.display = "inline-block";
    }

    if (modal) modal.classList.add("active");
  } catch (err) {
    showToast("Error inspecting Endpoint response: " + err.message, "danger");
  }
}
window.showOracleResponseModal = showOracleResponseModal;
window.showEndpointResponseModal = showOracleResponseModal;

function closeOracleResponseModal() {
  const modal = document.getElementById("modal-oracle-response");
  if (modal) modal.classList.remove("active");
}

function copyOracleResponseJson(event) {
  if (event) event.stopPropagation();
  const rawJsonEl = document.getElementById("modal-oracle-raw-json");
  if (!rawJsonEl) return;
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(rawJsonEl.textContent);
    } else {
      const tmp = document.createElement("textarea");
      tmp.value = rawJsonEl.textContent;
      document.body.appendChild(tmp);
      tmp.select();
      document.execCommand("copy");
      document.body.removeChild(tmp);
    }
    showToast("Endpoint response JSON copied to clipboard!", "success");
  } catch (err) {
    showToast("Failed to copy JSON: " + err.message, "danger");
  }
}

async function dispatchCurrentOracleModalDelivery() {
  if (!currentOracleModalDelivery) return;
  const id = currentOracleModalDelivery.delivery_id;
  await dispatchSingleDelivery(id);
  // Reload and refresh modal
  await showOracleResponseModal(id);
}

function copyPiTemplateBody() {
  const codeEl = document.getElementById("pi-notification-template-code");
  if (!codeEl) return;
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(codeEl.textContent);
    } else {
      const tmp = document.createElement("textarea");
      tmp.value = codeEl.textContent;
      document.body.appendChild(tmp);
      tmp.select();
      document.execCommand("copy");
      document.body.removeChild(tmp);
    }
    showToast("PI Notification JSON template copied to clipboard!", "success");
  } catch (err) {
    showToast("Failed to copy template", "danger");
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
// ============================================================
function initMappings() {
  document.getElementById("btn-add-mapping-modal")?.addEventListener("click", () => openMappingModal());
  document.getElementById("btn-close-modal")?.addEventListener("click", closeMappingModal);
  document.getElementById("btn-cancel-modal")?.addEventListener("click", closeMappingModal);
  document.getElementById("mapping-form")?.addEventListener("submit", handleSaveMappingModal);
  document.getElementById("btn-save-all-mappings")?.addEventListener("click", saveMappingsToServer);
  document.getElementById("btn-load-sample-templates")?.addEventListener("click", loadSamplePresets);
  document.getElementById("btn-refresh-payload-preview")?.addEventListener("click", refreshPayloadPreview);
  document.getElementById("btn-modal-test-endpoint")?.addEventListener("click", handleModalTestEndpoint);

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
        <td colspan="7" style="text-align: center; color: var(--text-muted); padding: 2rem;">
          No attribute mappings defined yet. Click <strong>"Add Attribute"</strong> or <strong>"Load Preset Assets"</strong> to get started.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = currentMappings.map((m, idx) => {
    const scaleRound = `×${m.scale_factor || 1.0}, ${m.round_decimals ?? 2} dec`;
    const isJ5 = (m.target_type === 'j5' || (m.target_endpoint_url && m.target_endpoint_url.toLowerCase().includes('hxgnsmartcloud')));
    const defaultUrl = isJ5
      ? (currentSettings?.j5_endpoint?.url || 'https://dataflow-inbound-message-prd-ase1.eam.hxgnsmartcloud.com/api/message?tag=purchaseorder')
      : (currentSettings?.oracle_erp?.base_url ? `${currentSettings.oracle_erp.base_url.replace(/\/+$/, '')}/${(m.resource_endpoint || currentSettings?.oracle_erp?.resource_endpoint || '').replace(/^\/+/, '')}` : '--');
    const targetUrl = m.target_endpoint_url || defaultUrl;
    const tagDisplay = m.tag || m.meter_tag || '--';
    const descDisplay = m.description || m.name || '--';
    const limitDisplay = (m.limit !== undefined && m.limit !== null && m.limit !== "") ? m.limit : '--';
    const resultsDisplay = (m.results !== undefined && m.results !== null && m.results !== "") ? m.results : '--';
    const targetBadge = isJ5
      ? `<span class="badge" style="font-size: 10px; padding: 1px 6px; background: rgba(99, 102, 241, 0.12); color: #4f46e5; border: 1px solid rgba(99, 102, 241, 0.3);"><span class="badge-dot" style="background:#6366f1;"></span> J5</span>`
      : `<span class="badge badge-info" style="font-size: 10px; padding: 1px 6px;"><span class="badge-dot"></span> Oracle</span>`;

    return `
      <tr>
        <td>
          <input type="checkbox" ${m.enabled ? 'checked' : ''} onchange="toggleMappingActive(${idx}, this.checked)" style="width: 16px; height: 16px; cursor: pointer;">
        </td>
        <td style="vertical-align: top;">
          <div style="display: flex; align-items: center; gap: 6px; flex-wrap: wrap;">
            <strong style="color: var(--ink-primary); font-size: 13px;">${escapeHtml(m.attribute_name || '')}</strong>
            ${targetBadge}
          </div>
          <div style="font-size: 11px; color: var(--ink-tertiary); margin-top: 2px;" title="${escapeHtml(m.full_path || '')}">
            ${escapeHtml(m.element_path || m.full_path || '')}
          </div>
        </td>
        <td style="vertical-align: top;">
          <div style="display: flex; align-items: baseline; gap: 6px;">
            <code style="font-family: var(--font-mono); font-size: 11px; font-weight: 600; color: var(--ink-primary); background: var(--bg-subtle); padding: 1px 5px; border-radius: 4px; border: 1px solid var(--border);">${escapeHtml(tagDisplay)}</code>
          </div>
          <div style="font-size: 11px; color: var(--ink-secondary); margin-top: 2px;">
            ${escapeHtml(descDisplay)}
          </div>
        </td>
        <td style="vertical-align: top; max-width: 250px;">
          <span class="path-code" style="font-size: 10px; word-break: break-all; display: block;" title="${escapeHtml(targetUrl)}">
            ${escapeHtml(targetUrl)}
          </span>
        </td>
        <td style="vertical-align: top; font-size: 11px; white-space: nowrap;">
          <div><span style="color: var(--ink-secondary);">Limit:</span> <code>${escapeHtml(String(limitDisplay))}</code></div>
          <div style="margin-top: 2px;"><span style="color: var(--ink-secondary);">Results:</span> ${resultsDisplay !== '--' ? `<span class="badge badge-info" style="font-size: 10px; padding: 1px 5px;">${escapeHtml(resultsDisplay)}</span>` : `<span style="color: var(--ink-tertiary);">--</span>`}</div>
        </td>
        <td style="font-size: 0.78rem; color: var(--ink-secondary); vertical-align: top;">
          <div>${scaleRound}</div>
          <div style="font-size: 10px; color: var(--ink-tertiary);">${escapeHtml(m.uom || '')}</div>
        </td>
        <td style="text-align: right; vertical-align: top; white-space: nowrap;">
          <button class="btn btn-secondary btn-sm" onclick="editMapping(${idx})" style="padding: 0.2rem 0.45rem; margin-right: 0.2rem;">Edit</button>
          <button class="btn btn-outline btn-sm" onclick="testTableEndpoint(${idx})" style="padding: 0.2rem 0.45rem; margin-right: 0.2rem;" title="Test connectivity to this destination endpoint">Test</button>
          <button class="btn btn-danger btn-sm" onclick="deleteMapping(${idx})" style="padding: 0.2rem 0.45rem;">Delete</button>
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

function handleModalTargetTypeChange() {
  const isJ5 = document.getElementById("target-type-j5")?.checked;
  const heading = document.getElementById("modal-destination-heading");
  const labelUrl = document.getElementById("modal-label-endpoint-url");
  const inputUrl = document.getElementById("modal-target-endpoint-url");
  const helpUrl = document.getElementById("modal-endpoint-url-help");
  const labelTag = document.getElementById("modal-label-tag");
  const labelDesc = document.getElementById("modal-label-desc");
  const labelLimit = document.getElementById("modal-label-limit");
  const labelResults = document.getElementById("modal-label-results");
  const testBox = document.getElementById("modal-endpoint-test-box");
  if (testBox) {
    testBox.style.display = "none";
    testBox.innerHTML = "";
  }

  const defaultJ5Url = currentSettings?.j5_endpoint?.url || "https://dataflow-inbound-message-prd-ase1.eam.hxgnsmartcloud.com/api/message?tag=purchaseorder";
  const defaultOrdsUrl = (currentSettings?.oracle_erp?.base_url && currentSettings?.oracle_erp?.resource_endpoint)
    ? `${currentSettings.oracle_erp.base_url.replace(/\/+$/, '')}/${currentSettings.oracle_erp.resource_endpoint.replace(/^\/+/, '')}`
    : "https://gda83ebb4f9065b-ecoatpdev1.adb.ap-singapore-1.oraclecloudapps.com/ords/pims_int/Final_Discharge_Effluent/";

  if (isJ5) {
    if (heading) heading.textContent = "J5 Destination Endpoint (Hexagon Smart Cloud)";
    if (labelUrl) labelUrl.textContent = "J5 Inbound Message URL *";
    if (helpUrl) helpUrl.textContent = "Hexagon J5 Inbound Message API endpoint receiving JSON telemetry via HTTP Basic Auth.";
    if (labelTag) labelTag.textContent = "J5 Message Tag / Key";
    if (labelDesc) labelDesc.textContent = "J5 Description";
    if (labelLimit) labelLimit.textContent = "Operating Limit (Optional)";
    if (labelResults) labelResults.textContent = "Result / Status (Optional)";
    if (inputUrl && (!inputUrl.value || inputUrl.value.includes("oraclecloudapps.com"))) {
      inputUrl.value = defaultJ5Url;
    }
  } else {
    if (heading) heading.textContent = "Oracle Destination Endpoint (ORDS REST POST)";
    if (labelUrl) labelUrl.textContent = "Target POST URL *";
    if (helpUrl) helpUrl.textContent = "Individual ORDS table/resource POST URL configured by Oracle team for this specific telemetry item.";
    if (labelTag) labelTag.textContent = "Oracle Tag (tag)";
    if (labelDesc) labelDesc.textContent = "Oracle Description (description)";
    if (labelLimit) labelLimit.textContent = "Limit (limit)";
    if (labelResults) labelResults.textContent = "Results (results)";
    if (inputUrl && (!inputUrl.value || inputUrl.value.includes("hxgnsmartcloud.com"))) {
      inputUrl.value = defaultOrdsUrl;
    }
  }
}
window.handleModalTargetTypeChange = handleModalTargetTypeChange;

function openMappingModal(mapping = null, index = -1) {
  const modal = document.getElementById("mapping-modal");
  const title = document.getElementById("modal-title");
  const testBox = document.getElementById("modal-endpoint-test-box");
  if (testBox) {
    testBox.style.display = "none";
    testBox.innerHTML = "";
  }
  modal.classList.add("active");

  const defaultOrdsUrl = (currentSettings?.oracle_erp?.base_url && currentSettings?.oracle_erp?.resource_endpoint)
    ? `${currentSettings.oracle_erp.base_url.replace(/\/+$/, '')}/${currentSettings.oracle_erp.resource_endpoint.replace(/^\/+/, '')}`
    : "https://gda83ebb4f9065b-ecoatpdev1.adb.ap-singapore-1.oraclecloudapps.com/ords/pims_int/Final_Discharge_Effluent/";
  const defaultJ5Url = currentSettings?.j5_endpoint?.url || "https://dataflow-inbound-message-prd-ase1.eam.hxgnsmartcloud.com/api/message?tag=purchaseorder";

  if (mapping) {
    title.textContent = "Edit Attribute Mapping";
    document.getElementById("modal-mapping-id").value = index;

    const isJ5 = (mapping.target_type === 'j5' || (mapping.target_endpoint_url && mapping.target_endpoint_url.toLowerCase().includes('hxgnsmartcloud')));
    const radOracle = document.getElementById("target-type-oracle");
    const radJ5 = document.getElementById("target-type-j5");
    if (isJ5) {
      if (radJ5) radJ5.checked = true;
    } else {
      if (radOracle) radOracle.checked = true;
    }
    handleModalTargetTypeChange();

    document.getElementById("modal-target-endpoint-url").value = mapping.target_endpoint_url || (isJ5 ? defaultJ5Url : defaultOrdsUrl);
    document.getElementById("modal-target-tag").value = mapping.tag || mapping.meter_tag || "";
    document.getElementById("modal-description").value = mapping.description || mapping.name || "";
    document.getElementById("modal-limit").value = (mapping.limit !== undefined && mapping.limit !== null) ? mapping.limit : "";
    document.getElementById("modal-results").value = (mapping.results !== undefined && mapping.results !== null) ? mapping.results : "";
    document.getElementById("modal-attr-name").value = mapping.attribute_name || "";
    document.getElementById("modal-af-server").value = mapping.af_server || "PISRV01";
    document.getElementById("modal-af-database").value = mapping.af_database || "Plant_Operations";
    document.getElementById("modal-element-path").value = mapping.element_path || "";
    document.getElementById("modal-full-path").value = mapping.full_path || "";
    document.getElementById("modal-uom").value = mapping.uom || "";
    document.getElementById("modal-scale").value = mapping.scale_factor ?? 1.0;
    document.getElementById("modal-decimals").value = mapping.round_decimals ?? 2;
    document.getElementById("modal-enabled").checked = mapping.enabled ?? true;
  } else {
    title.textContent = "Add Attribute Mapping";
    document.getElementById("modal-mapping-id").value = "-1";
    document.getElementById("mapping-form").reset();
    const radOracle = document.getElementById("target-type-oracle");
    if (radOracle) radOracle.checked = true;
    handleModalTargetTypeChange();

    document.getElementById("modal-target-endpoint-url").value = defaultOrdsUrl;
    document.getElementById("modal-target-tag").value = "";
    document.getElementById("modal-description").value = "";
    document.getElementById("modal-limit").value = "";
    document.getElementById("modal-results").value = "";
    document.getElementById("modal-uom").value = "";
    document.getElementById("modal-attr-name").value = "";
    document.getElementById("modal-af-server").value = currentSettings?.pi_web_api?.af_server || "PISRV01";
    document.getElementById("modal-af-database").value = currentSettings?.pi_web_api?.af_database || "Plant_Operations";
    document.getElementById("modal-element-path").value = "";
    document.getElementById("modal-full-path").value = "";
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

async function handleModalTestEndpoint() {
  const urlInput = document.getElementById("modal-target-endpoint-url");
  const box = document.getElementById("modal-endpoint-test-box");
  const isJ5 = document.getElementById("target-type-j5")?.checked;
  const targetType = isJ5 ? "j5" : "oracle";
  const epName = isJ5 ? "Hexagon J5" : "Oracle ORDS";
  const url = urlInput?.value?.trim();
  if (!url) {
    showToast("Please enter a Target POST URL to test.", "warning");
    return;
  }
  if (box) {
    box.style.display = "block";
    box.className = "error-console";
    box.innerHTML = `Testing connection to ${epName} endpoint...`;
  }
  try {
    const res = await fetch("/api/mappings/test-endpoint", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ endpoint_url: url, target_type: targetType })
    });
    const result = await res.json();
    if (result.success) {
      if (box) {
        box.className = "error-console";
        box.innerHTML = `<span style="color: var(--success); font-weight: bold;">✓ ${escapeHtml(result.message)}</span>\nLatency: ${result.latency_ms}ms\nHTTP Status: ${result.status_code}\nEndpoint: ${escapeHtml(url)}`;
      }
      showToast(`${epName} endpoint connected successfully!`, "success");
    } else {
      if (box) {
        box.className = "error-console danger";
        box.innerHTML = `<span style="color: var(--danger); font-weight: bold;">✕ Connection Test Failed</span>\n${escapeHtml(result.message)}\n${escapeHtml(result.error || '')}`;
      }
      showToast(`Failed to connect to ${epName} endpoint`, "danger");
    }
  } catch (err) {
    if (box) {
      box.className = "error-console danger";
      box.innerHTML = `Test Request Error: ${escapeHtml(err.message)}`;
    }
  }
}
window.handleModalTestEndpoint = handleModalTestEndpoint;

async function testTableEndpoint(idx) {
  const m = currentMappings[idx];
  if (!m) return;
  const isJ5 = (m.target_type === 'j5' || (m.target_endpoint_url && m.target_endpoint_url.toLowerCase().includes('hxgnsmartcloud')));
  const targetType = isJ5 ? 'j5' : 'oracle';
  const defaultUrl = isJ5
    ? (currentSettings?.j5_endpoint?.url || 'https://dataflow-inbound-message-prd-ase1.eam.hxgnsmartcloud.com/api/message?tag=purchaseorder')
    : (currentSettings?.oracle_erp?.base_url ? `${currentSettings.oracle_erp.base_url.replace(/\/+$/, '')}/${(m.resource_endpoint || currentSettings?.oracle_erp?.resource_endpoint || '').replace(/^\/+/, '')}` : currentSettings?.oracle_erp?.base_url);
  const url = m.target_endpoint_url || defaultUrl;
  if (!url) {
    showToast("No target endpoint URL configured for this mapping.", "warning");
    return;
  }
  const epLabel = isJ5 ? "J5" : "Oracle ORDS";
  showToast(`Testing ${epLabel} endpoint for "${m.attribute_name}"...`, "info");
  try {
    const res = await fetch("/api/mappings/test-endpoint", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ endpoint_url: url, target_type: targetType })
    });
    const result = await res.json();
    if (result.success) {
      showToast(`✓ Connected (${result.latency_ms}ms): ${m.attribute_name}`, "success");
    } else {
      showToast(`✕ Test Failed (HTTP ${result.status_code || ''}): ${result.message}`, "danger");
    }
  } catch (err) {
    showToast("Test Request Error: " + err.message, "danger");
  }
}
window.testTableEndpoint = testTableEndpoint;

function handleSaveMappingModal(e) {
  e.preventDefault();
  const editIdx = parseInt(document.getElementById("modal-mapping-id").value, 10);
  const targetType = document.getElementById("target-type-j5")?.checked ? "j5" : "oracle";
  const tagVal = document.getElementById("modal-target-tag").value.trim();
  const descVal = document.getElementById("modal-description").value.trim();
  const limitVal = document.getElementById("modal-limit").value.trim();
  const resultsVal = document.getElementById("modal-results").value.trim();
  const targetEndpointUrl = document.getElementById("modal-target-endpoint-url").value.trim();

  const newMapping = {
    id: editIdx >= 0 ? currentMappings[editIdx].id : `map-${Date.now()}`,
    target_type: targetType,
    attribute_name: document.getElementById("modal-attr-name").value.trim(),
    af_server: document.getElementById("modal-af-server").value.trim(),
    af_database: document.getElementById("modal-af-database").value.trim(),
    element_path: document.getElementById("modal-element-path").value.trim(),
    full_path: document.getElementById("modal-full-path").value.trim(),
    web_id: editIdx >= 0 ? currentMappings[editIdx].web_id : "",
    target_endpoint_url: targetEndpointUrl,
    tag: tagVal,
    description: descVal,
    limit: limitVal,
    results: resultsVal,
    meter_tag: tagVal,
    target_field: "value",
    target_tag_field: "tag",
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
    const defaultOrdsUrl = "https://gda83ebb4f9065b-ecoatpdev1.adb.ap-singapore-1.oraclecloudapps.com/ords/pims_int/Final_Discharge_Effluent/";
    currentMappings = [
      {
        id: "map-final-discharge",
        name: "Final Discharge Effluent 30 Min Average",
        attribute_name: "30 Min Average",
        af_server: "PISRV01",
        af_database: "Plant_Operations",
        element_path: "Effluent\\Discharge",
        full_path: "\\\\PISRV01\\Plant_Operations\\Effluent\\Discharge|30 Min Average",
        target_endpoint_url: defaultOrdsUrl,
        tag: "",
        description: "",
        limit: "",
        results: "",
        target_field: "value",
        meter_tag: "",
        target_tag_field: "tag",
        scale_factor: 1.0,
        round_decimals: 2,
        uom: "",
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
        target_endpoint_url: defaultOrdsUrl,
        tag: "BLR101_STM_PRESS",
        description: "Boiler 101 Steam Pressure",
        limit: "100.0",
        results: "Normal",
        target_field: "value",
        meter_tag: "BLR101_STM_PRESS",
        target_tag_field: "tag",
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
        target_endpoint_url: defaultOrdsUrl,
        tag: "TG01_FEED_FLOW",
        description: "Turbine Feedwater Flow Rate",
        limit: "500.0",
        results: "Normal",
        target_field: "value",
        meter_tag: "TG01_FEED_FLOW",
        target_tag_field: "tag",
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
        target_endpoint_url: defaultOrdsUrl,
        tag: "GEN01_ACT_PWR",
        description: "Generator Active Power Output",
        limit: "50.0",
        results: "Normal",
        target_field: "value",
        meter_tag: "GEN01_ACT_PWR",
        target_tag_field: "tag",
        scale_factor: 1.0,
        round_decimals: 3,
        uom: "MW",
        enabled: false
      },
      {
        id: "map-pmp-vib",
        name: "Cooling Pump 2A Vibration",
        attribute_name: "Vibration Overall",
        af_server: "PISRV01",
        af_database: "Plant_Operations",
        element_path: "Utilities\\Pumps\\Pump-2A",
        full_path: "\\\\PISRV01\\Plant_Operations\\Utilities\\Pumps\\Pump-2A|Vibration Overall",
        target_endpoint_url: defaultOrdsUrl,
        tag: "PMP2A_VIB_RMS",
        description: "Cooling Pump 2A Vibration",
        limit: "4.5",
        results: "Normal",
        target_field: "value",
        meter_tag: "PMP2A_VIB_RMS",
        target_tag_field: "tag",
        scale_factor: 1.0,
        round_decimals: 2,
        uom: "mm/s",
        enabled: true
      },
      {
        id: "map-j5-purchaseorder",
        name: "J5 Inbound Message Telemetry",
        attribute_name: "Effluent Turbidity",
        af_server: "PISRV01",
        af_database: "Plant_Operations",
        element_path: "Effluent\\Discharge",
        full_path: "\\\\PISRV01\\Plant_Operations\\Effluent\\Discharge|Effluent Turbidity",
        target_type: "j5",
        target_endpoint_url: currentSettings?.j5_endpoint?.url || "https://dataflow-inbound-message-prd-ase1.eam.hxgnsmartcloud.com/api/message?tag=purchaseorder",
        tag: "TURBIDITY_01",
        description: "Effluent Discharge Turbidity NTU",
        limit: "25.0",
        results: "Normal",
        target_field: "value",
        meter_tag: "TURBIDITY_01",
        target_tag_field: "tag",
        scale_factor: 1.0,
        round_decimals: 2,
        uom: "NTU",
        enabled: true
      }
    ];

    renderMappingsTable();
    saveMappingsToServer();
    refreshPayloadPreview();
    showToast("Loaded industrial telemetry presets with Oracle ORDS & J5 endpoints.", "success");
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

  openMappingModal({
    attribute_name: name,
    af_server: server,
    af_database: db,
    element_path: elemPath,
    full_path: path,
    tag: "",
    description: "",
    limit: "",
    results: "",
    meter_tag: "",
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
  document.getElementById("btn-test-j5-settings")?.addEventListener("click", handleTestJ5Settings);
  document.getElementById("btn-toggle-j5-password")?.addEventListener("click", toggleJ5PasswordVisibility);

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

  // Endpoint Security Action Listeners
  document.getElementById("btn-copy-sec-api-key")?.addEventListener("click", copySecApiKey);
  document.getElementById("btn-generate-sec-api-key")?.addEventListener("click", generateNewSecApiKey);
  document.getElementById("btn-add-current-pi-ip")?.addEventListener("click", handleAddCurrentPiIp);
  document.getElementById("setting-sec-api-key-enabled")?.addEventListener("change", updateSecurityBadges);
  document.getElementById("setting-sec-ip-whitelist-enabled")?.addEventListener("change", updateSecurityBadges);

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

    // J5 Inbound Message Settings (Hexagon Smart Cloud)
    const j5 = currentSettings.j5_endpoint || {};
    const j5EnabledEl = document.getElementById("setting-j5-enabled");
    const j5UrlEl = document.getElementById("setting-j5-url");
    const j5UserEl = document.getElementById("setting-j5-username");
    const j5PassEl = document.getElementById("setting-j5-password");
    const j5TenantEl = document.getElementById("setting-j5-tenant-id");
    const j5TimeoutEl = document.getElementById("setting-j5-timeout");

    if (j5EnabledEl) j5EnabledEl.checked = j5.enabled !== undefined ? !!j5.enabled : true;
    if (j5UrlEl) j5UrlEl.value = j5.url || "https://dataflow-inbound-message-prd-ase1.eam.hxgnsmartcloud.com/api/message?tag=purchaseorder";
    if (j5UserEl) j5UserEl.value = j5.username || "HIRUJR_JZNOT1742577235_TST";
    if (j5PassEl) j5PassEl.value = j5.password || "kah4YAH!bvm-vkt_jzd";
    if (j5TenantEl) j5TenantEl.value = j5.tenant_id || "JZNOT1742577235_TST";
    if (j5TimeoutEl) j5TimeoutEl.value = j5.timeout_seconds || 15;

    // Pipeline Settings
    document.getElementById("setting-pipeline-interval").value = pipe.interval_seconds || 30;
    const autoDispatchEl = document.getElementById("setting-pipeline-auto-dispatch");
    if (autoDispatchEl) autoDispatchEl.checked = pipe.auto_dispatch !== undefined ? pipe.auto_dispatch : true;

    // Endpoint Security Settings
    const sec = currentSettings.endpoint_security || {};
    const apiKeyEnabledEl = document.getElementById("setting-sec-api-key-enabled");
    const apiKeyEl = document.getElementById("setting-sec-api-key");
    const ipWhitelistEnabledEl = document.getElementById("setting-sec-ip-whitelist-enabled");
    const allowedIpsEl = document.getElementById("setting-sec-allowed-ips");

    if (apiKeyEnabledEl) apiKeyEnabledEl.checked = !!sec.api_key_enabled;
    if (apiKeyEl) apiKeyEl.value = sec.api_key || "";
    if (ipWhitelistEnabledEl) ipWhitelistEnabledEl.checked = !!sec.ip_whitelist_enabled;
    if (allowedIpsEl) allowedIpsEl.value = sec.allowed_ips || "";

    updateSecurityBadges();

    handlePiAuthChange();
    handleErpAuthChange();

    await refreshMockERPStatus();
  } catch (e) {
    console.error("Error loading settings:", e);
  }
}

async function copySecApiKey() {
  const keyInput = document.getElementById("setting-sec-api-key");
  const key = keyInput?.value?.trim() || "";
  if (!key) {
    showToast("No API Key configured to copy.", "warning");
    return;
  }
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(key);
    } else {
      keyInput.select();
      document.execCommand("copy");
    }
    showToast("API Key copied to clipboard!", "success");
  } catch (e) {
    showToast("API Key: " + key, "info");
  }
}

async function generateNewSecApiKey() {
  try {
    const res = await fetch("/api/security/generate-key", { method: "POST" });
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    const keyInput = document.getElementById("setting-sec-api-key");
    if (keyInput && data.api_key) {
      keyInput.value = data.api_key;
      updateSecurityBadges();
      showToast("Generated new API Key! Click 'Save Settings' to activate.", "success");
    }
  } catch (e) {
    // Client-side fallback random generation if server call fails
    const randomKey = "pi_sec_" + Array.from(crypto.getRandomValues(new Uint8Array(16))).map(b => b.toString(16).padStart(2, '0')).join('');
    const keyInput = document.getElementById("setting-sec-api-key");
    if (keyInput) {
      keyInput.value = randomKey;
      updateSecurityBadges();
      showToast("Generated new API Key! Click 'Save Settings' to activate.", "success");
    }
  }
}

function handleAddCurrentPiIp() {
  const input = document.getElementById("setting-sec-allowed-ips");
  if (!input) return;
  const current = input.value.trim();
  const targetIp = "10.60.2.20";
  if (!current) {
    input.value = targetIp;
  } else if (!current.includes(targetIp)) {
    input.value = current + ", " + targetIp;
  }
  const checkbox = document.getElementById("setting-sec-ip-whitelist-enabled");
  if (checkbox) checkbox.checked = true;
  updateSecurityBadges();
  showToast("Added verified PI AF server IP (10.60.2.20) to whitelist!", "success");
}

function updateSecurityBadges() {
  const apiKeyChecked = document.getElementById("setting-sec-api-key-enabled")?.checked;
  const ipWhitelistChecked = document.getElementById("setting-sec-ip-whitelist-enabled")?.checked;
  const badgeKey = document.getElementById("badge-api-key-status");
  const badgeIp = document.getElementById("badge-ip-whitelist-status");
  const badgeActive = document.getElementById("security-active-badge");
  const tableHeader = document.getElementById("guide-table-header");
  const apiKeyVal = document.getElementById("setting-sec-api-key")?.value?.trim() || "<YOUR_API_KEY>";

  if (badgeKey) {
    badgeKey.className = apiKeyChecked ? "badge badge-success" : "badge badge-pending";
    badgeKey.textContent = apiKeyChecked ? "Enforced" : "Disabled";
  }

  if (badgeIp) {
    badgeIp.className = ipWhitelistChecked ? "badge badge-success" : "badge badge-pending";
    badgeIp.textContent = ipWhitelistChecked ? "Enforced" : "Disabled";
  }

  if (badgeActive) {
    if (apiKeyChecked && ipWhitelistChecked) {
      badgeActive.className = "badge badge-success";
      badgeActive.textContent = "API Key + IP Whitelist Active";
    } else if (apiKeyChecked) {
      badgeActive.className = "badge badge-info";
      badgeActive.textContent = "API Key Active";
    } else if (ipWhitelistChecked) {
      badgeActive.className = "badge badge-info";
      badgeActive.textContent = "IP Whitelist Active";
    } else {
      badgeActive.className = "badge badge-pending";
      badgeActive.textContent = "Open Access (No Security)";
    }
  }

  if (tableHeader) {
    tableHeader.textContent = apiKeyChecked ? `X-API-Key: ${apiKeyVal}` : "X-API-Key: <YOUR_API_KEY> (Disabled)";
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
  document.querySelectorAll(".erp-none-field").forEach(el => el.style.display = (type === "none") ? "block" : "none");
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
    j5_endpoint: {
      enabled: document.getElementById("setting-j5-enabled") ? document.getElementById("setting-j5-enabled").checked : true,
      url: document.getElementById("setting-j5-url") ? document.getElementById("setting-j5-url").value.trim() : "https://dataflow-inbound-message-prd-ase1.eam.hxgnsmartcloud.com/api/message?tag=purchaseorder",
      auth_type: "basic",
      username: document.getElementById("setting-j5-username") ? document.getElementById("setting-j5-username").value.trim() : "HIRUJR_JZNOT1742577235_TST",
      password: document.getElementById("setting-j5-password") ? document.getElementById("setting-j5-password").value : "kah4YAH!bvm-vkt_jzd",
      tenant_id: document.getElementById("setting-j5-tenant-id") ? document.getElementById("setting-j5-tenant-id").value.trim() : "JZNOT1742577235_TST",
      timeout_seconds: parseInt(document.getElementById("setting-j5-timeout")?.value, 10) || 15
    },
    pipeline: {
      interval_seconds: parseInt(document.getElementById("setting-pipeline-interval").value, 10) || 30,
      ingestion_mode: document.querySelector('input[name="setting-ingestion-mode"]:checked')?.value || "endpoint",
      auto_dispatch: document.getElementById("setting-pipeline-auto-dispatch") ? document.getElementById("setting-pipeline-auto-dispatch").checked : true,
      auto_start: currentSettings?.pipeline?.auto_start !== undefined ? currentSettings.pipeline.auto_start : true,
      max_history_items: 100
    },
    endpoint_security: {
      api_key_enabled: document.getElementById("setting-sec-api-key-enabled") ? document.getElementById("setting-sec-api-key-enabled").checked : false,
      api_key: document.getElementById("setting-sec-api-key") ? document.getElementById("setting-sec-api-key").value.trim() : "",
      ip_whitelist_enabled: document.getElementById("setting-sec-ip-whitelist-enabled") ? document.getElementById("setting-sec-ip-whitelist-enabled").checked : false,
      allowed_ips: document.getElementById("setting-sec-allowed-ips") ? document.getElementById("setting-sec-allowed-ips").value.trim() : ""
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

async function handleTestJ5Settings() {
  const cfg = collectSettingsFromForm().j5_endpoint;
  const box = document.getElementById("j5-test-result-box");
  if (!box) return;
  box.style.display = "block";
  box.className = "error-console";
  box.innerHTML = "Testing connection to Hexagon J5 Cloud endpoint with Basic Authentication...";

  try {
    const res = await fetch("/api/settings/test-j5", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cfg)
    });
    const result = await res.json();
    if (result.success) {
      box.className = "error-console";
      box.innerHTML = `<span style="color: var(--success); font-weight: bold;">✓ ${escapeHtml(result.message)}</span>\nLatency: ${result.latency_ms}ms\nHTTP Status: ${result.status_code}\nEndpoint: ${escapeHtml(result.endpoint_tested || cfg.url)}`;
      showToast("J5 endpoint connected successfully!", "success");
    } else {
      box.className = "error-console danger";
      let text = `<span style="color: var(--danger); font-weight: bold;">✕ J5 Connection Test Failed</span>\nMessage: ${escapeHtml(result.message)}`;
      if (result.status_code) {
        text += `\nHTTP Status: ${result.status_code}`;
      }
      if (result.endpoint_tested) {
        text += `\nTested Endpoint: ${escapeHtml(result.endpoint_tested)}`;
      }
      text += `\n\n${escapeHtml(result.error || '')}`;
      box.innerHTML = text;
      showToast("Failed to connect to J5 endpoint", "danger");
    }
  } catch (e) {
    box.className = "error-console danger";
    box.innerHTML = `Request Exception: ${escapeHtml(e.message)}`;
  }
}
window.handleTestJ5Settings = handleTestJ5Settings;

function toggleJ5PasswordVisibility() {
  const input = document.getElementById("setting-j5-password");
  const btn = document.getElementById("btn-toggle-j5-password");
  if (!input || !btn) return;
  if (input.type === "password") {
    input.type = "text";
    btn.textContent = "Hide";
  } else {
    input.type = "password";
    btn.textContent = "Show";
  }
}
window.toggleJ5PasswordVisibility = toggleJ5PasswordVisibility;

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
