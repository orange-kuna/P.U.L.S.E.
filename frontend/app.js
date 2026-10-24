(() => {
  "use strict";

  const $ = (selector) => document.querySelector(selector);
  const state = { config: null, result: null, weather: null, charts: [], busy: false };
  const palette = { navy: "#102b3a", teal: "#167a78", orange: "#ed653f", gold: "#c18c2b", grid: "#dce2dc", muted: "#65747a" };
  const number = (value, digits = 1) => Number(value).toLocaleString(undefined, { maximumFractionDigits: digits });
  const timeStamp = (iso) => new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" }) + " UTC";
  const escaped = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);

  async function request(url, options) {
    const response = await fetch(url, options);
    const type = response.headers.get("content-type") || "";
    const data = type.includes("application/json") ? await response.json() : await response.text();
    if (!response.ok) throw new Error(typeof data === "object" ? data.detail || response.statusText : response.statusText);
    return data;
  }

  function showError(message, title = "Request failed") {
    $("#error-title").textContent = title;
    $("#error-message").textContent = message;
    $("#error-banner").classList.add("visible");
  }
  function clearError() { $("#error-banner").classList.remove("visible"); }
  function busy(loading) {
    state.busy = loading;
    $("#loading-strip").classList.toggle("visible", loading);
    for (const button of [$("#run-simulation"), $("#refresh-weather"), $("#scan-windows")]) {
      if (button) button.disabled = loading;
    }
    if ($("#run-simulation")) $("#run-simulation").textContent = loading ? "Calculating trajectory…" : "Run simulation →";
  }

  function renderProfileNote() {
    const selected = state.config.profiles.find((item) => item.id === $("#profile").value);
    $("#profile-description").textContent = selected ? selected.description : "";
  }

  function fillConfig(config) {
    state.config = config;
    $("#profile").innerHTML = config.profiles.map((p) =>
      `<option value="${escaped(p.id)}">${escaped(p.name)}</option>`).join("");
    $("#site").innerHTML = config.sites.map((s) =>
      `<option value="${escaped(s.id)}">${escaped(s.name)} · ${escaped(s.region)}</option>`).join("");
    for (const [key, value] of Object.entries(config.defaults)) {
      const control = $(`[name="${key}"]`);
      if (control && control.type === "radio") {
        const radio = document.querySelector(`[name="${key}"][value="${value}"]`);
        if (radio) radio.checked = true;
      } else if (control) control.value = String(value);
    }
    updateOutputs();
    renderProfileNote();
    $("#connection-label").textContent = "API ONLINE";
    $("#connection-label").parentElement.style.color = "var(--teal)";
  }

  function updateOutputs() {
    const values = [
      ["duration", "duration-output", (x) => `${x} s`],
      ["throttle", "throttle-output", (x) => `${Math.round(x * 100)}%`],
      ["pitch", "pitch-output", (x) => `${x}°`],
      ["heading", "heading-output", (x) => `${x}°`],
      ["q-limit", "q-limit-output", (x) => `${x} kPa`],
      ["wind-limit", "wind-limit-output", (x) => `${x} m/s`],
    ];
    for (const [input, output, format] of values) $(`#${output}`).textContent = format(Number($(`#${input}`).value));
  }

  function formBody() {
    const localTime = $("#launch-time").value;
    return {
      profile_id: $("#profile").value,
      site_id: $("#site").value,
      weather_mode: document.querySelector('[name="weather_mode"]:checked').value,
      duration_s: Number($("#duration").value),
      pitch_deg: Number($("#pitch").value),
      heading_deg: Number($("#heading").value),
      throttle: Number($("#throttle").value),
      max_q_limit_kpa: Number($("#q-limit").value),
      wind_limit_ms: Number($("#wind-limit").value),
      ...(localTime ? { launch_time: new Date(localTime).toISOString() } : {}),
    };
  }

  async function runSimulation(event) {
    event?.preventDefault();
    if (state.busy) return;
    clearError();
    busy(true);
    try {
      const result = await request("/api/simulate", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formBody()),
      });
      state.result = result;
      state.weather = result.weather;
      renderResult(result);
      $("#export-csv").disabled = false;
      $("#export-json").disabled = false;
    } catch (error) {
      showError(error.message || "Could not run the simulation. Previous results are preserved.", "Simulation unavailable");
    } finally { busy(false); }
  }

  function updateMetric(id, value, unit, digits = 1) {
    $(`#${id}`).innerHTML = `${number(value, digits)}<span class="metric-unit">${escaped(unit)}</span>`;
  }

  function destroyCharts() {
    for (const chart of state.charts) chart.destroy();
    state.charts = [];
  }

  function chartBase() {
    return {
      responsive: true, maintainAspectRatio: false, animation: { duration: 350 },
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { labels: { usePointStyle: true, boxWidth: 7, color: palette.muted, font: { family: "DM Mono", size: 9 } } },
        tooltip: { titleFont: { family: "DM Mono" }, bodyFont: { family: "DM Mono" } },
      },
      scales: {
        x: { type: "linear", title: { display: true, text: "Elapsed time (s)", color: palette.muted, font: { family: "DM Mono", size: 9 } }, grid: { color: palette.grid }, ticks: { color: palette.muted, maxTicksLimit: 7 } },
      },
    };
  }

  function renderCharts(rows) {
    destroyCharts();
    if (!window.Chart) {
      showError("The local chart library did not load. Values and exports remain available.", "Charts unavailable");
      return;
    }
    const flight = chartBase();
    flight.data = {
      datasets: [
        { label: "Altitude (km)", data: rows.map((r) => ({ x: r.time_s, y: r.altitude_km })), borderColor: palette.orange, backgroundColor: palette.orange, pointRadius: 0, borderWidth: 2, yAxisID: "y" },
        { label: "Speed (m/s)", data: rows.map((r) => ({ x: r.time_s, y: r.velocity_ms })), borderColor: palette.teal, backgroundColor: palette.teal, pointRadius: 0, borderWidth: 2, borderDash: [5, 3], yAxisID: "y1" },
      ],
    };
    flight.options.scales.y = { type: "linear", position: "left", beginAtZero: true, title: { display: true, text: "Altitude (km)", color: palette.orange, font: { family: "DM Mono", size: 9 } }, grid: { color: palette.grid }, ticks: { color: palette.muted, maxTicksLimit: 5 } };
    flight.options.scales.y1 = { type: "linear", position: "right", beginAtZero: true, title: { display: true, text: "Speed (m/s)", color: palette.teal, font: { family: "DM Mono", size: 9 } }, grid: { drawOnChartArea: false }, ticks: { color: palette.muted, maxTicksLimit: 5 } };
    state.charts.push(new Chart($("#flight-chart"), { type: "line", data: flight.data, options: flight.options }));

    const q = chartBase();
    q.data = { datasets: [{ label: "Dynamic pressure (kPa)", data: rows.map((r) => ({ x: r.time_s, y: r.q_kpa })), borderColor: palette.orange, backgroundColor: "rgba(237,101,63,.10)", pointRadius: 0, borderWidth: 2, fill: true, tension: 0 }] };
    q.options.scales.y = { type: "linear", beginAtZero: true, title: { display: true, text: "Dynamic pressure (kPa)", color: palette.muted, font: { family: "DM Mono", size: 9 } }, grid: { color: palette.grid }, ticks: { color: palette.muted, maxTicksLimit: 5 } };
    state.charts.push(new Chart($("#q-chart"), { type: "line", data: q.data, options: q.options }));
  }

  function renderTrajectory(rows) {
    const container = $("#trajectory");
    const width = 800, height = 210, left = 56, right = 18, top = 14, bottom = 32;
    const maxX = Math.max(...rows.map((r) => Math.abs(r.downrange_km)), 1);
    const maxY = Math.max(...rows.map((r) => r.altitude_km), 1);
    const points = rows.map((r) => {
      const x = left + (r.downrange_km / maxX) * (width - left - right);
      const y = top + (1 - r.altitude_km / maxY) * (height - top - bottom);
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    }).join(" ");
    const ground = height - bottom;
    container.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="presentation" aria-hidden="true">
      <defs><linearGradient id="trajFill" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#ed653f" stop-opacity=".19"/><stop offset="1" stop-color="#ed653f" stop-opacity="0"/></linearGradient></defs>
      <line class="svg-grid" x1="${left}" x2="${width - right}" y1="${top}" y2="${top}"/><line class="svg-grid" x1="${left}" x2="${width - right}" y1="${(top + ground) / 2}" y2="${(top + ground) / 2}"/><line class="svg-grid" x1="${left}" x2="${width - right}" y1="${ground}" y2="${ground}"/>
      <text class="axis-label" x="4" y="${top + 5}">${number(maxY, 0)} km</text><text class="axis-label" x="8" y="${ground}">0</text><text class="axis-label" x="${left}" y="${height - 7}">0 km</text><text class="axis-label" text-anchor="end" x="${width - right}" y="${height - 7}">${number(maxX, 1)} km downrange</text>
      <polygon class="trajectory-fill" points="${left},${ground} ${points} ${left + (rows.at(-1).downrange_km / maxX) * (width - left - right)},${ground}"/>
      <polyline class="trajectory-line" points="${points}"/>
      <circle class="trajectory-point" cx="${left + (rows.at(-1).downrange_km / maxX) * (width - left - right)}" cy="${top + (1 - rows.at(-1).altitude_km / maxY) * (height - top - bottom)}" r="4"/>
    </svg>`;
  }

  function renderRisk(risk) {
    $("#risk-overall").textContent = risk.overall;
    $("#risk-overall").setAttribute("aria-label", `Screening status: ${risk.overall}`);
    $("#risk-dot").className = `status-dot ${risk.overall}`;
    $("#risk-caption").textContent = "Screening status is not launch clearance.";
    $("#risk-checks").innerHTML = risk.checks.map((check) => {
      const value = check.value == null ? "Unavailable" : `${number(check.value, 2)} ${check.unit}`;
      const limit = check.limit == null ? "" : ` · limit ${number(check.limit, 2)} ${check.unit}`;
      return `<div class="check"><span class="check-mark ${escaped(check.status)}" aria-hidden="true">${check.status === "nominal" ? "OK" : check.status === "caution" ? "!" : "×"}</span><div class="check-copy"><b>${escaped(check.name)} · ${escaped(check.status)}</b><small>${escaped(value + limit)}</small><div class="field-help">${escaped(check.detail)}</div></div></div>`;
    }).join("");
  }

  function renderEvents(events) {
    $("#events-list").innerHTML = events.map((event) =>
      `<div class="event"><time class="event-time">${number(event.time_s, 2)} s</time><i class="event-node" aria-hidden="true"></i><div><div class="event-name">${escaped(event.name)}</div><div class="event-detail">${escaped(event.detail)}</div></div></div>`).join("");
  }

  function renderResult(result) {
    updateMetric("metric-altitude", result.summary.max_altitude_km, "km", 2);
    updateMetric("metric-velocity", result.summary.max_velocity_ms, "m/s", 0);
    updateMetric("metric-q", result.summary.max_q_kpa, "kPa", 2);
    updateMetric("metric-heat", result.summary.max_heating_kw_m2, "kW/m²", 2);
    $("#metric-q-caption").textContent = `PEAK AT ${number(result.summary.max_q_time_s, 1)} S`;
    $("#run-meta").textContent = `${result.profile.name} · ${result.site.name} · ${timeStamp(result.created_at)} · ${result.telemetry.length} samples`;
    $("#model-meta").textContent = `${result.weather.label} · ${result.weather.valid_at}`;
    renderCharts(result.telemetry);
    renderTrajectory(result.telemetry);
    renderRisk(result.risk);
    renderEvents(result.events);
    renderWeather(result.weather);
  }

  function renderWeather(weather) {
    state.weather = weather;
    const surface = weather.surface;
    $("#weather-temp").innerHTML = `${number(surface.temperature_c, 1)}<small>°C / SURFACE</small>`;
    $("#weather-description").textContent = `${weather.label} · valid ${timeStamp(weather.valid_at)}`;
    $("#weather-source").textContent = weather.source === "open-meteo" ? "OPEN-METEO FORECAST" : "MODELED REFERENCE";
    $("#weather-source").className = `badge ${weather.source === "standard" ? "caution" : ""}`;
    const readings = [
      ["Wind", `${number(surface.wind_ms, 1)} m/s`],
      ["Precipitation", surface.precipitation_mm == null ? "Not modeled" : `${number(surface.precipitation_mm, 2)} mm/h`],
      ["Cloud cover", surface.cloud_cover_pct == null ? "Not modeled" : `${number(surface.cloud_cover_pct, 0)}%`],
      ["Humidity", surface.humidity_pct == null ? "Not modeled" : `${number(surface.humidity_pct, 0)}%`],
    ];
    $("#weather-readings").innerHTML = readings.map(([label, value]) => `<div class="weather-reading"><span>${escaped(label)}</span><b>${escaped(value)}</b></div>`).join("");
    $("#weather-note").textContent = weather.note;
    $("#atmo-method").textContent = `${weather.note} Altitude above mean sea level; pressure-level model heights are approximate.`;
    $("#atmo-rows").innerHTML = weather.layers.map((layer) =>
      `<tr><td>${number(layer.altitude_m / 1000, 2)} km</td><td>${number(layer.pressure_pa / 100, 1)} hPa</td><td>${number(layer.temperature_c, 1)} °C</td><td>${Number(layer.density_kg_m3).toPrecision(3)} kg/m³</td><td>${number(layer.wind_east_ms, 1)} m/s</td><td>${number(layer.wind_north_ms, 1)} m/s</td><td>${number(layer.wind_ms, 1)} m/s</td></tr>`).join("");
  }

  async function refreshWeather() {
    if (state.busy) return;
    clearError();
    busy(true);
    try {
      const weather = await request(`/api/weather?site_id=${encodeURIComponent($("#site").value)}`);
      renderWeather(weather);
      $("#weather-description").textContent += " · fetched independently; simulation results unchanged";
    } catch (error) {
      showError(error.message || "No live forecast is available. Previous atmosphere data is preserved.", "Live forecast unavailable");
    } finally { busy(false); }
  }

  async function scanWindows() {
    if (state.busy) return;
    clearError();
    busy(true);
    $("#window-list").innerHTML = "";
    $("#windows-state").innerHTML = "<strong>Requesting forecast</strong>Sampling 12 hourly-model times from Open-Meteo.";
    try {
      const result = await request("/api/windows", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(formBody()),
      });
      const recommendedTime = result.recommended.launch_time;
      $("#window-list").innerHTML = `<div class="window-row" aria-hidden="true" style="font:8px var(--mono);color:var(--muted);text-transform:uppercase"><span>Forecast time · UTC</span><span>Profile wind</span><span>Rain</span><span>Relative index</span><span>Screen / factors</span></div>` +
        result.windows.map((window) => {
          const recommended = window.launch_time === recommendedTime;
          return `<article class="window-row ${recommended ? "recommended" : ""}"><time class="window-time">${timeStamp(window.launch_time)}${recommended ? " · top score" : ""}</time><span class="window-val">${number(window.wind_ms, 1)} m/s</span><span class="window-val">${number(window.precipitation_mm, 2)} mm/h</span><span class="window-val">${number(window.score, 0)} / 100</span><span><span class="badge ${escaped(window.status)}">${escaped(window.status)}</span><span class="window-reasons">${window.reasons.map(escaped).join(" · ")}</span></span></article>`;
        }).join("");
      $("#windows-state").innerHTML = `<strong>${result.windows.length} forecast hours sampled</strong>${escaped(result.site.name)} · sampled every three hours over 36 hours.`;
      $("#window-method").textContent = `${result.method} ${result.note} This relative index is not a launch probability, clearance or actual recommendation.`;
    } catch (error) {
      $("#windows-state").innerHTML = "<strong>Forecast unavailable</strong>The scan could not complete. No simulated substitute was generated.";
      showError(error.message || "No live forecast is available.", "Window scan unavailable");
    } finally { busy(false); }
  }

  function setView(name) {
    const valid = ["simulation", "atmosphere", "windows"];
    if (!valid.includes(name)) return;
    document.querySelectorAll(".view").forEach((view) => view.classList.toggle("active", view.id === `view-${name}`));
    document.querySelectorAll(".nav-item[data-view]").forEach((item) => item.classList.toggle("active", item.dataset.view === name));
    $("#crumb-title").textContent = name.toUpperCase();
    if (name === "windows" && !$("#window-list").children.length) {
      $("#windows-state").innerHTML = "<strong>Ready to scan</strong>This fetches real forecast data and can take several seconds.";
    }
    document.body.classList.remove("menu-open");
    $("#mobile-menu").setAttribute("aria-expanded", "false");
    window.location.hash = name;
  }

  function wireEvents() {
    document.querySelectorAll("input[type=range]").forEach((input) => input.addEventListener("input", updateOutputs));
    $("#profile").addEventListener("change", renderProfileNote);
    $("#simulation-form").addEventListener("submit", runSimulation);
    $("#refresh-weather").addEventListener("click", refreshWeather);
    $("#scan-windows").addEventListener("click", scanWindows);
    $("#export-csv").addEventListener("click", () => { if (state.result) window.location.href = `/api/export/${state.result.id}.csv`; });
    $("#export-json").addEventListener("click", () => { if (state.result) window.location.href = `/api/export/${state.result.id}.json`; });
    document.querySelectorAll("[data-view]").forEach((link) => link.addEventListener("click", (event) => {
      event.preventDefault();
      setView(link.dataset.view);
    }));
    $("#mobile-menu").addEventListener("click", () => {
      const opened = document.body.classList.toggle("menu-open");
      $("#mobile-menu").setAttribute("aria-expanded", String(opened));
    });
    $("#utc-clock").textContent = `${new Date().toISOString().slice(0, 16).replace("T", " ")} UTC`;
    const hash = window.location.hash.replace("#", "");
    if (hash) setView(hash);
  }

  async function init() {
    wireEvents();
    try {
      const config = await request("/api/config");
      fillConfig(config);
      await runSimulation();
    } catch (error) {
      $("#connection-label").textContent = "API OFFLINE";
      showError(error.message || "The simulation service could not start.", "Workbench unavailable");
    }
  }
  document.addEventListener("DOMContentLoaded", init, { once: true });
})();
