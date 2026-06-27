const monthSelect = document.querySelector("#month");
const dashboard = document.querySelector("#dashboard");
const emptyState = document.querySelector("#emptyState");
let cachedPayload = null;

const fmt = (value, digits = 3) => {
  const number = numericValue(value);
  return number === null ? "-" : number.toFixed(digits);
};

const pct = (value) => {
  const number = numericValue(value);
  return number === null ? "-" : `${(number * 100).toFixed(1)}%`;
};

function numericValue(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function setText(id, value) {
  document.querySelector(`#${id}`).textContent = value;
}

function monthLabel(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 7);
  const month = date.toLocaleString("en-US", { month: "short" });
  const year = String(date.getFullYear()).slice(-2);
  return `${month}-${year}`;
}

function chartMonthLabel(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 7);
  const month = date.toLocaleString("en-US", { month: "short" });
  return `${month} ${date.getFullYear()}`;
}

function normalizeStatus(status) {
  return String(status || "unknown").replaceAll("_", " ");
}

function compactRangeLabel(label) {
  return String(label || "-").replace(/\b([A-Z][a-z]{2}) (\d{4})-([A-Z][a-z]{2}) \2\b/g, "$1-$3 $2");
}

function compactDevelopmentLabel(payload) {
  const splits = payload.split_summary || {};
  if (splits.train || splits.validation || splits.test) {
    const labels = [splits.train?.label, splits.validation?.label, splits.test?.label].filter(Boolean);
    if (labels.length === 3 && new Set(labels).size === 1) {
      return `Development: ${compactRangeLabel(labels[0])} loan-level 80/10/10`;
    }
    const parts = [];
    if (splits.train?.label) parts.push(`Train ${compactRangeLabel(splits.train.label)}`);
    if (splits.validation?.label) parts.push(`Validation ${compactRangeLabel(splits.validation.label)}`);
    if (splits.test?.label) parts.push(`Test ${compactRangeLabel(splits.test.label)}`);
    return `Development: ${parts.join(" | ")}`;
  }
  return `Development: ${compactRangeLabel(payload.period_summary?.development_period || "-")}`;
}

function compactOotLabel(payload) {
  const label = payload.split_summary?.oot?.label || payload.period_summary?.oot_window || "-";
  return `OOT monitoring: ${compactRangeLabel(label)}`;
}

function statusTone(status) {
  if (status === "stable" || status === "pass") return "stable";
  if (status === "watch") return "watch";
  if (status === "significant_drift" || status === "fail") return "alert";
  return "neutral";
}

function isOotOrHoldout(row) {
  const split = String(row.data_split || "").toLowerCase();
  return ["validation", "test", "oot", "prediction"].includes(split);
}

function isDeployedMonitoringRow(row) {
  const split = String(row.data_split || "").toLowerCase();
  return ["oot", "prediction"].includes(split);
}

function selectedChampionMetrics(payload) {
  const championName = payload.registry?.champion_model || payload.summary?.model_name;
  const rows = payload.evaluation || [];
  const validation = rows.find(
    (row) => row.model_name === championName && String(row.dataset).toLowerCase() === "validation"
  );
  const test = rows.find(
    (row) => row.model_name === championName && String(row.dataset).toLowerCase() === "test"
  );

  return {
    validation_recall:
      numericValue(validation?.p0_metric_value) ??
      numericValue(validation?.recall) ??
      null,
    validation_pr_auc:
      numericValue(validation?.p1_metric_value) ??
      numericValue(validation?.pr_auc) ??
      null,
    governance_score:
      numericValue(validation?.governance_score) ?? null,
    test_recall:
      numericValue(test?.p0_metric_value) ?? numericValue(test?.recall) ?? null,
    test_pr_auc:
      numericValue(test?.p1_metric_value) ?? numericValue(test?.pr_auc) ?? null,
  };
}

