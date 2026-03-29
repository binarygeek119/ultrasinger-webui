const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];

const views = {
  home: $("#view-home"),
  jobs: $("#view-jobs"),
  downloads: $("#view-downloads"),
  settings: $("#view-settings"),
  about: $("#view-about"),
};

const OPTIONS_STORAGE_KEY = "ultrasinger_webui_processing_v1";
const WELCOME_DONE_KEY = "ultrasinger_webui_onboarding_done";
const WELCOME_ABOUT_SESSION_KEY = "ultrasinger_webui_onboarding_about_session";

function loadProcessingOptions() {
  try {
    const raw = localStorage.getItem(OPTIONS_STORAGE_KEY);
    if (!raw) return;
    const o = JSON.parse(raw);
    const w = $("#opt-whisper");
    const a = $("#opt-audio");
    const y = $("#opt-yarg");
    const d = $("#opt-delwf");
    if (!w || !a || !y || !d) return;
    if (o.whisper_compute_type) w.value = o.whisper_compute_type;
    if (o.output_audio_format) a.value = o.output_audio_format;
    if (typeof o.yarg_compatible === "boolean") y.checked = o.yarg_compatible;
    if (typeof o.delete_workfiles === "boolean") d.checked = o.delete_workfiles;
  } catch {
    /* ignore */
  }
}

function saveProcessingOptions() {
  try {
    localStorage.setItem(OPTIONS_STORAGE_KEY, JSON.stringify(optionsFromForm()));
  } catch {
    /* ignore */
  }
}

function bindProcessingOptionsPersistence() {
  ["#opt-whisper", "#opt-audio"].forEach((sel) => {
    const el = $(sel);
    if (el) el.addEventListener("change", saveProcessingOptions);
  });
  ["#opt-yarg", "#opt-delwf"].forEach((sel) => {
    const el = $(sel);
    if (el) el.addEventListener("change", saveProcessingOptions);
  });
}

function _setFolderResolved(el, resolved, writable, label) {
  if (!el) return;
  if (!resolved) {
    el.textContent = "";
    return;
  }
  const w = writable ? "" : " (not writable — check permissions)";
  el.textContent = `Resolved ${label}: ${resolved}${w}`;
  el.className = writable ? "muted" : "settings-path-bad";
  el.style.fontSize = "0.78rem";
  el.style.margin = "0.25rem 0 0.65rem";
}

async function loadServerSettings() {
  const pathInput = $("#srv-ultrasinger-path");
  const lockMsg = $("#srv-ultrasinger-env-lock");
  const statusEl = $("#srv-ultrasinger-status");
  const outIn = $("#srv-output-folder");
  const upIn = $("#srv-upload-folder");
  const foldersWarn = $("#srv-folders-warn");
  if (!pathInput || !statusEl) return;
  try {
    const d = await api("GET", "/api/settings");
    pathInput.value = d.ultrasinger_py_input || "";
    if (outIn) outIn.value = d.output_folder_input || "";
    if (upIn) upIn.value = d.upload_folder_input || "";

    const locked = d.ultrasinger_py_locked_by_env;
    pathInput.readOnly = locked;
    pathInput.classList.toggle("input-locked", locked);
    if (lockMsg) {
      lockMsg.classList.toggle("hidden", !locked);
      if (locked) {
        lockMsg.textContent =
          "ULTRASINGER_PY is set in the server environment; it overrides the UltraSinger.py field above. You can still change folders below.";
      }
    }
    if (locked) {
      statusEl.textContent = "Using UltraSinger path from ULTRASINGER_PY.";
      statusEl.className = "muted";
      statusEl.style.margin = "0.35rem 0 0.5rem";
    } else if (d.ultrasinger_py) {
      statusEl.textContent = d.ultrasinger_py_is_file
        ? "Resolved path exists — ready to run jobs."
        : "Resolved path is not an existing file. Check the path.";
      statusEl.className = d.ultrasinger_py_is_file ? "settings-path-ok" : "settings-path-bad";
      statusEl.style.margin = "";
    } else {
      statusEl.textContent = "No UltraSinger path configured yet.";
      statusEl.className = "muted";
      statusEl.style.margin = "0.35rem 0 0.5rem";
    }

    _setFolderResolved($("#srv-output-folder-resolved"), d.output_folder_resolved, d.output_folder_writable, "output");
    _setFolderResolved($("#srv-upload-folder-resolved"), d.upload_folder_resolved, d.upload_folder_writable, "uploads");

    if (foldersWarn) {
      const bad = !d.output_folder_writable || !d.upload_folder_writable;
      foldersWarn.classList.toggle("hidden", !bad);
      if (bad) {
        foldersWarn.textContent =
          "One or more folders are missing or not writable. The server will try to create them when you save or run a job.";
      }
    }

    const cfgPathEl = $("#srv-webui-config-path");
    if (cfgPathEl && d.webui_config_file) {
      cfgPathEl.textContent = d.webui_config_exists
        ? `Settings file: ${d.webui_config_file}`
        : `Settings file (created on save): ${d.webui_config_file}`;
    }
  } catch (e) {
    statusEl.textContent = e.message;
    statusEl.className = "settings-path-bad";
  }
}

