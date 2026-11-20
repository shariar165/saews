import { api } from "./api.js";
import { $, $$, emptyRow, esc, fmtDateTime, initShell, titleCase, toast } from "./ui.js";

const user = await initShell("admin.html", ["admin"]);
const TABS = [["users", "Users & roles"], ["model", "Model monitor"], ["audit", "Audit log"], ["retention", "Data retention"]];

if (user) {
  $("#main").innerHTML = `
    <div class="page-head"><div><h1>Administration</h1><p>Accounts, model quality, audit trail and data retention.</p></div></div>
    <div class="tabs" role="tablist">${TABS.map(([k, l], i) => `<button role="tab" id="tab-${k}" aria-controls="panel" aria-selected="${i === 0}" data-tab="${k}">${l}</button>`).join("")}</div>
    <div id="panel" role="tabpanel"></div>`;
  $(".tabs").addEventListener("click", (e) => {
    const b = e.target.closest("[data-tab]"); if (!b) return;
    $$(".tabs button").forEach((x) => x.setAttribute("aria-selected", x === b)); show(b.dataset.tab);
  });
  show("users");
}

async function show(tab) {
  const old = $("#panel");
  const panel = old.cloneNode(false); // fresh element => no stale event listeners from the previous tab
  old.replaceWith(panel);
  panel.innerHTML = `<p class="loading">Loading…</p>`;
  panel.setAttribute("aria-labelledby", `tab-${tab}`);
  try { await { users, model, audit, retention }[tab](panel); } catch (e) { panel.innerHTML = `<p class="form-error">${esc(e.message)}</p>`; }
}

async function users(panel) {
  const { items } = await api("/admin/users");
  panel.innerHTML = `<div class="grid grid-main">
    <section class="card"><h2>Users</h2><div class="table-wrap"><table><thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Status</th><th>Identifiable access</th><th>Last login</th></tr></thead>
    <tbody>${items.map((u) => `<tr><td>${esc(u.full_name)}</td><td class="small">${esc(u.email)}</td>
      <td><select data-role="${u.id}" aria-label="Role for ${esc(u.full_name)}" ${u.id === user.id ? "disabled" : ""}>${["admin", "teacher", "advisor", "student", "analyst"].map((r) => `<option${r === u.role ? " selected" : ""}>${r}</option>`).join("")}</select></td>
      <td><button class="btn small ${u.is_active ? "secondary" : ""}" data-active="${u.id}" data-value="${!u.is_active}" ${u.id === user.id ? "disabled" : ""}>${u.is_active ? "Active — deactivate" : "Inactive — activate"}</button></td>
      <td>${u.role === "analyst" ? `<label class="small"><input type="checkbox" data-ident="${u.id}" ${u.identifiable_access ? "checked" : ""}> Authorized</label>` : '<span class="muted small">n/a</span>'}</td>
      <td class="small">${fmtDateTime(u.last_login_at)}</td></tr>`).join("")}</tbody></table></div></section>
    <section class="card"><h2>Create user</h2><form id="new-user">
      <div class="field"><label for="nu-name">Full name</label><input id="nu-name" required minlength="2"></div>
      <div class="field"><label for="nu-email">Email</label><input id="nu-email" type="email" required></div>
      <div class="field"><label for="nu-role">Role</label><select id="nu-role"><option>teacher</option><option>advisor</option><option>student</option><option>analyst</option><option>admin</option></select></div>
      <div class="field"><label for="nu-code">Student ID (student accounts)</label><input id="nu-code" placeholder="e.g. S20260042"></div>
      <div class="field"><label for="nu-pw">Initial password</label><input id="nu-pw" type="password" minlength="10" required autocomplete="new-password"><span class="help">At least 10 characters. Stored as an Argon2id hash.</span></div>
      <div class="actions"><button class="btn" type="submit">Create</button></div></form></section></div>`;
  const patch = async (id, body) => { try { await api(`/admin/users/${id}`, { method: "PATCH", body }); toast("User updated", "success"); } catch (e) { toast(e.message, "error"); } show("users"); };
  panel.addEventListener("change", (e) => {
    if (e.target.dataset.role) patch(e.target.dataset.role, { role: e.target.value });
    if (e.target.dataset.ident) patch(e.target.dataset.ident, { identifiable_access: e.target.checked });
  });
  panel.addEventListener("click", (e) => { const b = e.target.closest("[data-active]"); if (b) patch(b.dataset.active, { is_active: b.dataset.value === "true" }); });
  $("#new-user").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      await api("/admin/users", { method: "POST", body: { full_name: $("#nu-name").value, email: $("#nu-email").value, role: $("#nu-role").value,
        password: $("#nu-pw").value, student_code: $("#nu-code").value || null } });
      toast("User created", "success"); show("users");
    } catch (ex) { toast(ex.message, "error"); }
  });
}