function leaderboardRows(payload) {
  const validationRows = (payload.evaluation || [])
    .filter((row) => String(row.dataset).toLowerCase() === "validation")
    .map((row) => ({
      name: displayModelName(row),
      recall: numericValue(row.p0_metric_value) ?? numericValue(row.recall),
      pr_auc: numericValue(row.p1_metric_value) ?? numericValue(row.pr_auc),
      governance: numericValue(row.governance_score),
      family: row.model_family || row.base_model_name || row.model_name,
    }))
    .filter((row) => row.recall !== null && row.pr_auc !== null && row.governance !== null);

  if (!validationRows.length) return [];

  const bestByFamily = new Map();
  validationRows.forEach((row) => {
    const current = bestByFamily.get(row.family);
    if (!current || row.governance > current.governance) bestByFamily.set(row.family, row);
  });

  return [...bestByFamily.values()]
    .sort((a, b) => b.governance - a.governance)
    .slice(0, 4)
    .map((row) => [row.name, row.recall, row.pr_auc, row.governance]);
}

function displayModelName(row) {
  const raw = row.base_model_name || row.model_family || row.model_name || "Model";
  return displayRawModelName(raw);
}

function displayRawModelName(raw) {
  const cleaned = String(raw)
    .replaceAll("_", " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
  if (cleaned.toLowerCase().includes("hist gradient")) return "HGB Champion";
  if (cleaned.toLowerCase().includes("xgboost")) return "XGBoost";
  if (cleaned.toLowerCase().includes("random forest")) return "Random Forest";
  if (cleaned.toLowerCase().includes("logistic regression")) return "Logistic Regression";
  return cleaned;
}

function resizeCanvas(canvas, height = 285) {
  const ratio = window.devicePixelRatio || 1;
  const width = Math.max(canvas.clientWidth, 320);
  canvas.width = Math.floor(width * ratio);
  canvas.height = Math.floor(height * ratio);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  return { ctx, width, height };
}

function drawLineChart(canvas, rows, series, options = {}) {
  const { ctx, width, height } = resizeCanvas(canvas, options.height || 285);
  const pad = { left: 44, right: 26, top: 24, bottom: 40 };
  ctx.clearRect(0, 0, width, height);
  ctx.font = "11px Inter, Segoe UI, sans-serif";
  ctx.lineWidth = 1;

  const values = rows.flatMap((row) =>
    series.map((item) => numericValue(row[item.key])).filter((value) => value !== null)
  );
  const thresholds = options.thresholds || [];
  const rawMax = Math.max(0.1, ...values, ...thresholds.map((item) => item.value));
  const step = options.tickStep || 0.25;
  const yMax = options.yMax || Math.ceil(rawMax / step) * step;
  const x = (index) =>
    pad.left + (index * (width - pad.left - pad.right)) / Math.max(rows.length - 1, 1);
  const y = (value) =>
    pad.top + ((yMax - value) * (height - pad.top - pad.bottom)) / yMax;

  if (options.developmentUntil) {
    const boundaryIndex = rows.findIndex((row) => new Date(row.snapshot_date) > new Date(options.developmentUntil));
    if (boundaryIndex > 0) {
      const boundaryX = x(boundaryIndex - 0.5);
      ctx.fillStyle = "rgba(102, 112, 133, 0.08)";
      ctx.fillRect(pad.left, pad.top, boundaryX - pad.left, height - pad.top - pad.bottom);
      ctx.strokeStyle = "rgba(102, 112, 133, 0.55)";
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(boundaryX, pad.top);
      ctx.lineTo(boundaryX, height - pad.bottom);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = "#667085";
      ctx.font = "10px Inter, Segoe UI, sans-serif";
      ctx.fillText("2023 dev", pad.left + 4, pad.top + 12);
      ctx.fillText("OOT", boundaryX + 6, pad.top + 12);
      ctx.font = "11px Inter, Segoe UI, sans-serif";
    }
  }

  if (options.deploymentMarker && rows.length) {
    const markerIndex = Math.max(0, rows.findIndex((row) => {
      const rowDate = new Date(row.snapshot_date);
      return rowDate >= new Date(options.deploymentMarker);
    }));
    const markerX = x(markerIndex);
    if (options.shadeFromDeployment) {
      ctx.fillStyle = "rgba(197, 59, 50, 0.06)";
      ctx.fillRect(markerX, pad.top, width - pad.right - markerX, height - pad.top - pad.bottom);
    }
    ctx.strokeStyle = "rgba(96, 112, 138, 0.42)";
    ctx.setLineDash([3, 3]);
    ctx.beginPath();
    ctx.moveTo(markerX, pad.top);
    ctx.lineTo(markerX, height - pad.bottom);
    ctx.stroke();
    ctx.setLineDash([]);
    if (options.deploymentLabel) {
      const boxWidth = 78;
      const boxHeight = 34;
      const boxX = Math.min(Math.max(markerX - boxWidth / 2, pad.left + 4), width - pad.right - boxWidth - 4);
      const boxY = pad.top + 10;
      ctx.fillStyle = "#eef2f7";
      ctx.strokeStyle = "#d7dfeb";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.roundRect(boxX, boxY, boxWidth, boxHeight, 5);
      ctx.fill();
      ctx.stroke();
      ctx.fillStyle = "#0b2a59";
      ctx.font = "700 9px Inter, Segoe UI, sans-serif";
      ctx.fillText("DEPLOYMENT", boxX + 11, boxY + 13);
      ctx.fillText(options.deploymentLabel, boxX + 17, boxY + 26);
      ctx.font = "11px Inter, Segoe UI, sans-serif";
    }
  }

  if (options.highlightKey) {
    rows.forEach((row, index) => {
      const value = numericValue(row[options.highlightKey]);
      const highlightAbove = numericValue(options.highlightAbove);
      if (value === null || highlightAbove === null || value <= highlightAbove) return;
      const nextX = rows.length > 1 ? x(Math.min(index + 1, rows.length - 1)) : width - pad.right;
      const previousX = rows.length > 1 ? x(Math.max(index - 1, 0)) : pad.left;
      const bandWidth = Math.max(16, (nextX - previousX) / 2);
      ctx.fillStyle = "rgba(197, 59, 50, 0.07)";
      ctx.fillRect(x(index) - bandWidth / 2, pad.top, bandWidth, height - pad.top - pad.bottom);
    });
  }

  const tickCount = Math.round(yMax / step);
  for (let i = 0; i <= tickCount; i += 1) {
    const value = Number((i * step).toFixed(10));
    const py = y(value);
    ctx.strokeStyle = "#e5e9f0";
    ctx.beginPath();
    ctx.moveTo(pad.left, py);
    ctx.lineTo(width - pad.right, py);
    ctx.stroke();
    ctx.fillStyle = "#667085";
    ctx.fillText(value.toFixed(2), 8, py + 4);
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
      const value = numericValue(row[item.key]);
      if (value === null) return;
      if (!started) {
        ctx.moveTo(x(index), y(value));
        started = true;
      } else {
        ctx.lineTo(x(index), y(value));
      }
    });
    ctx.stroke();
    rows.forEach((row, index) => {
      const value = numericValue(row[item.key]);
      if (value === null) return;
      ctx.beginPath();
      ctx.arc(x(index), y(value), item.radius || 4, 0, Math.PI * 2);
      ctx.fill();
      if (options.showPointLabels) {
        const label = value.toFixed(item.labelDigits ?? 3);
        ctx.save();
        ctx.font = "700 9px Inter, Segoe UI, sans-serif";
        ctx.fillStyle = item.color;
        const yOffset = item.labelOffset ?? -10;
        ctx.fillText(label, x(index) - ctx.measureText(label).width / 2, y(value) + yOffset);
        ctx.restore();
      }
    });
  });

  ctx.fillStyle = "#667085";
  rows.forEach((row, index) => {
    const labelEvery = options.labelEvery || (rows.length > 16 ? 3 : 2);
    if (rows.length > 8 && index % labelEvery !== 0 && index !== rows.length - 1) return;
    const label = options.fullMonthLabels ? chartMonthLabel(row.snapshot_date) : monthLabel(row.snapshot_date);
    ctx.fillText(label, x(index) - 18, height - 12);
  });
}

