// Build Runner — minimal frontend logic
// No frameworks. Talks to existing /build, /status, /logs (WS), /history endpoints.

const API_KEY = "";  // empty -> server allows (dev mode in _check_api_key)
let activeJobId = null;
let activeWebSocket = null;

// ---------- helpers ----------
function $(id) { return document.getElementById(id); }

function statusClass(status) {
  return `badge badge-${status || "queued"}`;
}

function shortJobId(id) {
  return id ? id.split("-")[0] : "";
}

function repoName(url) {
  if (!url) return "(no repo)";
  try {
    const u = new URL(url);
    return u.pathname.replace(/^\//, "").replace(/\.git$/, "");
  } catch { return url; }
}

async function api(path, opts = {}) {
  const headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
  if (API_KEY) headers["X-API-Key"] = API_KEY;
  const res = await fetch(path, { ...opts, headers });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${txt}`);
  }
  return res.json();
}

// ---------- build submission ----------
$("build-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const url = $("repo-url").value.trim();
  if (!url) return;

  const btn = $("submit-btn");
  btn.disabled = true;
  btn.textContent = "⏳ Submitting…";

  try {
    const data = await api(`/build?github_url=${encodeURIComponent(url)}`, {
      method: "POST",
    });
    activeJobId = data.job_id;
    showActiveCard(data.job_id, url);
    openLogSocket(data.job_id);
    $("repo-url").value = "";
    refreshHistory();
  } catch (err) {
    alert(`Build failed to start: ${err.message}`);
  } finally {
    btn.disabled = false;
    btn.textContent = "⚡ Trigger Build";
  }
});

// ---------- active build card ----------
function showActiveCard(jobId, url) {
  $("active-card").hidden = false;
  $("active-job").textContent = shortJobId(jobId);
  $("active-repo").textContent = repoName(url);
  $("active-status").textContent = "queued";
  $("active-status").className = statusClass("queued");
  $("active-message").textContent = "Job submitted, waiting for worker…";
  $("log-box").textContent = "";
}

function updateActiveStatus(job) {
  $("active-status").textContent = job.status;
  $("active-status").className = statusClass(job.status);
  $("active-message").textContent = job.message || "(no message)";
  if (job.image_tag) {
    $("active-message").textContent += `  [${job.image_tag}]`;
  }
}

function appendLog(line) {
  const box = $("log-box");
  const span = document.createElement("span");
  span.className = "line";
  if (/error|fail|fatal/i.test(line)) span.classList.add("err");
  else if (/success|✓|✅/i.test(line)) span.classList.add("ok");
  span.textContent = line + "\n";
  box.appendChild(span);
  box.scrollTop = box.scrollHeight;  // auto-scroll
}

// ---------- websocket for live logs ----------
function openLogSocket(jobId) {
  if (activeWebSocket) {
    try { activeWebSocket.close(); } catch {}
  }
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/logs/${jobId}`);
  activeWebSocket = ws;

  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      if (msg.type === "status") {
        updateActiveStatus(msg);
        if (["success", "failed"].includes(msg.status)) {
          refreshHistory();
        }
      } else if (msg.type === "log") {
        appendLog(msg.line);
      }
    } catch (e) {
      appendLog(`[parse error] ${ev.data}`);
    }
  };
  ws.onerror = () => appendLog("[websocket error]");
  ws.onclose = () => appendLog("[websocket closed]");
}

// ---------- history ----------
async function refreshHistory() {
  try {
    const data = await api("/history");
    const list = $("history-list");
    if (!data.jobs || data.jobs.length === 0) {
      list.innerHTML = '<p class="empty">No builds yet — trigger one above ↑</p>';
      return;
    }
    list.innerHTML = "";
    for (const job of data.jobs) {
      const item = document.createElement("div");
      item.className = "history-item";
      item.innerHTML = `
        <div>
          <div class="repo">${repoName(job.github_url)}</div>
          <div class="job">${shortJobId(job.job_id)} • ${new Date().toISOString().slice(0,16)}Z</div>
        </div>
        <span class="${statusClass(job.status)}">${job.status}</span>
      `;
      item.addEventListener("click", () => {
        activeJobId = job.job_id;
        showActiveCard(job.job_id, job.github_url);
        updateActiveStatus(job);
        openLogSocket(job.job_id);
        $("active-card").scrollIntoView({ behavior: "smooth" });
      });
      list.appendChild(item);
    }
  } catch (err) {
    console.error("history load failed:", err);
  }
}

$("refresh-btn").addEventListener("click", refreshHistory);

// auto-refresh history every 5s so past builds show up while polling
setInterval(refreshHistory, 5000);
refreshHistory();
