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
      label: "Search or category (optional)",
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
      const response = await fetch(path, { headers: { "X-API-Key": demoKey } });
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

    count += 1;
    requestCount.textContent = String(count);
  });
}
