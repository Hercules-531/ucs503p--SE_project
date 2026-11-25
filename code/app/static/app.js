const menuButton = document.querySelector(".mobile-menu");
const nav = document.querySelector("#main-nav");

if (menuButton && nav) {
  menuButton.addEventListener("click", () => {
    const expanded = menuButton.getAttribute("aria-expanded") === "true";
    menuButton.setAttribute("aria-expanded", String(!expanded));
    nav.classList.toggle("is-open", !expanded);
  });
}

document.querySelectorAll("[data-copy-target]").forEach((button) => {
  button.addEventListener("click", async () => {
    const target = document.getElementById(button.dataset.copyTarget);
    if (!target) return;
    try {
      await navigator.clipboard.writeText(target.textContent.trim());
      const original = button.textContent;
      button.textContent = "Copied";
      window.setTimeout(() => { button.textContent = original; }, 1400);
    } catch {
      button.textContent = "Select key to copy";
    }
  });
});

const playground = document.querySelector("#api-playground");

if (playground) {
  const readinessStatus = document.querySelector("#readiness-status");
  fetch("/health/ready", { cache: "no-store" })
    .then((response) => { readinessStatus.textContent = response.ok ? "Ready" : "Unavailable"; })
    .catch(() => { readinessStatus.textContent = "Unavailable"; });
  const endpointSelect = document.querySelector("#endpoint-select");
  const parameterInput = document.querySelector("#endpoint-parameter");
  const parameterLabel = document.querySelector("#parameter-label");
  const requestUrl = document.querySelector("#request-url");
  const responseTarget = document.querySelector("#api-response");
  const requestStatus = document.querySelector("#request-status");
  const requestCount = document.querySelector("#request-count");
  const demoKey = document.querySelector("#demo-key").textContent.trim();
  let count = 0;

  const endpointConfig = {
    schemes: {
      label: "Search text (optional)",
      placeholder: "Try health",
      defaultValue: "",
      path: (value) => value ? `/api/v1/schemes?q=${encodeURIComponent(value)}` : "/api/v1/schemes",
    },
    scheme: {
      label: "Scheme ID",
      placeholder: "scheme-pm-kisan",
      defaultValue: "scheme-pm-kisan",
      path: (value) => `/api/v1/schemes/${encodeURIComponent(value || "scheme-pm-kisan")}`,
    },
    pincode: {
      label: "Six-digit PIN code",
      placeholder: "147004",
      defaultValue: "147004",
      path: (value) => `/api/v1/locations/pincode/${encodeURIComponent(value || "147004")}`,
    },
  };

  function updateRequestPreview(resetValue = false) {
    const config = endpointConfig[endpointSelect.value];
    parameterLabel.textContent = config.label;
    parameterInput.placeholder = config.placeholder;
    if (resetValue) parameterInput.value = config.defaultValue;
    requestUrl.textContent = config.path(parameterInput.value.trim());
  }

  const initialParams = new URLSearchParams(window.location.search);
  const initialEndpoint = initialParams.get("endpoint");
  if (initialEndpoint && endpointConfig[initialEndpoint]) {
    endpointSelect.value = initialEndpoint;
    parameterInput.value = initialParams.get("id") || endpointConfig[initialEndpoint].defaultValue;
  }
  updateRequestPreview(false);
  endpointSelect.addEventListener("change", () => updateRequestPreview(true));
  parameterInput.addEventListener("input", () => updateRequestPreview(false));

  playground.addEventListener("submit", async (event) => {
    event.preventDefault();
    const path = endpointConfig[endpointSelect.value].path(parameterInput.value.trim());
    requestUrl.textContent = path;
    requestStatus.textContent = "Requesting…";
    requestStatus.className = "request-status";
    responseTarget.textContent = "Loading response…";
    const startedAt = performance.now();

    try {
      const key = document.querySelector("#playground-key")?.value.trim() || demoKey;
      const response = await fetch(path, { headers: { "X-API-Key": key } });
      const payload = await response.json();
      const elapsed = Math.round(performance.now() - startedAt);
      responseTarget.textContent = JSON.stringify(payload, null, 2);
      requestStatus.textContent = `${response.status} · ${elapsed} ms`;
      requestStatus.className = `request-status ${response.ok ? "success" : "error"}`;
    } catch {
      responseTarget.textContent = JSON.stringify({
        error: { code: "NETWORK_ERROR", message: "The local API could not be reached." },
      }, null, 2);
      requestStatus.textContent = "Request failed";
      requestStatus.className = "request-status error";
    }

    if (demoKey) {
      count += 1;
      requestCount.textContent = String(count);
    } else {
      document.dispatchEvent(new Event("bharatos:request-complete"));
    }
  });
}

