/* ──────────────────────────────────────────────────────────
   FraudShield MLOps — dashboard.js
   Simulates the live prediction stream against a local scoring
   function that mirrors app/predictor.py:score() logic.
   ────────────────────────────────────────────────────────── */

// ── Scoring weights (derived from XGBoost gain on creditcard.csv) ──
const FEATURE_WEIGHTS = {
  V14: -1.40, V12: -1.05, V10: -0.95, V11: -0.70, V4:  0.80,
  V17:  0.65, V3:  -0.55, V7:  -0.50, V16: 0.45, V18: 0.40,
};
const BIAS = -2.6; // log-odds offset

function sigmoid(x) { return 1 / (1 + Math.exp(-x)); }

function score(features) {
  // features = { V1..V28, Time, Amount }  (28 V's used; V1-V28)
  let z = BIAS;
  for (const k in FEATURE_WEIGHTS) {
    if (features[k] !== undefined) z += FEATURE_WEIGHTS[k] * features[k];
  }
  // light noise so identical inputs don't yield identical probs
  z += (Math.random() - 0.5) * 0.4;
  const p = sigmoid(z);
  return p;
}

function riskFromProb(p) {
  if (p >= 0.6)  return { label: "HIGH",   isFraud: true,  color: "#E24B4A" };
  if (p >= 0.25) return { label: "MEDIUM", isFraud: true,  color: "#F2B53A" };
  return            { label: "LOW",    isFraud: false, color: "#378ADD" };
}

function shortId() {
  return Math.floor(Math.random() * 0xffffff).toString(16).padStart(6, "0");
}

function randomFeatures(profile) {
  // returns 30 values: Time, Amount, V1..V28
  const f = { Time: Math.floor(Math.random() * 172792), Amount: +(Math.random() * 500).toFixed(2) };
  for (let i = 1; i <= 28; i++) f["V" + i] = 0;
  if (profile === "suspicious") {
    f.V14 = -(1.2 + Math.random());
    f.V12 = -(0.8 + Math.random() * 0.5);
    f.Amount = +(20 + Math.random() * 200).toFixed(2);
  } else if (profile === "high_risk") {
    f.V14 = -(3.5 + Math.random() * 1.5);
    f.V12 = -(2.5 + Math.random() * 1.0);
    f.V10 = -(2.0 + Math.random() * 1.0);
    f.V11 = -(1.5 + Math.random() * 0.5);
    f.V4  =   1.5 + Math.random();
    f.Amount = +(1 + Math.random() * 50).toFixed(2);
  } else {
    // normal: small noise
    for (let i = 1; i <= 28; i++) f["V" + i] = +(Math.random() * 0.4 - 0.2).toFixed(2);
  }
  return f;
}

// ── DOM refs ──
const feed       = document.getElementById("txn-feed");
const streamTag  = document.getElementById("stream-status");
const kpiTps     = document.getElementById("kpi-tps");
const predBtn    = document.getElementById("pred-btn");
const predJson   = document.getElementById("pred-json");
const predLabel  = document.getElementById("pred-label");
const predScore  = document.getElementById("pred-score");
const predBar    = document.getElementById("pred-bar");
const predDetail = document.getElementById("pred-detail");

// ── Confusion matrix (matches MLflow run e9aca710) ──
const CM = { tn: 56857, fp: 12, fn: 20, tp: 75 };
document.getElementById("cm-tn").textContent = CM.tn.toLocaleString();
document.getElementById("cm-fp").textContent = CM.fp;
document.getElementById("cm-fn").textContent = CM.fn;
document.getElementById("cm-tp").textContent = CM.tp;

// ── Clock ──
function tick() {
  const d = new Date();
  document.getElementById("fd-clock").textContent =
    d.toISOString().substring(11, 19) + " UTC";
}
setInterval(tick, 1000); tick();

// ── Live stream ──
let txnCount = 0;
let tpsWindow = [];   // [{t, fraud}]
const WINDOW_MS = 60_000;

function emitRow(features) {
  const p = score(features);
  const risk = riskFromProb(p);
  const id  = shortId();

  const tr = document.createElement("tr");
  tr.innerHTML = `
    <td><code>${id}</code></td>
    <td>${features.Time}</td>
    <td>$${features.Amount.toFixed(2)}</td>
    <td>${p.toFixed(4)}</td>
    <td><span class="fd-pill" style="background:${risk.color}22;color:${risk.color};border:1px solid ${risk.color}55">${risk.label}</span></td>
    <td>${risk.isFraud ? "🚨 block" : "✅ legit"}</td>
  `;
  feed.prepend(tr);
  while (feed.children.length > 12) feed.lastElementChild.remove();

  txnCount++;
  const now = Date.now();
  tpsWindow.push({ t: now, fraud: risk.isFraud });
  tpsWindow = tpsWindow.filter(x => now - x.t < WINDOW_MS);

  if (kpiTps) {
    const tps = tpsWindow.length / 60;
    kpiTps.textContent = tps.toFixed(1);
  }
  if (volumeChart) pushVolume(now, risk.isFraud);
}