function welcomeAdvanceToPhase2() {
  const backdrop = $("#welcome-backdrop");
  const p1 = $("#welcome-panel-phase1");
  const p2 = $("#welcome-panel-phase2");
  if (!backdrop || !p1 || !p2) return;
  if (!p2.classList.contains("hidden")) return;
  try {
    sessionStorage.setItem(WELCOME_ABOUT_SESSION_KEY, "1");
  } catch {
    /* ignore */
  }
  p1.classList.add("hidden");
  p2.classList.remove("hidden");
  backdrop.classList.add("welcome-bar-mode");
}

function welcomeOnboardingAfterNav(name) {
  if (localStorage.getItem(WELCOME_DONE_KEY)) return;
  const backdrop = $("#welcome-backdrop");
  if (!backdrop || backdrop.classList.contains("hidden")) return;
  if (name !== "about") return;
  welcomeAdvanceToPhase2();
}

function showView(name) {
  const view = views[name];
  if (!view) return;
  Object.values(views).forEach((v) => {
    if (v) v.classList.add("hidden");
  });
  view.classList.remove("hidden");
  $$("nav button").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  if (name === "jobs") loadJobs();
  if (name === "downloads") loadDownloads();
  if (name === "settings") loadServerSettings();
  history.replaceState(null, "", `#${name}`);
  welcomeOnboardingAfterNav(name);
}

function initWelcomeOnboarding() {
  if (localStorage.getItem(WELCOME_DONE_KEY)) return;
  const backdrop = $("#welcome-backdrop");
  const openAbout = $("#welcome-open-about");
  const linkAbout = $("#welcome-link-about");
  const cont = $("#welcome-continue");
  const openSettings = $("#welcome-open-settings");
  if (!backdrop || !openAbout || !cont) return;

  const p1 = $("#welcome-panel-phase1");
  const p2 = $("#welcome-panel-phase2");
  p1?.classList.remove("hidden");
  p2?.classList.add("hidden");
  backdrop.classList.remove("welcome-bar-mode");

  const hash = (location.hash || "#home").slice(1);
  let sawAbout = false;
  try {
    sawAbout = sessionStorage.getItem(WELCOME_ABOUT_SESSION_KEY) === "1";
  } catch {
    /* ignore */
  }

  backdrop.classList.remove("hidden");

  if (hash === "about" || sawAbout) {
    welcomeAdvanceToPhase2();
  }

  openAbout.addEventListener("click", () => showView("about"));
  linkAbout?.addEventListener("click", (e) => {
    e.preventDefault();
    showView("about");
  });
  openSettings?.addEventListener("click", () => showView("settings"));
  cont.addEventListener("click", () => {
    try {
      localStorage.setItem(WELCOME_DONE_KEY, "1");
    } catch {
      /* ignore */
    }
    backdrop.classList.add("hidden");
    backdrop.classList.remove("welcome-bar-mode");
    $("#welcome-panel-phase1")?.classList.remove("hidden");
    $("#welcome-panel-phase2")?.classList.add("hidden");
  });

  backdrop.addEventListener("click", (e) => {
    if (e.target !== backdrop) return;
    if (backdrop.classList.contains("welcome-bar-mode")) return;
    e.preventDefault();
    e.stopPropagation();
  });

  document.addEventListener(
    "keydown",
    (e) => {
      if (e.key !== "Escape") return;
      if (localStorage.getItem(WELCOME_DONE_KEY)) return;
      const b = $("#welcome-backdrop");
      if (!b || b.classList.contains("hidden")) return;
      e.preventDefault();
      e.stopPropagation();
    },
    true,
  );
}

function toast(msg) {
  const t = document.createElement("div");
  t.className = "toast";
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 4500);
}

function optionsFromForm() {
  return {
    whisper_compute_type: $("#opt-whisper").value,
    output_audio_format: $("#opt-audio").value,
    yarg_compatible: $("#opt-yarg").checked,
    delete_workfiles: $("#opt-delwf").checked,
  };
}

async function api(method, url, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const r = await fetch(url, opts);
  const text = await r.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { detail: text };
  }
  if (!r.ok) {
    const d = data?.detail;
    const msg = typeof d === "string" ? d : Array.isArray(d) ? d.map((x) => x.msg).join("; ") : r.statusText;
    throw new Error(msg || "Request failed");
  }
  return data;
}

