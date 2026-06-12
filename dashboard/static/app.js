const monthSelect = document.querySelector("#month");
const dashboard = document.querySelector("#dashboard");
const emptyState = document.querySelector("#emptyState");

const fmt = (value, digits = 3) =>
  value === null || value === undefined
    ? "Pending"
    : Number(value).toFixed(digits);

const pct = (value) =>
  value === null || value === undefined
    ? "Pending"
    : `${(Number(value) * 100).toFixed(1)}%`;

function setText(id, value) {
  document.querySelector(`#${id}`).textContent = value;
}

function chart(canvas, rows, series, thresholds = []) {
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  const pad = { left: 56, right: 18, top: 18, bottom: 42 };
  ctx.clearRect(0, 0, width, height);
  ctx.strokeStyle = "#d7dde7";
  ctx.lineWidth = 1;
  ctx.font = "11px Segoe UI";
  ctx.fillStyle = "#667085";

  const values = rows.flatMap((row) =>
    series.map((item) => Number(row[item.key])).filter(Number.isFinite)
  );
  const thresholdValues = thresholds.map((item) => item.value);
  const max = Math.max(1, ...values, ...thresholdValues);
  const min = 0;
  const x = (index) =>
    pad.left + (index * (width - pad.left - pad.right)) / Math.max(rows.length - 1, 1);
  const y = (value) =>
    pad.top + ((max - value) * (height - pad.top - pad.bottom)) / (max - min);

  for (let step = 0; step <= 4; step += 1) {
    const value = min + ((max - min) * step) / 4;
    const py = y(value);
    ctx.beginPath();
    ctx.moveTo(pad.left, py);
    ctx.lineTo(width - pad.right, py);
    ctx.stroke();
    ctx.fillText(value.toFixed(2), 10, py + 4);
  }

  thresholds.forEach((item) => {
    ctx.save();
    ctx.setLineDash([6, 5]);
    ctx.strokeStyle = item.color;
    ctx.beginPath();
    ctx.moveTo(pad.left, y(item.value));
    ctx.lineTo(width - pad.right, y(item.value));
    ctx.stroke();
    ctx.restore();
  });

  series.forEach((item) => {
    ctx.strokeStyle = item.color;
    ctx.fillStyle = item.color;
    ctx.lineWidth = 3;
    ctx.beginPath();
    let started = false;
    rows.forEach((row, index) => {
      const value = Number(row[item.key]);
      if (!Number.isFinite(value)) return;
      if (!started) {
        ctx.moveTo(x(index), y(value));
        started = true;
      } else {
        ctx.lineTo(x(index), y(value));
      }
    });
    ctx.stroke();
    rows.forEach((row, index) => {
      const value = Number(row[item.key]);
      if (!Number.isFinite(value)) return;
      ctx.beginPath();
      ctx.arc(x(index), y(value), 4, 0, Math.PI * 2);
      ctx.fill();
    });
  });

  ctx.fillStyle = "#667085";
  rows.forEach((row, index) => {
    if (index % Math.max(Math.ceil(rows.length / 8), 1) !== 0 && index !== rows.length - 1) return;
    const label = String(row.snapshot_date).slice(0, 7);
    ctx.fillText(label, x(index) - 18, height - 16);
  });
}

function render(payload) {
  if (!payload.ready) {
    dashboard.hidden = true;
    emptyState.hidden = false;
    emptyState.textContent = payload.message;
    return;
  }
  dashboard.hidden = false;
  emptyState.hidden = true;

  if (!monthSelect.options.length) {
    payload.months.forEach((month) => {
      const option = document.createElement("option");
      option.value = month;
      option.textContent = month.slice(0, 7);
      monthSelect.appendChild(option);
    });
  }
  monthSelect.value = payload.selected_month;

  const s = payload.summary;
  setText("modelName", s.model_name || "-");
  setText("modelVersion", s.model_version || "-");
  setText("labelStatus", String(s.observation_status).replaceAll("_", " "));
  setText("dataDriftStatus", String(s.data_drift_status).replaceAll("_", " "));
  setText("performanceDriftStatus", String(s.performance_drift_status).replaceAll("_", " "));
  setText("monitoringStatus", String(s.monitoring_status).replaceAll("_", " "));
  document.querySelector("#monitoringStatus").className = `status ${s.monitoring_status}`;
  setText("p0Label", `P0 ${String(s.p0_name).replaceAll("_", " ")}`);
  setText("p0Value", fmt(s.p0_value));
  setText("p1Label", `P1 ${String(s.p1_name).replaceAll("_", " ")}`);
  setText("p1Value", fmt(s.p1_value));
  setText("psiValue", fmt(s.psi));
  setText("predictionCount", Number(s.prediction_count).toLocaleString());
  setText("predictedRate", pct(s.predicted_default_rate));
  setText("observedRate", pct(s.observed_default_rate));
  setText("watchCount", s.watch_feature_count);
  setText("significantCount", s.significant_feature_count);

  const psiText =
    s.psi === null ? "Population labels unavailable" :
    s.psi < 0.1 ? "Stable: below 0.10" :
    s.psi <= 0.25 ? "Watch: moderate drift" :
    "Significant drift";
  setText("psiInterpretation", psiText);

  chart(
    document.querySelector("#performanceChart"),
    payload.performance,
    [
      { key: "p0_metric_value", color: "#2764c4" },
      { key: "p1_metric_value", color: "#25835b" },
    ]
  );
  chart(
    document.querySelector("#psiChart"),
    payload.performance,
    [{ key: "psi", color: "#b7791f" }],
    [
      { value: 0.1, color: "#b7791f" },
      { value: 0.25, color: "#c53b32" },
    ]
  );

  const tbody = document.querySelector("#driftRows");
  tbody.replaceChildren();
  payload.drift.forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.feature_name}</td>
      <td>${fmt(row.csi)}</td>
      <td><span class="badge ${row.drift_status}">${row.drift_status.replaceAll("_", " ")}</span></td>
      <td>${fmt(row.baseline_mean)}</td>
      <td>${fmt(row.current_mean)}</td>
    `;
    tbody.appendChild(tr);
  });
}

async function load() {
  const query = monthSelect.value ? `?month=${encodeURIComponent(monthSelect.value)}` : "";
  const response = await fetch(`/api/monitoring${query}`, { cache: "no-store" });
  render(await response.json());
}

monthSelect.addEventListener("change", load);
document.querySelector("#refresh").addEventListener("click", load);
load();