function drawBarChart(canvas, rows, significantCutoff) {
  const { ctx, width, height } = resizeCanvas(canvas, 285);
  const pad = { left: 120, right: 20, top: 14, bottom: 24 };
  const topRows = rows.slice(0, 10);
  const cutoff = numericValue(significantCutoff);
  const max = Math.max(cutoff || 0, ...topRows.map((row) => numericValue(row.csi) || 0));
  const barGap = 8;
  const barHeight = Math.max(14, (height - pad.top - pad.bottom) / topRows.length - barGap);

  ctx.clearRect(0, 0, width, height);
  ctx.font = "11px Inter, Segoe UI, sans-serif";
  topRows.forEach((row, index) => {
    const value = numericValue(row.csi) || 0;
    const y = pad.top + index * (barHeight + barGap);
    const barWidth = ((width - pad.left - pad.right) * value) / max;
    ctx.fillStyle = "#344054";
    ctx.fillText(String(row.feature_name).slice(0, 18), 8, y + barHeight - 3);
    ctx.fillStyle = cutoff !== null && value > cutoff ? "#c53b32" : "#b7791f";
    ctx.fillRect(pad.left, y, barWidth, barHeight);
    ctx.fillStyle = "#172033";
    ctx.fillText(value.toFixed(3), pad.left + barWidth + 6, y + barHeight - 3);
  });
}