async function checkHealth() {
  try {
    const h = await api("GET", "/api/health");
    const el = $("#health-banner");
    if (!h.ultrasinger_configured) {
      el.classList.remove("hidden");
      el.textContent =
        "UltraSinger is not configured: set the path under Settings, or set ULTRASINGER_PY on the server.";
    } else {
      el.classList.add("hidden");
    }
  } catch {
    /* ignore */
  }
}

const urlHintSingle = "One job per link.";
const urlHintPlaylist = "Requires yt-dlp on PATH. Each playlist entry becomes its own job.";

function syncUrlModeHint() {
  const playlist = $('input[name="url-mode"][value="playlist"]').checked;
  $("#url-mode-hint").textContent = playlist ? urlHintPlaylist : urlHintSingle;
}

$$('input[name="url-mode"]').forEach((r) => r.addEventListener("change", syncUrlModeHint));
syncUrlModeHint();

$("#form-url").addEventListener("submit", async (e) => {
  e.preventDefault();
  const url = $("#url-input").value.trim();
  if (!url) return toast("Enter a URL");
  const playlist = $('input[name="url-mode"][value="playlist"]').checked;
  const opts = optionsFromForm();
  try {
    if (playlist) {
      const data = await api("POST", "/api/jobs/playlist", { playlist_url: url, options: opts });
      toast(`Queued ${data.count} job(s)`);
    } else {
      const data = await api("POST", "/api/jobs/url", { url, options: opts });
      toast(`Job queued: ${data.job.id}`);
    }
    $("#url-input").value = "";
    showView("jobs");
  } catch (err) {
    toast(err.message);
  }
});

$("#form-upload").addEventListener("submit", async (e) => {
  e.preventDefault();
  const file = $("#file-audio").files[0];
  if (!file) return toast("Choose a file");
  const fd = new FormData();
  fd.append("file", file);
  fd.append("whisper_compute_type", $("#opt-whisper").value);
  fd.append("output_audio_format", $("#opt-audio").value);
  fd.append("yarg_compatible", $("#opt-yarg").checked ? "true" : "false");
  fd.append("delete_workfiles", $("#opt-delwf").checked ? "true" : "false");
  try {
    const r = await fetch("/api/jobs/upload", { method: "POST", body: fd });
    const text = await r.text();
    const data = JSON.parse(text);
    if (!r.ok) throw new Error(data.detail || r.statusText);
    toast(`Job queued: ${data.job.id}`);
    $("#file-audio").value = "";
    showView("jobs");
  } catch (err) {
    toast(err.message);
  }
});

function statusClass(s) {
  return `status ${s}`;
}