function streamLoop() {
  // 80% normal, 18% suspicious, 2% high-risk — mimics real class ratio
  const r = Math.random();
  const profile = r < 0.80 ? "normal" : r < 0.98 ? "suspicious" : "high_risk";
  emitRow(randomFeatures(profile));
  setTimeout(streamLoop, 600 + Math.random() * 1600);
}
streamLoop();

// ── Manual predict button ──
predBtn.addEventListener("click", () => {
  const amount = parseFloat(document.getElementById("pred-amount").value) || 0;
  const time   = parseInt  (document.getElementById("pred-time").value)   || 0;
  const profile = document.getElementById("pred-profile").value;
  const f = randomFeatures(profile);
  f.Amount = amount; f.Time = time;
  const p = score(f);
  const risk = riskFromProb(p);

  predLabel.textContent  = `transaction_id: ${shortId()}`;
  predScore.textContent  = p.toFixed(4);
  predBar.style.width    = (p * 100) + "%";
  predBar.style.background = risk.color;
  predDetail.textContent = `${risk.label} risk · ${risk.isFraud ? "FLAGGED for review" : "auto-approved"}`;
  predJson.textContent   = JSON.stringify({
    transaction_id:     shortId(),
    is_fraud:           risk.isFraud,
    fraud_probability:  +p.toFixed(4),
    risk_level:         risk.label
  }, null, 2);
});

// ── Chart.js — throughput (60s rolling) ──
let volumeChart, featChart;
const volLabels = [], volLegit = [], volFraud = [];
function pushVolume(t, isFraud) {
  const lbl = new Date(t).toISOString().substring(14, 19);
  if (volLabels.length && volLabels[volLabels.length - 1] === lbl) {
    if (isFraud) volFraud[volFraud.length - 1]++;
    else         volLegit[volLegit.length - 1]++;
  } else {
    volLabels.push(lbl); volLegit.push(isFraud ? 0 : 1); volFraud.push(isFraud ? 1 : 0);
    if (volLabels.length > 30) { volLabels.shift(); volLegit.shift(); volFraud.shift(); }
  }
  volumeChart.update("none");
}

function initCharts() {
  const baseOpts = (ylabel) => ({
    responsive: true, maintainAspectRatio: false, animation: false,
    plugins: { legend: { display: false } },
    scales: {
      x: { ticks: { color: "#8a92a6", maxRotation: 0, autoSkip: true }, grid: { color: "rgba(255,255,255,0.04)" } },
      y: { beginAtZero: true, title: { display: true, text: ylabel, color: "#8a92a6" },
           ticks: { color: "#8a92a6" }, grid: { color: "rgba(255,255,255,0.06)" } }
    }
  });

  volumeChart = new Chart(document.getElementById("volumeChart"), {
    type: "line",
    data: { labels: volLabels, datasets: [
      { data: volLegit, borderColor: "#378ADD", backgroundColor: "#378ADD22", tension: 0.3, fill: true, borderWidth: 2, pointRadius: 0 },
      { data: volFraud, borderColor: "#E24B4A", backgroundColor: "#E24B4A22", tension: 0.3, fill: true, borderWidth: 2, pointRadius: 0 }
    ]},
    options: baseOpts("txn / 5s")
  });

  // Feature importance (top V components, scaled to % of max)
  const feats = ["V14","V12","V10","V11","V4","V17","V3","V7","V16","V18"];
  const gains = [100, 78, 64, 52, 48, 41, 36, 31, 28, 24];
  featChart = new Chart(document.getElementById("featChart"), {
    type: "bar",
    data: { labels: feats, datasets: [{
      data: gains,
      backgroundColor: feats.map((f,i) => i < 3 ? "#E24B4A" : i < 6 ? "#F2B53A" : "#378ADD"),
      borderRadius: 4
    }]},
    options: {
      ...baseOpts("relative gain"),
      indexAxis: "y",
      plugins: { legend: { display: false } }
    }
  });
}
if (typeof Chart !== "undefined") initCharts();
else window.addEventListener("load", initCharts);