const developerAccess = document.querySelector("#developer-access");
if (developerAccess) {
  const loginForm = document.querySelector("#developer-login");
  const signedIn = document.querySelector("#developer-signed-in");
  const message = document.querySelector("#developer-message");
  const keyList = document.querySelector("#developer-key-list");
  const newKey = document.querySelector("#new-key");
  const newKeyContainer = document.querySelector("#new-key-container");
  const usageAverage = document.querySelector("#usage-average");
  const usageToday = document.querySelector("#usage-today");
  const usageEndpoints = document.querySelector("#usage-endpoints");
  let sessionToken = null;

  async function request(path, method = "GET", body = null) {
    const headers = {};
    if (body) headers["Content-Type"] = "application/json";
    if (sessionToken) headers.Authorization = `Bearer ${sessionToken}`;
    const response = await fetch(path, { method, headers, body: body ? JSON.stringify(body) : undefined });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error?.message || "The request could not be completed.");
    return payload;
  }

  function resetSession() {
    sessionToken = null;
    newKey.textContent = "";
    newKeyContainer.hidden = true;
    keyList.replaceChildren();
    loginForm.hidden = false;
    signedIn.hidden = true;
    document.querySelector("#playground-key").value = "";
    document.querySelector("#request-count").textContent = "0";
    usageAverage.textContent = "Sign in to load usage.";
    usageToday.hidden = true;
    usageEndpoints.replaceChildren();
  }

  async function refreshUsage() {
    if (!sessionToken) return;
    try {
      const usage = await request("/api/v1/developers/usage");
      document.querySelector("#request-count").textContent = String(usage.total_requests);
      usageToday.textContent = `Requests today (UTC): ${usage.requests_today}. All-time success rate: ${
        usage.success_rate === null ? "—" : (usage.success_rate * 100).toFixed(1) + "%"
      }.`;
      usageToday.hidden = false;
      usageAverage.textContent = usage.average_duration_ms === null
        ? "No recorded requests yet."
        : `Average recorded duration: ${usage.average_duration_ms} ms.`;
      usageEndpoints.replaceChildren();
      usage.endpoints.forEach((endpoint) => {
        const item = document.createElement("li");
        item.textContent = `${endpoint.path}: ${endpoint.count} request${endpoint.count === 1 ? "" : "s"}`;
        usageEndpoints.append(item);
      });
    } catch (error) {
      usageAverage.textContent = "Usage could not be loaded.";
      usageToday.hidden = true;
      usageEndpoints.replaceChildren();
      message.textContent = error.message;
    }
  }
  document.addEventListener("bharatos:request-complete", refreshUsage);
  document.querySelector("#refresh-usage").addEventListener("click", refreshUsage);

  async function refreshKeys() {
    const result = await request("/api/v1/developers/keys");
    keyList.replaceChildren();
    if (!result.keys.length) {
      const empty = document.createElement("li");
      empty.textContent = "No keys yet.";
      keyList.append(empty);
    }
    result.keys.forEach((key) => {
      const item = document.createElement("li");
      const label = document.createElement("span");
      label.textContent = `${key.prefix}… (${key.revoked ? "revoked" : "active"}) `;
      item.append(label);
      if (!key.revoked) {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = "Revoke";
        button.setAttribute("aria-label", `Revoke key ${key.prefix}`);
        button.addEventListener("click", async () => {
          button.disabled = true;
          try {
            await request(`/api/v1/developers/keys/${encodeURIComponent(key.id)}`, "DELETE");
            message.textContent = "Key revoked.";
            await refreshKeys();
          } catch (error) { message.textContent = error.message; button.disabled = false; }
        });
        item.append(button);
        const rotate = document.createElement("button");
        rotate.type = "button";
        rotate.textContent = "Rotate";
        rotate.setAttribute("aria-label", `Rotate key ${key.prefix}`);
        rotate.addEventListener("click", async () => {
          if (!window.confirm("Rotating immediately revokes this key. Existing applications must use the replacement. Continue?")) return;
          rotate.disabled = true;
          try {
            const replacement = await request(`/api/v1/developers/keys/${encodeURIComponent(key.id)}/rotate`, "POST");
            newKey.textContent = replacement.key;
            newKeyContainer.hidden = false;
            document.querySelector("#playground-key").value = replacement.key;
            message.textContent = "Key rotated. Save the replacement now; it will not be shown again.";
            await refreshKeys();
          } catch (error) {
            message.textContent = `${error.message} If the response was interrupted, check your keys and create another if needed.`;
            rotate.disabled = false;
          }
        });
        item.append(" ", rotate);
      }
      keyList.append(item);
    });
  }

  function credentials() {
    return { email: document.querySelector("#developer-email").value, password: document.querySelector("#developer-password").value };
  }

  document.querySelector("#developer-register").addEventListener("click", async () => {
    if (!loginForm.reportValidity()) return;
    try {
      await request("/api/v1/developers/register", "POST", credentials());
      message.textContent = "Account created. Sign in to continue.";
    } catch (error) { message.textContent = error.message; }
  });

  loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const result = await request("/api/v1/developers/login", "POST", credentials());
      sessionToken = result.session_token;
      document.querySelector("#developer-password").value = "";
      loginForm.hidden = true;
      signedIn.hidden = false;
      message.textContent = "Signed in. Your session is kept only on this page.";
      await refreshKeys();
      await refreshUsage();
    } catch (error) { message.textContent = error.message; }
  });

  document.querySelector("#developer-create-key").addEventListener("click", async () => {
    try {
      const result = await request("/api/v1/developers/keys", "POST");
      newKey.textContent = result.key;
      newKeyContainer.hidden = false;
      document.querySelector("#playground-key").value = result.key;
      message.textContent = "Key created. Save it now; it will not be shown again.";
      await refreshKeys();
    } catch (error) { message.textContent = error.message; }
  });

  document.querySelector("#developer-logout").addEventListener("click", async () => {
    try {
      await request("/api/v1/developers/logout", "POST");
      message.textContent = "Signed out.";
      resetSession();
    } catch (error) { message.textContent = error.message; }
  });
}