async function loadJobs() {
  const tbody = $("#jobs-tbody");
  tbody.innerHTML = `<tr><td colspan="5">Loading…</td></tr>`;
  try {
    const data = await api("GET", "/api/jobs");
    if (!data.jobs.length) {
      tbody.innerHTML = `<tr><td colspan="5" class="muted">No jobs yet.</td></tr>`;
      return;
    }
    tbody.innerHTML = "";
    for (const j of data.jobs) {
      const tr = document.createElement("tr");
      const src = j.input?.source || "";
      const short = src.length > 64 ? src.slice(0, 61) + "…" : src;
      tr.innerHTML = `
        <td class="mono">${j.id}</td>
        <td><span class="${statusClass(j.status)}">${j.status}</span></td>
        <td>${j.input?.type || ""}</td>
        <td class="mono" title="${src.replace(/"/g, "&quot;")}">${short}</td>
        <td>
          <button class="btn secondary" type="button" data-detail="${j.id}">Details</button>
          ${
            j.status === "failed"
              ? `<button class="btn secondary" type="button" data-retry="${j.id}">Retry</button>`
              : ""
          }
        </td>`;
      tbody.appendChild(tr);
    }
    tbody.querySelectorAll("[data-detail]").forEach((b) =>
      b.addEventListener("click", () => openDetail(b.getAttribute("data-detail")))
    );
    tbody.querySelectorAll("[data-retry]").forEach((b) =>
      b.addEventListener("click", () => retryJob(b.getAttribute("data-retry")))
    );
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="5">${err.message}</td></tr>`;
  }
}

async function retryJob(id) {
  try {
    const data = await api("POST", `/api/jobs/${id}/retry`);
    toast(`Retry queued: ${data.job.id}`);
    loadJobs();
  } catch (e) {
    toast(e.message);
  }
}

let jobsPoll = null;
function startJobsPoll() {
  if (jobsPoll) clearInterval(jobsPoll);
  jobsPoll = setInterval(() => {
    if (!$("#view-jobs").classList.contains("hidden")) loadJobs();
  }, 5000);
}

async function openDetail(id) {
  const backdrop = $("#modal-backdrop");
  const body = $("#modal-body");
  backdrop.classList.remove("hidden");
  body.innerHTML = "Loading…";
  try {
    const { job } = await api("GET", `/api/jobs/${id}`);
    const zip = job.output?.zip_name || "—";
    const canDl = job.status === "completed";
    body.innerHTML = `
      <h3>${job.id}</h3>
      <p><span class="${statusClass(job.status)}">${job.status}</span>
      ${job.retried_from ? ` <span class="muted">retry chain from ${job.retried_from}</span>` : ""}</p>
      <p><strong>Input</strong> (${job.input?.type}): <span class="mono">${job.input?.source || ""}</span></p>
      <p><strong>Options</strong>: whisper_compute_type=${job.options?.whisper_compute_type}, audio=${job.options?.output_audio_format},
      YARG=${job.options?.yarg_compatible}, delete_workfiles=${job.options?.delete_workfiles}</p>
      <p><strong>Package</strong>: ${zip}</p>
      ${job.error ? `<p class="mono" style="color:var(--err)">${job.error}</p>` : ""}
      <p>
        <a class="btn secondary" href="/api/jobs/${id}/log" target="_blank" rel="noopener">View log</a>
        ${
          canDl
            ? `<a class="btn" href="/api/jobs/${id}/download" download>Download ZIP</a>`
            : ""
        }
      </p>
      <pre class="log" id="inline-log"></pre>`;
    try {
      const logText = await fetch(`/api/jobs/${id}/log`).then((r) => (r.ok ? r.text() : ""));
      const pre = $("#inline-log");
      if (pre) pre.textContent = logText.slice(-12000) || "(empty log)";
    } catch {
      /* ignore */
    }
  } catch (e) {
    body.textContent = e.message;
  }
}

$("#modal-backdrop").addEventListener("click", (e) => {
  if (e.target.id === "modal-backdrop") $("#modal-backdrop").classList.add("hidden");
});
$("#modal-close").addEventListener("click", () => $("#modal-backdrop").classList.add("hidden"));

async function loadDownloads() {
  const tbody = $("#dl-tbody");
  tbody.innerHTML = "";
  try {
    const data = await api("GET", "/api/jobs");
    const done = data.jobs.filter((j) => j.status === "completed");
    if (!done.length) {
      tbody.innerHTML = `<tr><td colspan="3">No completed jobs.</td></tr>`;
      return;
    }
    for (const j of done) {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td class="mono">${j.id}</td>
        <td>${j.output?.zip_name || "—"}</td>
        <td><a class="btn secondary" href="/api/jobs/${j.id}/download">Download</a></td>`;
      tbody.appendChild(tr);
    }
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="3">${e.message}</td></tr>`;
  }
}

$("#btn-dl-all").addEventListener("click", async () => {
  const wrap = $("#bundle-area");
  wrap.classList.remove("hidden");
  $("#bundle-status").textContent = "Starting…";
  $("#bundle-dl").classList.add("hidden");
  try {
    const { bundle_id } = await api("POST", "/api/bundles/start", { job_ids: null });
    const poll = async () => {
      const st = await api("GET", `/api/bundles/${bundle_id}`);
      if (st.status === "failed") {
        $("#bundle-status").textContent = st.message || "Failed";
        return;
      }
      if (st.ready) {
        $("#bundle-status").textContent = "Ready.";
        const a = $("#bundle-dl");
        a.href = `/api/bundles/${bundle_id}/download`;
        a.download = st.filename || "download.zip";
        a.classList.remove("hidden");
        return;
      }
      $("#bundle-status").textContent = st.message || "Preparing download…";
      setTimeout(poll, 1500);
    };
    poll();
  } catch (e) {
    $("#bundle-status").textContent = e.message;
  }
});

$("#srv-server-save")?.addEventListener("click", async () => {
  const ultra = $("#srv-ultrasinger-path")?.value?.trim() || null;
  const outputFolder = $("#srv-output-folder")?.value?.trim() || null;
  const uploadFolder = $("#srv-upload-folder")?.value?.trim() || null;
  try {
    const d = await api("PUT", "/api/settings", {
      ultrasinger_py: ultra,
      output_folder: outputFolder,
      upload_folder: uploadFolder,
    });
    toast(
      d.webui_config_exists
        ? `Server settings saved to ${d.webui_config_file}`
        : "Server settings saved (no file — all paths cleared; defaults apply).",
    );
    await loadServerSettings();
    checkHealth();
  } catch (e) {
    toast(e.message);
  }
});

$$("nav button").forEach((b) =>
  b.addEventListener("click", () => showView(b.dataset.view))
);

window.addEventListener("hashchange", () => {
  const h = (location.hash || "#home").slice(1);
  if (views[h]) showView(h);
});

loadProcessingOptions();
bindProcessingOptionsPersistence();

const initial = (location.hash || "#home").slice(1);
showView(views[initial] ? initial : "home");
initWelcomeOnboarding();
checkHealth();
startJobsPoll();