function renderAlerts(summary, thresholds) {
  const watchCutoff = numericValue(thresholds?.stable_upper);
  const significantCutoff = numericValue(thresholds?.watch_upper);
  const rows = [
    [
      `PSI > ${fmt(significantCutoff, 2)}`,
      significantCutoff !== null && summary.psi > significantCutoff ? "Triggered" : "Not triggered",
      significantCutoff !== null && summary.psi > significantCutoff ? "alert" : "stable",
    ],
    [
      `PSI watch > ${fmt(watchCutoff, 2)}`,
      watchCutoff !== null && summary.psi > watchCutoff ? "Triggered" : "Not triggered",
      watchCutoff !== null && summary.psi > watchCutoff ? "watch" : "stable",
    ],
    [
      `CSI > ${fmt(significantCutoff, 2)}`,
      `${summary.significant_feature_count || 0} features`,
      (summary.significant_feature_count || 0) > 0 ? "alert" : "stable",
    ],
    [
      "Performance drift",
      summary.performance_drift_status === "stable" ? "Not detected" : normalizeStatus(summary.performance_drift_status),
      summary.performance_drift_status === "stable" ? "stable" : "watch",
    ],
    ["Retraining trigger", "Not met", "stable"],
    ["Action", "Investigate data drift", "watch"],
  ];

  const host = document.querySelector("#alertRows");
  host.replaceChildren();
  rows.forEach(([label, value, tone]) => {
    const item = document.createElement("div");
    item.className = `alert-row ${tone}`;
    item.innerHTML = `<span>${label}</span><strong>${value}</strong>`;
    host.appendChild(item);
  });
}

function renderConfusionMatrix(matrix) {
  const cm = matrix || {};
  setText("matrixTn", cm.available ? Number(cm.tn || 0).toLocaleString() : "-");
  setText("matrixFp", cm.available ? Number(cm.fp || 0).toLocaleString() : "-");
  setText("matrixFn", cm.available ? Number(cm.fn || 0).toLocaleString() : "-");
  setText("matrixTp", cm.available ? Number(cm.tp || 0).toLocaleString() : "-");
  setText("matrixThreshold", fmt(cm.threshold, 2));
  setText("matrixPrecision", fmt(cm.precision));
  setText("matrixRecall", fmt(cm.recall));
  setText("matrixF1", fmt(cm.f1_score));
  setText("matrixPredRate", pct(cm.predicted_default_rate));
  setText("matrixObsRate", pct(cm.observed_default_rate));
}

