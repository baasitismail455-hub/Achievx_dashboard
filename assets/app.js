/* AchievX Admin Dashboard
   Flask API-backed organization control plane.
*/

const API_BASE = "/api";

let state = {
  user: null,
  org: null,
  workers: [],
  studies: [],
  invites: [],
  records: [],
  audit: [],
};

async function apiRequest(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    },
    ...options
  });

  let data = {};

  try {
    data = await response.json();
  } catch {
    data = {};
  }

  if (!response.ok) {
    const error = new Error(
      data.message ||
      data.error ||
      `Request failed with status ${response.status}`
    );

    error.status = response.status;
    error.data = data;

    throw error;
  }

  return data;
}

const $ = (id) => document.getElementById(id);
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;" }[c]));
const initials = (name) => (name || "A").split(/\s+/).slice(0,2).map(x => x[0]).join("").toUpperCase();
const formatDate = (v) => v ? new Intl.DateTimeFormat(undefined,{dateStyle:"medium"}).format(new Date(v)) : "—";
const formatDateTime = (v) => v ? new Intl.DateTimeFormat(undefined,{dateStyle:"medium",timeStyle:"short"}).format(new Date(v)) : "Never";
const relativeTime = (v) => {
  if (!v) return "Never";
  const diff = Date.now() - new Date(v).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs/24)}d ago`;
};

function setAlert(el, message, type="error") {
  el.textContent = message;
  el.className = `alert ${type}`;
}
function toast(message, type="success") {
  const el = $("toast");
  el.textContent = message;
  el.className = `toast ${type}`;
  setTimeout(() => el.classList.add("hidden"), 3000);
}
function showModal(html) {
  $("modalContent").innerHTML = html;
  $("modal").classList.remove("hidden");
}
function closeModal() { $("modal").classList.add("hidden"); }

async function initAuthPage() {
  try {
    const data = await apiRequest("/auth/me");

    if (data.authenticated) {
      window.location.href = "./dashboard.html";
      return;
    }
  } catch (e) {
    // Not authenticated is expected on the login page.
  }

  $("showRegister").onclick = () =>
    $("registerPanel").classList.remove("hidden");

  $("closeRegister").onclick = () =>
    $("registerPanel").classList.add("hidden");

  $("loginForm").onsubmit = async (event) => {
    event.preventDefault();

    const button = event.submitter;
    button.disabled = true;

    try {
      const email = $("loginEmail").value.trim();
      const password = $("loginPassword").value;

      await apiRequest("/auth/login", {
        method: "POST",
        body: JSON.stringify({
          email,
          password
        })
      });

      window.location.href = "./dashboard.html";

    } catch (e) {
      setAlert(
        $("authMessage"),
        e.message || "Unable to sign in."
      );
    } finally {
      button.disabled = false;
    }
  };

  $("registerForm").onsubmit = async (event) => {
    event.preventDefault();

    const button = event.submitter;
    button.disabled = true;

    try {
      const organizationName = $("orgName").value.trim();
      const adminName = $("adminName").value.trim();
      const email = $("adminEmail").value.trim();
      const password = $("adminPassword").value;

      if (password.length < 8) {
        throw new Error(
          "Use a password with at least 8 characters."
        );
      }

      const data = await apiRequest("/auth/register", {
        method: "POST",
        body: JSON.stringify({
          organization_name: organizationName,
          admin_name: adminName,
          email,
          password
        })
      });

      toast(
        `Organization ${data.organization.organization_code} created.`
      );

      window.location.href = "./dashboard.html";

    } catch (e) {
      setAlert(
        $("authMessage"),
        e.message || "Unable to create organization."
      );
    } finally {
      button.disabled = false;
    }
  };
}

async function requireUser() {
  try {
    const data = await apiRequest("/auth/me");

    if (!data.authenticated || !data.user) {
      window.location.href = "./index.html";
      return false;
    }

    state.user = data.user;
    return true;

  } catch (e) {
    window.location.href = "./index.html";
    return false;
  }
}

async function loadOrganization() {
  const data = await apiRequest("/organization");

  const org = data.organization;

  state.org = org;

  $("sidebarOrgName").textContent = org.organization_name;
  $("sidebarOrgCode").textContent = org.organization_code;
  $("orgAvatar").textContent = initials(org.organization_name);
  $("welcomeOrg").textContent = `${org.organization_name} at a glance.`;
  $("welcomeCode").textContent = org.organization_code;
  $("settingsOrgCode").textContent = org.organization_code;
  $("settingsOrgName").value = org.organization_name;
  $("settingsAdminName").value = org.admin_name || "";
  $("adminNameLabel").textContent =
    org.admin_name || state.user.email.split("@")[0];
  $("adminAvatar").textContent =
    initials(org.admin_name || state.user.email);
}


async function loadWorkers() {
  const data = await apiRequest("/workers");

  state.workers = data.workers || [];

  renderWorkers();
}


async function loadStudies() {
  const data = await apiRequest("/studies");

  state.studies = data.studies || [];

  renderStudies();
}


async function loadInvites() {
  const data = await apiRequest("/invitations");

  state.invites = data.invitations || [];

  renderInvites();
}


async function loadRecords() {
  const data = await apiRequest("/records");

  state.records = data.records || [];

  renderData();
}


async function loadAudit() {
  const data = await apiRequest("/audit");

  state.audit = data.audit || [];

  renderAudit();
}

async function refreshAll() {
  await Promise.all([loadOrganization(), loadWorkers(), loadStudies(), loadInvites(), loadRecords(), loadAudit()]);
  renderOverview();
}

function renderOverview() {
  const active = state.workers.filter(w => w.status === "active");
  const connected = state.workers.filter(w => w.status === "active" && w.last_sync_at);
  const pendingInvites = state.invites.filter(i => i.status === "pending" && new Date(i.expires_at) > new Date());
  $("statWorkers").textContent = active.length;
  $("statWorkerSub").textContent = `${state.workers.length} authorized device${state.workers.length === 1 ? "" : "s"}`;
  $("statRecords").textContent = state.records.length.toLocaleString();
  $("statRecordSub").textContent = state.records.length ? "Latest 500 records loaded" : "Waiting for synchronization";
  $("statStudies").textContent = state.studies.filter(s => s.status === "active").length;
  $("statInvites").textContent = pendingInvites.length;
  $("connectedCount").textContent = connected.length;
  $("offlineCount").textContent = Math.max(0, state.workers.length - connected.length);
  const pct = state.workers.length ? Math.round((connected.length / state.workers.length) * 100) : 0;
  $("syncPercent").textContent = state.workers.length ? `${pct}%` : "—";

  const activity = $("workerActivity");
  if (!state.workers.length) activity.innerHTML = `<div class="empty-state">No workers have been enrolled yet.</div>`;
  else activity.innerHTML = state.workers.slice(0,6).map(w => `
    <div class="activity-row">
      <div class="activity-avatar">${esc(initials(w.worker_label))}</div>
      <div class="activity-main"><strong>${esc(w.worker_label || "Unlabelled worker")}</strong><small>${esc(w.device_code)}</small></div>
      <span class="status-pill ${esc(w.status)}">${esc(w.status)}</span>
      <span class="activity-time">${relativeTime(w.last_sync_at)}</span>
    </div>`).join("");

  const studies = $("recentStudies");
  studies.innerHTML = state.studies.slice(0,4).map(s => `
    <div class="compact-row"><div><strong>${esc(s.study_name)}</strong><small>${esc(s.study_code)} · ${esc(s.status)}</small></div><span>${formatDate(s.created_at)}</span></div>`).join("") || `<div class="empty-state">No studies created yet.</div>`;

  const audit = $("recentAudit");
  audit.innerHTML = state.audit.slice(0,5).map(a => `
    <div class="compact-row"><div><strong>${esc(a.action)}</strong><small>${esc(a.details || "")}</small></div><span>${relativeTime(a.created_at)}</span></div>`).join("") || `<div class="empty-state">No events yet.</div>`;
}

function renderWorkers() {
  const query = ($("workerSearch")?.value || "").toLowerCase();
  const filter = $("workerStatusFilter")?.value || "all";
  const rows = state.workers.filter(w => {
    const matchesQuery = `${w.worker_label || ""} ${w.device_code || ""}`.toLowerCase().includes(query);
    return matchesQuery && (filter === "all" || w.status === filter);
  });
  $("workersTable").innerHTML = rows.map(w => `
    <tr>
      <td><div class="table-person"><div class="table-avatar">${esc(initials(w.worker_label))}</div><div><strong>${esc(w.worker_label || "Unlabelled")}</strong><small>Worker identity</small></div></div></td>
      <td><code>${esc(w.device_code)}</code></td>
      <td><span class="status-pill ${esc(w.status)}">${esc(w.status)}</span></td>
      <td>${esc(relativeTime(w.last_sync_at))}</td>
      <td>${esc(formatDate(w.created_at))}</td>
      <td><button class="table-action" onclick="window.AchievXAdmin.openDevice('${w.id}')">Manage</button></td>
    </tr>`).join("");
  $("workersEmpty").classList.toggle("hidden", rows.length !== 0);
}

function renderStudies() {
  $("studiesGrid").innerHTML = state.studies.map(s => `
    <article class="study-card">
      <div class="study-top"><span class="study-icon">▣</span><span class="status-pill ${esc(s.status)}">${esc(s.status)}</span></div>
      <span class="eyebrow">${esc(s.study_code)}</span><h3>${esc(s.study_name)}</h3><p>${esc(s.description || "No description provided.")}</p>
      <div class="study-foot"><span>Created ${esc(formatDate(s.created_at))}</span><button class="table-action" onclick="window.AchievXAdmin.openStudy('${s.id}')">Open</button></div>
    </article>`).join("");
  $("studiesEmpty").classList.toggle("hidden", state.studies.length !== 0);
}

function renderInvites() {
  const now = Date.now();
  const active = state.invites.filter(i => i.status === "pending" && new Date(i.expires_at).getTime() > now);
  $("invitesGrid").innerHTML = active.map(i => `
    <article class="invite-card">
      <div class="invite-card-top"><span class="status-pill pending">ACTIVE</span><span>${esc(relativeTime(i.created_at))}</span></div>
      <span class="eyebrow">DEVICE INVITATION</span>
      <h3>${esc(i.worker_label || "Worker")}</h3>
      <div class="invite-code">${esc(i.invitation_code)}</div>
      <div class="invite-meta"><span>Expires ${esc(formatDateTime(i.expires_at))}</span><button class="copy-btn" onclick="window.AchievXAdmin.copy('${esc(i.invitation_code)}')">Copy</button></div>
    </article>`).join("");
  $("invitesEmpty").classList.toggle("hidden", active.length !== 0);
}

function renderData() {
  const workerMap = Object.fromEntries(state.workers.map(w => [w.id,w]));
  const studyMap = Object.fromEntries(state.studies.map(s => [s.id,s]));
  const workerFilter = $("dataWorkerFilter")?.value || "";
  const studyFilter = $("dataStudyFilter")?.value || "";
  const locationFilter = ($("dataLocationFilter")?.value || "").toLowerCase();
  const from = $("dataFrom")?.value ? new Date($("dataFrom").value) : null;
  const to = $("dataTo")?.value ? new Date(`${$("dataTo").value}T23:59:59`) : null;

  const rows = state.records.filter(r => {
    const worker = workerMap[r.worker_id];
    const location = (r.location_label || "").toLowerCase();
    const d = new Date(r.collected_at || r.created_at);
    return (!workerFilter || r.worker_id === workerFilter) &&
      (!studyFilter || r.study_id === studyFilter) &&
      (!locationFilter || location.includes(locationFilter)) &&
      (!from || d >= from) && (!to || d <= to);
  });

  $("dataCount").textContent = `${rows.length.toLocaleString()} record${rows.length === 1 ? "" : "s"}`;
  $("dataTable").innerHTML = rows.map(r => {
    const worker = workerMap[r.worker_id];
    const study = studyMap[r.study_id];
    return `<tr><td><code>${esc(r.record_code || r.id.slice(0,8))}</code></td><td>${esc(worker?.worker_label || "—")}</td><td>${esc(study?.study_name || "—")}</td><td>${esc(formatDateTime(r.collected_at || r.created_at))}</td><td>${esc(r.location_label || "—")}</td><td><code>${esc(worker?.device_code || "—")}</code></td><td><details><summary>View</summary><pre>${esc(JSON.stringify(r.payload_json || {}, null, 2))}</pre></details></td></tr>`;
  }).join("");
  $("dataEmpty").classList.toggle("hidden", rows.length !== 0);
}

function renderAudit() {
  $("auditTable").innerHTML = state.audit.map(a => `<tr><td>${esc(formatDateTime(a.created_at))}</td><td><strong>${esc(a.action)}</strong></td><td>${esc(a.actor_name || "System")}</td><td>${esc(a.details || "—")}</td></tr>`).join("");
}

function fillDataFilters() {
  $("dataWorkerFilter").innerHTML = `<option value="">All workers</option>` + state.workers.map(w => `<option value="${w.id}">${esc(w.worker_label || w.device_code)}</option>`).join("");
  $("dataStudyFilter").innerHTML = `<option value="">All studies</option>` + state.studies.map(s => `<option value="${s.id}">${esc(s.study_name)}</option>`).join("");
}

async function createInvitation() {
  showModal(`
    <span class="eyebrow">DEVICE ENROLLMENT</span><h2>Create worker invitation</h2>
    <p class="modal-helper">This code expires in 30 minutes and can be used once.</p>
    <form id="inviteForm" class="modal-form">
      <label>Worker label<input id="inviteWorker" placeholder="Worker 01" required maxlength="80"></label>
      <label>Expiration<select id="inviteMinutes"><option value="30">30 minutes</option><option value="60">1 hour</option><option value="240">4 hours</option></select></label>
      <button class="btn btn-primary btn-block" type="submit">Generate invitation</button>
    </form>`);

  $("inviteForm").onsubmit = async (e) => {
    e.preventDefault();

    try {
      const data = await apiRequest("/invitations", {
        method: "POST",
        body: JSON.stringify({
          worker_label: $("inviteWorker").value.trim(),
          expires_minutes: Number($("inviteMinutes").value)
        })
      });

      closeModal();

      await loadInvites();
      renderOverview();

      showModal(`
        <span class="eyebrow">INVITATION READY</span>
        <h2>Send this code to the worker</h2>
        <div class="generated-code">${esc(data.invitation.invitation_code)}</div>
        <div class="code-details">
          <span>Organization</span>
          <strong>${esc(state.org.organization_name)}</strong>
          <span>Worker</span>
          <strong>${esc(data.invitation.worker_label)}</strong>
          <span>Expires</span>
          <strong>${esc(formatDateTime(data.invitation.expires_at))}</strong>
        </div>
        <button class="btn btn-primary btn-block"
          onclick="window.AchievXAdmin.copy('${esc(data.invitation.invitation_code)}');closeModal()">
          Copy invitation code
        </button>`);
    } catch (err) {
      console.error("CREATE INVITATION ERROR:", err);
      toast(err.message || "Could not create invitation.", "error");
    }
  };
}

async function createStudy() {
  showModal(`
    <span class="eyebrow">PROJECT MANAGEMENT</span>
    <h2>Create study</h2>

    <form id="studyForm" class="modal-form">
      <label>
        Study name
        <input
          id="studyName"
          placeholder="Malaria surveillance"
          required
          maxlength="160"
        >
      </label>

      <label>
        Description
        <textarea
          id="studyDescription"
          rows="4"
          placeholder="What is this project collecting?"
        ></textarea>
      </label>

      <button class="btn btn-primary btn-block" type="submit">
        Create study
      </button>
    </form>
  `);

  $("studyForm").onsubmit = async (e) => {
    e.preventDefault();

    const button = e.submitter;
    button.disabled = true;

    try {
      const data = await apiRequest("/studies", {
          method: "POST",
          body: JSON.stringify({
            study_name: $("studyName").value.trim(),
            description: $("studyDescription").value.trim() || null
          })
        });

      closeModal();

      await loadStudies();
      renderOverview();

      toast(`Study ${data.study.study_code} created.`);
    } catch (err) {
      console.error("CREATE STUDY ERROR:", err);
      toast(err.message || "Could not create study.", "error");
    } finally {
      button.disabled = false;
    }
  };
}

async function openDevice(id) {
  const w = state.workers.find(x => x.id === id);
  if (!w) return;

  showModal(`
    <span class="eyebrow">DEVICE MANAGEMENT</span><h2>${esc(w.worker_label || "Worker")}</h2>
    <div class="device-detail"><span>Device ID</span><code>${esc(w.device_code)}</code><span>Status</span><strong>${esc(w.status)}</strong><span>Last sync</span><strong>${esc(formatDateTime(w.last_sync_at))}</strong></div>
    <div class="modal-actions">
      ${w.status !== "revoked" ? `<button class="btn btn-danger" id="revokeDevice">Revoke device</button>` : ""}
      <button class="btn btn-secondary" id="closeDevice">Close</button>
    </div>`);

  $("closeDevice").onclick = closeModal;

  if ($("revokeDevice")) $("revokeDevice").onclick = async () => {
    if (!confirm("Revoke this device? Future synchronization from it will be denied.")) return;

    try {
      await apiRequest(`/workers/${encodeURIComponent(id)}/revoke`, {
        method: "POST"
      });

      closeModal();
      await loadWorkers();
      await loadAudit();
      renderOverview();
      toast("Device revoked.");

    } catch (e) {
      console.error("REVOKE DEVICE ERROR:", e);
      toast(e.message || "Unable to revoke device.", "error");
    }
  };
}

function openStudy(id) {
  const s = state.studies.find(x => x.id === id);
  if (!s) return;
  const count = state.records.filter(r => r.study_id === id).length;
  showModal(`<span class="eyebrow">${esc(s.study_code)}</span><h2>${esc(s.study_name)}</h2><p class="modal-helper">${esc(s.description || "No description provided.")}</p><div class="study-summary"><strong>${count.toLocaleString()}</strong><span>loaded cloud records</span></div><button class="btn btn-secondary btn-block" onclick="closeModal()">Close</button>`);
}

async function saveSettings() {
  try {
    await apiRequest("/organization", {
      method: "PUT",
      body: JSON.stringify({
        organization_name: $("settingsOrgName").value.trim(),
        admin_name: $("settingsAdminName").value.trim()
      })
    });

    await loadOrganization();
    toast("Organization profile updated.");

  } catch (e) {
    console.error("SAVE SETTINGS ERROR:", e);
    toast(e.message || "Unable to save settings.", "error");
  }
}

function copy(text) {
  navigator.clipboard.writeText(text).then(() => toast("Copied to clipboard."));
}

function bindNavigation() {
  document.querySelectorAll(".nav-item[data-view]").forEach(btn => {
    btn.onclick = () => switchView(btn.dataset.view);
  });

  document.querySelectorAll("[data-go]").forEach(btn => {
    btn.onclick = () => switchView(btn.dataset.go);
  });
}

function bindDashboardControls() {
  // Workers / invitations
  $("newInviteBtn").onclick = createInvitation;
  $("newInviteBtn2").onclick = createInvitation;

  // Studies
  $("newStudyBtn").onclick = createStudy;

  // Worker search + status filter
  $("workerSearch").oninput = renderWorkers;
  $("workerStatusFilter").onchange = renderWorkers;

  // Cloud data
  $("refreshDataBtn").onclick = async () => {
    try {
      const button = $("refreshDataBtn");
      button.disabled = true;

      await loadRecords();
      renderData();

      toast("Cloud data refreshed.");
    } catch (e) {
      console.error("REFRESH DATA ERROR:", e);
      toast(e.message || "Unable to refresh cloud data.", "error");
    } finally {
      $("refreshDataBtn").disabled = false;
    }
  };

  $("applyDataFilter").onclick = () => {
    renderData();
  };

  $("dataWorkerFilter").onchange = renderData;
  $("dataStudyFilter").onchange = renderData;
  $("dataLocationFilter").oninput = renderData;
  $("dataFrom").onchange = renderData;
  $("dataTo").onchange = renderData;

  // Organization ID copy
  $("copyOrgCode").onclick = () => {
    if (state.org?.organization_code) {
      copy(state.org.organization_code);
    }
  };

  $("copySettingsCode").onclick = () => {
    if (state.org?.organization_code) {
      copy(state.org.organization_code);
    }
  };

  // Organization settings
  $("saveSettings").onclick = saveSettings;

    // Mobile sidebar
  $("mobileMenu").onclick = openSidebar;
  $("mobileClose").onclick = closeSidebar;
  $("sidebarBackdrop").onclick = closeSidebar;
}

function switchView(view) {
  document.querySelectorAll(".view").forEach(v => v.classList.remove("active-view"));
  document.querySelector(`#view-${view}`).classList.add("active-view");
  document.querySelectorAll(".nav-item[data-view]").forEach(b => b.classList.toggle("active", b.dataset.view === view));
  const titles = {
    overview:["ORGANIZATION OVERVIEW","Good afternoon, Admin"],
    workers:["FIELD NETWORK","Workers & devices"],
    studies:["PROJECT MANAGEMENT","Studies"],
    data:["CENTRAL DATASET","Cloud data"],
    invitations:["DEVICE ENROLLMENT","Invitation codes"],
    audit:["COMPLIANCE","Audit log"],
    settings:["ORGANIZATION","Organization settings"]
  };
  $("viewEyebrow").textContent = titles[view][0];
  $("viewTitle").textContent = titles[view][1];
  closeSidebar();
  if (view === "data") { fillDataFilters(); renderData(); }
}

function closeSidebar() { $("sidebar").classList.remove("open"); $("sidebarBackdrop").classList.remove("show"); }
function openSidebar() { $("sidebar").classList.add("open"); $("sidebarBackdrop").classList.add("show"); }

async function initDashboard() {
  const authenticated = await requireUser();

  if (!authenticated) {
    return;
  }

  $("logoutBtn").onclick = async () => {
    try {
      await apiRequest("/auth/logout", {
        method: "POST"
      });
    } catch (e) {
      console.error("Logout failed:", e);
    }

    window.location.href = "./index.html";
  };

  await refreshAll();
  bindNavigation();
  bindDashboardControls();

}

window.AchievXAdmin = {
  initAuthPage, initDashboard, copy, openDevice, openStudy, closeModal
};
