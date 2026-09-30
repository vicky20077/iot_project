/* ==========================================================================
   AI Obstacle Assistance — Dashboard client logic
   Polls the Flask API (no API keys ever touch this file) and updates
   the DOM. The /video_feed <img> streams itself via multipart MJPEG.
   ========================================================================== */

const POLL_INTERVAL_MS = 1000;

function riskClass(risk) {
  switch ((risk || "").toUpperCase()) {
    case "CRITICAL": return "risk-critical";
    case "HIGH": return "risk-high";
    case "WARNING":
    case "WATCH":
    case "MEDIUM": return "risk-medium";
    case "SAFE": return "risk-safe";
    default: return "risk-safe";
  }
}

function setDot(prefix, state) {
  const dot = document.getElementById(`dot-${prefix}`);
  const label = document.getElementById(`status-${prefix}`);
  if (!dot || !label) return;
  dot.classList.remove("dot-online", "dot-offline", "dot-error");
  if (state === true) {
    dot.classList.add("dot-online");
    label.textContent = "Connected";
  } else {
    dot.classList.add("dot-offline");
    label.textContent = "Offline";
  }
}

async function pollStatus() {
  try {
    const res = await fetch("/api/status");
    if (!res.ok) throw new Error("status fetch failed");
    const data = await res.json();
    setDot("camera", data.camera);
    setDot("arduino", data.arduino);
    setDot("roboflow", data.roboflow);
  } catch (err) {
    setDot("camera", false);
    setDot("arduino", false);
    setDot("roboflow", false);
  }
}

async function pollDetection() {
  try {
    const res = await fetch("/api/detection");
    if (!res.ok) throw new Error("detection fetch failed");
    const d = await res.json();

    const objectText = d.object || "—";
    const confidenceText = d.object ? `${Math.round((d.confidence || 0) * 100)}%` : "—";
    const distanceText = d.distance !== null && d.distance !== undefined ? `${Math.round(d.distance)} cm` : "— cm";
    const riskText = d.risk || "—";
    const cls = riskClass(d.risk);

    document.getElementById("metric-object").textContent = objectText;
    document.getElementById("metric-confidence").textContent = confidenceText;
    document.getElementById("metric-distance").textContent = distanceText;
    document.getElementById("metric-approaching").textContent =
      d.approaching ? "YES" : "NO";

    const metricRisk = document.getElementById("metric-risk");
    metricRisk.textContent = riskText;
    metricRisk.className = `metric-value risk-badge ${cls}`;

    document.getElementById("summary-object").textContent = objectText;
    document.getElementById("summary-confidence").textContent = confidenceText;
    document.getElementById("summary-distance").textContent = distanceText;
    document.getElementById("summary-approaching").textContent =
      d.approaching ? "YES" : "NO";

    const summaryRisk = document.getElementById("summary-risk");
    summaryRisk.textContent = riskText;
    summaryRisk.className = `summary-value risk-badge ${cls}`;
  } catch (err) {
    // Leave last known values on screen; status panel already shows offline state.
  }
}

async function pollAlerts() {
  try {
    const res = await fetch("/api/alerts");
    if (!res.ok) throw new Error("alerts fetch failed");
    const data = await res.json();
    const list = document.getElementById("alerts-list");
    list.innerHTML = "";

    if (!data.alerts || data.alerts.length === 0) {
      const li = document.createElement("li");
      li.className = "alerts-empty";
      li.textContent = "No alerts yet.";
      list.appendChild(li);
      return;
    }

    data.alerts.forEach((alert) => {
      const li = document.createElement("li");
      const time = document.createElement("span");
      time.className = "alert-time";
      time.textContent = alert.time;
      const msg = document.createElement("span");
      msg.textContent = `${alert.message} — ${alert.risk}`;
      li.appendChild(time);
      li.appendChild(msg);
      list.appendChild(li);
    });
  } catch (err) {
    // keep last rendered list on failure
  }
}

function pollAll() {
  pollStatus();
  pollDetection();
  pollAlerts();
}

pollAll();
setInterval(pollAll, POLL_INTERVAL_MS);