const adminAccess = document.querySelector("#admin-access");
if (adminAccess) {
  adminAccess.addEventListener("submit", async (event) => {
    event.preventDefault();
    const message = document.querySelector("#admin-message");
    const results = document.querySelector("#admin-results");
    const token = document.querySelector("#admin-token").value;
    const buttons = adminAccess.querySelectorAll("button");
    buttons.forEach((button) => { button.disabled = true; });
    message.textContent = event.submitter?.value === "check" ? "Checking official pages…" : "Loading monitoring data…";
    try {
      if (event.submitter?.value === "check") {
        const checked = await fetch("/api/v1/admin/source-checks", {
          method: "POST", headers: { "X-Admin-Token": token }, cache: "no-store",
        });
        if (!checked.ok) {
          const failure = await checked.json();
          throw new Error(failure.error?.message || "Unable to check official pages.");
        }
      }
      const response = await fetch("/api/v1/admin/overview", {
        headers: { "X-Admin-Token": token }, cache: "no-store",
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error?.message || "Unable to load monitoring.");
      document.querySelector("#admin-schemes").textContent = payload.record_counts.scheme || 0;
      document.querySelector("#admin-locations").textContent = payload.record_counts.location || 0;
      document.querySelector("#admin-requests").textContent = payload.request_count;
      document.querySelector("#admin-errors").textContent = payload.error_count;
      document.querySelector("#admin-error-rate").textContent = payload.error_rate === null
        ? "HTTP 4xx and 5xx"
        : `${(payload.error_rate * 100).toFixed(1)}% of recorded requests`;
      const recentErrors = payload.recent_api_errors.by_route;
      const errorRows = document.querySelector("#admin-recent-errors");
      errorRows.replaceChildren();
      recentErrors.forEach(({ route, status, count }) => {
        const row = document.createElement("tr");
        [route, status, count].forEach((value) => {
          const cell = document.createElement("td");
          cell.textContent = String(value);
          row.append(cell);
        });
        errorRows.append(row);
      });
      document.querySelector("#admin-recent-errors-table").hidden = recentErrors.length === 0;
      document.querySelector("#admin-recent-errors-empty").hidden = recentErrors.length !== 0;
      const cache = payload.cache;
      document.querySelector("#admin-cache").textContent = cache.status === "available"
        ? `Hits: ${cache.hits}; misses: ${cache.misses}; recorded errors: ${cache.errors}; hit ratio: ${cache.hit_ratio === null ? "not yet available" : `${(cache.hit_ratio * 100).toFixed(1)}%`}.`
        : `Cache metrics: ${cache.status.replaceAll("_", " ")}.`;
      const alerts = document.querySelector("#admin-alerts");
      alerts.replaceChildren();
      payload.alerts.forEach((alert) => {
        const item = document.createElement("li");
        item.textContent = `${alert.severity.toUpperCase()}: ${alert.message}`;
        alerts.append(item);
      });
      document.querySelector("#admin-alerts-empty").hidden = payload.alerts.length > 0;
      const probes = document.querySelector("#admin-probes");
      probes.replaceChildren();
      payload.source_checks.forEach((probe) => {
        const row = document.createElement("tr");
        [probe.source, probe.status.replaceAll("_", " "), probe.http_status ?? "—",
          probe.checked_at || "Not checked"].forEach((value) => {
          const cell = document.createElement("td");
          cell.textContent = String(value);
          row.append(cell);
        });
        probes.append(row);
      });
      const sources = document.querySelector("#admin-sources");
      sources.replaceChildren();
      payload.sources.forEach((source) => {
        const row = document.createElement("tr");
        const percent = (value) => value === null ? "Not available" : `${value}%`;
        const snapshotScope = source.complete_snapshot == null ? "Unknown"
          : source.complete_snapshot ? "Complete snapshot" : "Partial import";
        [source.source, source.record_kind || "Unknown", snapshotScope,
          source.records, percent(source.freshness_percent),
          percent(source.completeness_percent), percent(source.consistency_percent),
          source.review_due, source.unknown,
          source.oldest_verified || "Unknown", source.last_import_status].forEach((value) => {
          const cell = document.createElement("td");
          cell.textContent = String(value);
          row.append(cell);
        });
        sources.append(row);
      });
      document.querySelector("#admin-sources-empty").hidden = payload.sources.length > 0;
      const body = document.querySelector("#admin-runs");
      body.replaceChildren();
      payload.recent_ingestion_runs.forEach((run) => {
        const row = document.createElement("tr");
        [run.source, run.status, run.accepted, run.started_at].forEach((value) => {
          const cell = document.createElement("td");
          cell.textContent = String(value);
          row.append(cell);
        });
        body.append(row);
      });
      document.querySelector("#admin-empty").hidden = payload.recent_ingestion_runs.length > 0;
      results.hidden = false;
      document.querySelector("#admin-token").value = "";
      message.textContent = "Monitoring data loaded. Enter the token again to refresh.";
    } catch (error) {
      results.hidden = true;
      message.textContent = error.message || "Unable to load monitoring.";
    } finally {
      buttons.forEach((button) => { button.disabled = false; });
    }
  });
}