const metricRow = (label, m) => m ? `<tr><th scope="row">${label}</th><td class="num">${m.recall}</td><td class="num">${m.precision}</td><td class="num">${m.fpr ?? "—"}</td>
  <td class="num">${m.fnr ?? "—"}</td><td class="num">${m.roc_auc ?? "—"}</td><td class="num">${m.brier ?? "—"}</td><td class="num">${m.flag_rate}</td></tr>` : "";

async function model(panel) {
  const d = await api("/admin/model");
  const m = d.metrics?.metrics, f = d.metrics?.fairness;
  panel.innerHTML = `<div class="grid grid-3">
      <section class="card kpi"><span class="label">Model status</span><span class="value">${d.status.available ? "Available" : "Unavailable"}</span>
        <span class="small muted">${esc(d.status.version || d.status.error || "")}</span></section>
      <section class="card kpi"><span class="label">Current assessments by source</span>
        <span class="small">${Object.entries(d.current_methods).map(([k, v]) => `${titleCase(k)}: <strong>${v}</strong>`).join("<br>")}</span></section>
      <section class="card"><h2>Refresh</h2><p class="small muted">Re-run assessments for all students in the background.</p>
        <button class="btn" id="recompute" type="button">Recompute all risk assessments</button></section></div>
    ${m ? `<section class="card mt"><h2>Validation metrics (held-out test set)</h2>
      <p class="small muted">${esc(m.training.data)}. Train ${m.training.n_train} / test ${m.training.n_test}. Alert threshold ${m.alert_threshold}.</p>
      <div class="table-wrap"><table><thead><tr><th></th><th class="num">Recall</th><th class="num">Precision</th><th class="num">FPR</th><th class="num">FNR</th><th class="num">ROC-AUC</th><th class="num">Brier</th><th class="num">Flag rate</th></tr></thead>
      <tbody>${metricRow("Model @ alert threshold", m.model_at_alert_threshold)}${metricRow("Model @ high threshold", m.model_at_high_threshold)}${metricRow("Rule baseline", m.rule_baseline)}</tbody></table></div>
      <h3>Calibration</h3><div class="table-wrap"><table><thead><tr><th>Predicted band</th><th class="num">n</th><th class="num">Mean predicted</th><th class="num">Observed rate</th></tr></thead>
      <tbody>${m.calibration.map((c) => `<tr><td>${c.bin}</td><td class="num">${c.n}</td><td class="num">${c.mean_predicted}</td><td class="num">${c.observed_rate}</td></tr>`).join("")}</tbody></table></div>
      <h3>Coefficients (standardized log-odds)</h3><p class="small">${Object.entries(m.coefficients).map(([k, v]) => `<span class="tag">${esc(k)}: ${v}</span>`).join(" ")}</p></section>
    <section class="card mt"><h2>Subgroup error rates</h2>
      <p class="small muted">Checks for unequal recall and false-positive rates. A high overall metric does not prove fairness; flagged gaps need human review. "equity_group" is a synthetic evaluation-only attribute and is never a model input.</p>
      ${Object.entries(f).map(([col, rep]) => `<h3>${esc(col)} ${rep.needs_review ? '<span class="tag warn">Needs review</span>' : '<span class="tag ok">Within tolerance</span>'}
        <span class="small muted">recall gap ${rep.recall_gap}, FPR gap ${rep.fpr_gap}</span></h3>
        <div class="table-wrap"><table><thead><tr><th>Group</th><th class="num">n</th><th class="num">Base rate</th><th class="num">Recall</th><th class="num">FPR</th><th class="num">FNR</th></tr></thead>
        <tbody>${Object.entries(rep.groups).map(([g, r]) => `<tr><td>${esc(g)}${r.sufficient_sample ? "" : ' <span class="tag">small n</span>'}</td><td class="num">${r.n}</td><td class="num">${r.base_rate}</td><td class="num">${r.recall}</td><td class="num">${r.fpr ?? "—"}</td><td class="num">${r.fnr ?? "—"}</td></tr>`).join("")}</tbody></table></div>`).join("")}
    </section>` : `<div class="warning-box mt">No model metrics available. Train a model with <code>python -m backend.app.ml.train</code>. Until then, assessments use the rule-based fallback.</div>`}
    ${d.recent_errors.length ? `<section class="card mt"><h2>Recent model errors</h2><ul class="small">${d.recent_errors.map((x) => `<li>${fmtDateTime(x.created_at)} — ${esc(x.error)}</li>`).join("")}</ul></section>` : ""}`;
  $("#recompute").addEventListener("click", async (e) => {
    e.target.disabled = true;
    try { await api("/admin/recompute", { method: "POST" }); toast("Recompute queued — refresh in a few seconds", "success"); } catch (ex) { toast(ex.message, "error"); }
  });
}