function render(payload) {
  if (!payload.ready) {
    cachedPayload = null;
    dashboard.hidden = true;
    emptyState.hidden = false;
    emptyState.textContent = payload.message;
    return;
  }

  cachedPayload = payload;
  dashboard.hidden = false;
  emptyState.hidden = true;

  if (!monthSelect.options.length) {
    payload.months.forEach((month) => {
      const option = document.createElement("option");
      option.value = month;
      option.textContent = monthLabel(month);
      monthSelect.appendChild(option);
    });
  }
  monthSelect.value = payload.selected_month;

  const s = payload.summary;
  const thresholds = payload.thresholds || {};
  const stableCutoff = numericValue(thresholds.stable_upper);
  const significantCutoff = numericValue(thresholds.watch_upper);
  const metrics = selectedChampionMetrics(payload);
  const featureAlert = (s.significant_feature_count || 0) > 0;
  const populationWatch =
    s.data_drift_status === "watch" ||
    (stableCutoff !== null && (s.psi || 0) > stableCutoff);
  const populationAlert =
    s.data_drift_status === "significant_drift" ||
    (significantCutoff !== null && (s.psi || 0) > significantCutoff);
  const performanceStable = s.performance_drift_status === "stable";
  const action = performanceStable && (populationAlert || populationWatch || featureAlert)
    ? "Investigate data drift; retraining trigger not met"
    : performanceStable
      ? "Continue Monitoring"
      : "Escalate Performance Review";
  let decisionTitle = "Model operating within expected range.";
  if (!performanceStable) {
    decisionTitle = "Performance review required.";
  } else if (populationAlert || populationWatch || featureAlert) {
    decisionTitle = "Performance stable, but data drift requires investigation.";
  }

  setText("selectedMonthLabel", monthLabel(payload.selected_month));
  setText("lastUpdated", `Last updated: ${new Date().toLocaleString()}`);
  setText("decisionTitle", decisionTitle);
  setText("candidateCount", `${Number(payload.registry?.candidate_count || 0).toLocaleString()} Candidates`);
  setText("p0Gate", "P0 Gate");
  setText("sideOotWindow", payload.period_summary?.oot_window || "-");
  setText("developmentPeriod", compactDevelopmentLabel(payload));
  setText("ootWindow", compactOotLabel(payload));
  setText("matrixMonthLabel", payload.period_summary?.selected_month_label || monthLabel(payload.selected_month));
  setText("psiWatchLabel", `${fmt(stableCutoff, 2)} watch`);
  setText("psiAlertLabel", `${fmt(significantCutoff, 2)} significant`);
  setText("csiAlertLabel", `CSI > ${fmt(significantCutoff, 2)}`);
  setText("sideModelName", s.model_name ? displayRawModelName(s.model_name) : "-");
  setText("sideModelVersion", s.model_version || "-");
  setText("modelName", s.model_name ? displayRawModelName(s.model_name) : "-");
  setText("modelVersion", s.model_version || "-");
  setText("labelStatus", normalizeStatus(s.observation_status));
  setText("decisionPerformance", performanceStable ? "Stable" : normalizeStatus(s.performance_drift_status));
  setText("decisionPopulation", populationAlert ? "Significant" : populationWatch ? "Watch" : "Stable");
  let driftAlertText = "No significant feature drift";
  if (populationAlert && featureAlert) {
    driftAlertText = "Significant PSI/CSI detected";
  } else if (populationAlert) {
    driftAlertText = "Significant PSI detected";
  } else if (featureAlert) {
    driftAlertText = "Significant CSI detected";
  }
  setText("decisionFeature", driftAlertText);
  setText("decisionAction", action);

  ["decisionPerformance", "decisionPopulation", "decisionFeature", "decisionAction"].forEach((id) => {
    const node = document.querySelector(`#${id}`);
    node.className = "";
    if (id === "decisionPerformance") node.classList.add(performanceStable ? "text-stable" : "text-alert");
    if (id === "decisionPopulation") node.classList.add(populationAlert ? "text-alert" : populationWatch ? "text-watch" : "text-stable");
    if (id === "decisionFeature") node.classList.add(featureAlert ? "text-alert" : "text-stable");
    if (id === "decisionAction") node.classList.add("text-watch");
  });

  setText("valRecall", fmt(metrics.validation_recall));
  setText("valPrauc", fmt(metrics.validation_pr_auc));
  setText("govScore", fmt(metrics.governance_score));
  setText("testRecall", fmt(metrics.test_recall));
  setText("testPrauc", fmt(metrics.test_pr_auc));

  setText("p0Value", fmt(s.p0_value));
  setText("p1Value", fmt(s.p1_value));
  setText("psiValue", fmt(s.psi));
  setText("predictionCount", Number(s.prediction_count || 0).toLocaleString());
  setText("predictedRate", pct(s.predicted_default_rate));
  setText("observedRate", pct(s.observed_default_rate));
  setText(
    "psiInterpretation",
    stableCutoff === null || significantCutoff === null
      ? "-"
      : s.psi < stableCutoff
        ? `Stable: below ${fmt(stableCutoff, 2)}`
        : s.psi <= significantCutoff
          ? `Watch: ${fmt(stableCutoff, 2)}-${fmt(significantCutoff, 2)}`
          : `Significant: above ${fmt(significantCutoff, 2)}`
  );

  const deployedRows = (payload.performance || []).filter(isDeployedMonitoringRow);
  const monitoredRows = deployedRows.length ? deployedRows : (payload.performance || []).filter(isOotOrHoldout);
  const psiThresholds = [
    stableCutoff !== null ? { value: stableCutoff, color: "#b7791f" } : null,
    significantCutoff !== null ? { value: significantCutoff, color: "#c53b32" } : null,
  ].filter(Boolean);

  drawLineChart(
    document.querySelector("#psiChart"),
    monitoredRows,
    [{ key: "psi", color: "#b7791f" }],
    {
      tickStep: 0.1,
      thresholds: psiThresholds,
      highlightKey: "psi",
      highlightAbove: significantCutoff,
      deploymentMarker: "2024-01-01",
      deploymentLabel: "Jan 2024",
      shadeFromDeployment: true,
      labelEvery: 1,
      fullMonthLabels: true,
      showPointLabels: true,
    }
  );
  drawLineChart(
    document.querySelector("#performanceChart"),
    monitoredRows,
    [
      { key: "p0_metric_value", color: "#2764c4" },
      { key: "p1_metric_value", color: "#25835b" },
      { key: "precision", color: "#6941c6", radius: 3 },
    ],
    {
      tickStep: 0.25,
      yMax: 1,
      thresholds: numericValue(payload.p0_minimum) !== null
        ? [{ value: numericValue(payload.p0_minimum), color: "#c53b32" }]
        : [],
      deploymentMarker: "2024-01-01",
      deploymentLabel: "Jan 2024",
      labelEvery: 1,
      fullMonthLabels: true,
      showPointLabels: true,
    }
  );
  drawBarChart(document.querySelector("#csiChart"), payload.drift || [], significantCutoff);

  renderConfusionMatrix(payload.confusion_matrix);
  renderAlerts(s, thresholds);

  const tbody = document.querySelector("#leaderboardRows");
  tbody.replaceChildren();
  leaderboardRows(payload).forEach(([name, recall, prAuc, governance]) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${name}</td>
      <td>${fmt(recall)}</td>
      <td>${fmt(prAuc)}</td>
      <td>${fmt(governance)}</td>
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
document.querySelectorAll("nav a[href^='#']").forEach((link) => {
  link.addEventListener("click", () => {
    document.querySelectorAll("nav a").forEach((item) => item.classList.remove("active"));
    link.classList.add("active");
  });
});
window.addEventListener("resize", () => {
  if (cachedPayload) render(cachedPayload);
});
load();