async function audit(panel) {
  panel.innerHTML = `<section class="card"><form class="toolbar" id="af">
      <div class="field"><label for="a-action">Action starts with</label><input id="a-action" placeholder="e.g. student.view, auth, report.export"></div>
      <div class="field"><label for="a-outcome">Outcome</label><select id="a-outcome"><option value="">Any</option><option>success</option><option>denied</option><option>error</option></select></div>
      <button class="btn" type="submit">Filter</button></form>
    <div class="table-wrap"><table><thead><tr><th>Time</th><th>Actor</th><th>Action</th><th>Target</th><th>Outcome</th><th>Detail</th></tr></thead><tbody id="arows"></tbody></table></div></section>`;
  const load = async () => {
    const p = new URLSearchParams({ limit: 300 });
    if ($("#a-action").value) p.set("action", $("#a-action").value);
    if ($("#a-outcome").value) p.set("outcome", $("#a-outcome").value);
    const { items } = await api(`/admin/audit?${p}`);
    $("#arows").innerHTML = items.length ? items.map((a) => `<tr><td class="small">${fmtDateTime(a.ts)}</td><td class="small">${esc(a.actor || "anonymous")} <span class="muted">${esc(a.actor_role || "")}</span></td>
      <td><code>${esc(a.action)}</code></td><td class="small">${esc(a.target_type || "")} ${esc(a.target_id || "")}</td>
      <td><span class="tag ${a.outcome === "success" ? "ok" : "warn"}">${esc(a.outcome)}</span></td><td class="small muted">${esc(JSON.stringify(a.detail))}</td></tr>`).join("") : emptyRow(6, "No entries.");
  };
  $("#af").addEventListener("submit", (e) => { e.preventDefault(); load(); });
  load();
}

async function retention(panel) {
  const d = await api("/admin/model");
  const s = d.settings;
  panel.innerHTML = `<section class="card"><h2>Retention rules</h2>
    <ul class="small"><li>Audit logs are kept for <strong>${s.audit_retention_days}</strong> days.</li>
    <li>Superseded risk assessments and import batches are kept for <strong>${s.retention_days}</strong> days.</li>
    <li>Staged upload contents are removed once a batch is committed or rejected.</li></ul>
    <p class="small muted">Retention periods are set through configuration (<code>EWS_RETENTION_DAYS</code>, <code>EWS_AUDIT_RETENTION_DAYS</code>) and must follow institutional policy.</p>
    <div class="actions"><button class="btn secondary" id="dry" type="button">Preview (dry run)</button><button class="btn danger" id="run" type="button">Apply retention now</button></div>
    <div id="ret-out" style="margin-top:1rem" aria-live="polite"></div></section>`;
  const run = async (dry) => {
    try {
      const r = await api("/admin/retention", { method: "POST", body: { dry_run: dry } });
      $("#ret-out").innerHTML = `<div class="notice">${dry ? "Would delete" : "Deleted"}: ${Object.entries(r.counts).map(([k, v]) => `${titleCase(k)} <strong>${v}</strong>`).join(", ")}</div>`;
    } catch (e) { toast(e.message, "error"); }
  };
  $("#dry").addEventListener("click", () => run(true));
  $("#run").addEventListener("click", () => run(false));
}
