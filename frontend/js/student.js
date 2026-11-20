import { api } from "./api.js";
import { line } from "./charts.js";
import { $, avatar, emptyRow, esc, fmtDate, fmtDateTime, icon, initShell, methodTag, pct, qs, riskBadge, titleCase, toast } from "./ui.js";

const user = await initShell("students.html", ["admin", "teacher", "advisor"]);
const id = Number(qs("id"));
const main = $("#main");

const ACTIONS = ["advisor_meeting", "tutoring_session", "study_plan_review", "attendance_followup", "email_or_message", "referral", "other"];
const TRACKED = [
  { k: "attendance_rate", label: "Attendance", fmt: (v) => pct(v), better: 1 },
  { k: "avg_score", label: "Avg score", fmt: (v) => (v == null ? "—" : `${v.toFixed(0)}%`), better: 1 },
  { k: "missing_rate", label: "Missing work", fmt: (v) => pct(v), better: -1 },
  { k: "avg_logins", label: "Logins/wk", fmt: (v) => (v == null ? "—" : v.toFixed(1)), better: 1 },
];
let staff = [];

if (user && id) {
  try { await render(); } catch (e) {
    main.innerHTML = `<div class="card"><h1>Student profile</h1><p class="form-error" role="alert">${esc(e.message)}</p>
      <p><a href="students.html">Back to students</a></p></div>`;
  }
} else if (user) {
  main.innerHTML = `<div class="card">No student selected. <a href="students.html">Browse students</a>.</div>`;
}

async function render() {
  const [st, staffRes] = await Promise.all([api(`/students/${id}`), api("/staff")]);
  staff = staffRes.items;
  document.title = `${st.full_name} · SAEWS`;
  main.innerHTML = `
    <p class="small" style="margin:0 0 .75rem"><a class="back-link" href="students.html">${icon("arrowLeft")} Students</a></p>
    <section class="card profile-card">${avatar(st.full_name, "lg")}
      <div class="who"><h1>${esc(st.full_name)}</h1>
        <div class="chips"><span class="chip">${icon("user")}${esc(st.student_code)}</span><span class="chip">${icon("graduation")}${esc(st.program)} · Year ${st.year_of_study}</span>
          <span class="chip">${icon("support")}Advisor: ${esc(st.advisor?.full_name || "—")}</span></div>
        <div class="chips"><span class="small muted">Courses:</span> ${st.courses.map((c) => `<span class="tag" title="${esc(c.title)} — ${esc(c.teacher || "")}">${esc(c.code)}</span>`).join(" ")}</div></div>
      <button class="btn secondary" id="reassess" type="button">${icon("refresh")}Re-assess now</button></section>
    <div class="grid grid-main">
      <div class="stack">
        <section class="card" id="assessment" aria-labelledby="ra-title"></section>
        <section class="card"><h2>Progress indicators</h2>
          <div class="grid grid-2">
            <div><h3>Weekly attendance</h3><div class="chart-box short"><canvas id="c-att" role="img" aria-label="Weekly attendance rate"></canvas></div></div>
            <div><h3>Learning-platform logins (per course, weekly)</h3><div class="chart-box short"><canvas id="c-eng" role="img" aria-label="Weekly logins"></canvas></div></div>
          </div>
          <h3>Assessment scores</h3><div class="chart-box short"><canvas id="c-sc" role="img" aria-label="Assessment scores by course"></canvas></div>
          <p class="small" id="asg-summary"></p></section>
        <section class="card"><h2>Assessment history</h2><div class="table-wrap"><table>
          <thead><tr><th>Assessed</th><th>Risk</th><th class="num">Likelihood</th><th>Source</th><th>Model</th><th>Review</th></tr></thead>
          <tbody id="history"></tbody></table></div></section>
      </div>
      <div class="stack">
        <section class="card"><h2>Suggested support</h2><p class="small muted">Suggestions must be approved or edited by staff before the student sees them.</p><ul class="list" id="recs"></ul></section>
        <section class="card"><div class="card-head"><h2>Support plans &amp; interventions</h2></div><div id="plans"></div>
          <details class="inline-form"><summary>Create a support plan manually</summary>
            <form id="plan-form"><div class="field"><label for="p-title">Title</label><input id="p-title" required minlength="3" maxlength="200"></div>
            <div class="field"><label for="p-desc">Description</label><textarea id="p-desc" maxlength="4000"></textarea></div>
            <div class="row"><div class="field"><label for="p-owner">Owner</label><select id="p-owner">${ownerOptions(user.id)}</select></div>
            <div class="field"><label for="p-due">Due date</label><input id="p-due" type="date"></div></div>
            <div class="actions"><button class="btn small" type="submit">Create plan</button></div></form></details></section>
        <section class="card"><h2>Student requests</h2><ul class="list" id="requests"></ul></section>
      </div>
    </div>`;

  renderAssessment(st.assessment);
  $("#reassess").addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    try { renderAssessment(await api(`/students/${id}/assess`, { method: "POST" })); await Promise.all([loadRecs(), loadHistory()]); toast("Assessment refreshed", "success"); }
    catch (ex) { toast(ex.message, "error"); } finally { btn.disabled = false; }
  });
  $("#plan-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      await api("/plans", { method: "POST", body: { student_id: id, title: $("#p-title").value, description: $("#p-desc").value || null,
        owner_id: Number($("#p-owner").value), due_date: $("#p-due").value || null } });
      e.target.reset(); e.target.closest("details").open = false; toast("Support plan created", "success"); loadPlans();
    } catch (ex) { toast(ex.message, "error"); }
  });
  await Promise.all([loadIndicators(), loadHistory(), loadRecs(), loadPlans(), loadRequests()]);
}

function ownerOptions(selected) {
  return staff.map((s) => `<option value="${s.id}"${s.id === selected ? " selected" : ""}>${esc(s.full_name)} (${esc(s.role)})</option>`).join("")
    || `<option value="${user.id}">${esc(user.full_name)}</option>`;
}

function renderAssessment(a) {
  const box = $("#assessment");
  if (!a) { box.innerHTML = `<h2 id="ra-title">Current assessment</h2><p class="muted">Not assessed yet.</p>`; return; }
  const maxC = Math.max(...(a.factors || []).map((f) => f.contribution), 1);
  const factors = (a.factors || []).map((f) => `<div class="factor"><div>${esc(f.label)}</div>
      <div class="factor-bar" role="img" aria-label="Relative weight ${Math.round((f.contribution / maxC) * 100)}%"><span style="width:${Math.round((f.contribution / maxC) * 100)}%"></span></div></div>`).join("");
  box.innerHTML = `
    <div class="card-head"><h2 id="ra-title">Current assessment</h2><span class="tag">Review: ${esc(a.review_status)}</span></div>
    <div class="risk-hero">${riskBadge(a.risk_level)}
      ${a.probability != null ? `<div class="meter tone-${esc(a.risk_level)}" style="--p:${Math.round(a.probability * 100)}" aria-hidden="true"><span>${Math.round(a.probability * 100)}%</span></div>
        <div class="risk-stat"><strong>${Math.round(a.probability * 100)}%</strong><span class="muted small">estimated likelihood of academic difficulty</span></div>` : ""}
      ${a.rule_points != null ? `<div class="risk-stat"><strong>${a.rule_points}</strong><span class="muted small">rule points</span></div>` : ""}
      ${methodTag(a)}</div>
    ${a.warnings?.length ? `<div class="warning-box" role="note"><strong>Data quality</strong><ul>${a.warnings.map((w) => `<li>${esc(w)}</li>`).join("")}</ul></div>` : ""}
    <h3>Main contributing factors</h3>
    ${factors || `<p class="muted small">No individual factor stands out${a.risk_level === "insufficient_data" ? " (not enough data)" : ""}.</p>`}
    <dl class="meta-list">
      <dt>Source</dt><dd>${esc(a.method_label)}${a.model_version ? ` · ${esc(a.model_version)}` : ""}</dd>
      <dt>Assessed</dt><dd>${fmtDateTime(a.created_at)}</dd>
      <dt>Data as of</dt><dd>${fmtDate(a.data_as_of)}${a.data_age_days != null ? ` (${a.data_age_days} days ago)` : ""}</dd>
      <dt>Data completeness</dt><dd>${pct(a.completeness)}</dd>
      ${a.review_note ? `<dt>Review note</dt><dd>${esc(a.review_note)}</dd>` : ""}
    </dl>
    <p class="disclaimer">This is an estimate, not a fact. Confirm with the student and course context before acting. It must not be used for grading, discipline or eligibility decisions.</p>
    <div class="actions">
      <details class="inline-form" style="flex:1"><summary>Mark as reviewed</summary>
        <form id="review-form"><div class="field"><label for="r-note">Note (optional)</label><textarea id="r-note" maxlength="2000"></textarea></div>
        <div class="actions"><button class="btn small" type="submit">Confirm review</button></div></form></details>
      <details class="inline-form" style="flex:1"><summary>Flag this alert</summary>
        <form id="flag-form"><div class="field"><label for="f-reason">Why is it incorrect or inappropriate?</label><textarea id="f-reason" required minlength="3" maxlength="2000"></textarea></div>
        <label class="small"><input type="checkbox" id="f-data"> The underlying data is wrong (opens a correction request)</label>
        <div class="actions"><button class="btn small danger" type="submit">Flag alert</button></div></form></details>
    </div>`;
  $("#review-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try { renderAssessment(await api(`/risk/${a.id}/review`, { method: "POST", body: { note: $("#r-note").value || null } })); toast("Marked as reviewed", "success"); loadHistory(); }
    catch (ex) { toast(ex.message, "error"); }
  });
  $("#flag-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      renderAssessment(await api(`/risk/${a.id}/flag`, { method: "POST", body: { reason: $("#f-reason").value, data_issue: $("#f-data").checked } }));
      toast("Alert flagged for review", "success"); loadHistory(); loadRequests();
    } catch (ex) { toast(ex.message, "error"); }
  });
}

async function loadIndicators() {
  const d = await api(`/students/${id}/indicators`);
  line($("#c-att"), d.attendance.map((x) => `W${x.week}`), [{ label: "Attendance rate", data: d.attendance.map((x) => Math.round(x.rate * 100)) }],
    { yMax: 100, yFormat: (v) => `${v}%` });
  line($("#c-eng"), d.engagement.map((x) => `W${x.week}`), [{ label: "Avg logins", data: d.engagement.map((x) => x.logins) }]);
  const names = [...new Set(d.scores.map((s) => s.name))];
  const courses = [...new Set(d.scores.map((s) => s.course))];
  line($("#c-sc"), names, courses.map((c) => ({ label: c, data: names.map((n) => d.scores.find((s) => s.course === c && s.name === n)?.pct ?? null) })),
    { yMax: 100, yFormat: (v) => `${v}%` });
  const a = d.assignments, total = a.on_time + a.late + a.missing;
  $("#asg-summary").textContent = total ? `Assignments: ${a.on_time} on time, ${a.late} late, ${a.missing} missing (of ${total}).` : "No assignment data.";
}

async function loadHistory() {
  const { items } = await api(`/students/${id}/assessments`);
  $("#history").innerHTML = items.length ? items.slice(0, 10).map((a) => `<tr><td class="small">${fmtDateTime(a.created_at)}</td><td>${riskBadge(a.risk_level)}</td>
    <td class="num">${a.probability != null ? Math.round(a.probability * 100) + "%" : "—"}</td><td>${methodTag(a)}</td>
    <td class="small">${esc(a.model_version || "—")}</td><td><span class="tag">${esc(a.review_status)}</span></td></tr>`).join("") : emptyRow(6, "No assessments yet.");
}

async function loadRecs() {
  const { items } = await api(`/students/${id}/recommendations`);
  const list = $("#recs");
  if (!items.length) { list.innerHTML = `<li class="muted small">No suggestions. Suggestions appear for moderate or higher risk.</li>`; return; }
  const due = new Date(Date.now() + 14 * 864e5).toISOString().slice(0, 10);
  list.innerHTML = items.map((r) => `<li data-rec="${r.id}">
      <div class="list-title">${esc(r.title)} <span class="tag ${r.status === "approved" ? "ok" : r.status === "dismissed" ? "" : "info"}">${esc(r.status)}</span></div>
      <p class="small" style="margin:.3rem 0">${esc(r.text)}</p>
      ${r.review_note ? `<p class="small muted">Note: ${esc(r.review_note)}</p>` : ""}
      ${r.status === "proposed" ? `
      <details class="inline-form"><summary>Approve &amp; create plan</summary>
        <form data-approve="${r.id}">
          <div class="field"><label for="e-${r.id}">Text shown to the student (edit if needed)</label><textarea id="e-${r.id}" maxlength="4000">${esc(r.rationale)}</textarea></div>
          <div class="row"><div class="field"><label for="o-${r.id}">Owner</label><select id="o-${r.id}">${ownerOptions(user.id)}</select></div>
          <div class="field"><label for="d-${r.id}">Due date</label><input id="d-${r.id}" type="date" value="${due}" required></div></div>
          <div class="actions"><button class="btn small" type="submit">Approve</button></div></form></details>
      <details class="inline-form"><summary>Dismiss</summary>
        <form data-dismiss="${r.id}"><div class="field"><label for="x-${r.id}">Reason</label><input id="x-${r.id}" required minlength="3" maxlength="2000"></div>
          <div class="actions"><button class="btn small danger" type="submit">Dismiss</button></div></form></details>` : ""}
    </li>`).join("");
}

$("#main").addEventListener("submit", async (e) => {
  const f = e.target;
  try {
    if (f.dataset.approve) {
      e.preventDefault(); const rid = f.dataset.approve;
      await api(`/recommendations/${rid}/approve`, { method: "POST", body: { edited_text: $(`#e-${rid}`).value, owner_id: Number($(`#o-${rid}`).value), due_date: $(`#d-${rid}`).value } });
      toast("Recommendation approved and support plan created", "success"); await Promise.all([loadRecs(), loadPlans()]);
    } else if (f.dataset.dismiss) {
      e.preventDefault(); const rid = f.dataset.dismiss;
      await api(`/recommendations/${rid}/dismiss`, { method: "POST", body: { reason: $(`#x-${rid}`).value } });
      toast("Recommendation dismissed"); loadRecs();
    } else if (f.dataset.addIv) {
      e.preventDefault(); const pid = f.dataset.addIv;
      await api(`/plans/${pid}/interventions`, { method: "POST", body: { action_type: $(`#ia-${pid}`).value, notes: $(`#in-${pid}`).value || null, status: $(`#is-${pid}`).value } });
      toast("Intervention recorded", "success"); loadPlans();
    } else if (f.dataset.outcome) {
      e.preventDefault(); const iid = f.dataset.outcome;
      await api(`/interventions/${iid}`, { method: "PATCH", body: { status: $(`#os-${iid}`).value, outcome: $(`#ot-${iid}`).value, capture_followup: true } });
      toast("Outcome saved; indicators captured for comparison", "success"); loadPlans();
    }
  } catch (ex) { toast(ex.message, "error"); }
});

$("#main").addEventListener("change", async (e) => {
  const sel = e.target.closest("[data-plan-status]");
  if (!sel) return;
  try { await api(`/plans/${sel.dataset.planStatus}`, { method: "PATCH", body: { status: sel.value } }); toast("Plan status updated", "success"); }
  catch (ex) { toast(ex.message, "error"); loadPlans(); }
});

function deltas(iv) {
  if (!iv.followup_snapshot) return "";
  const b = iv.baseline_snapshot || {}, f = iv.followup_snapshot;
  return `<div class="small">Before → after: ${TRACKED.map((t) => {
    const x = b[t.k], y = f[t.k];
    if (x == null || y == null) return "";
    const diff = (y - x) * t.better;
    const cls = Math.abs(diff) < 1e-9 ? "" : diff > 0 ? "delta-up" : "delta-down";
    return `${t.label} ${t.fmt(x)} → <span class="${cls}">${t.fmt(y)}</span>`;
  }).filter(Boolean).join(" · ")}</div>`;
}

async function loadPlans() {
  const { items } = await api(`/students/${id}/plans`);
  const box = $("#plans");
  if (!items.length) { box.innerHTML = `<p class="muted small">No support plans yet. Approve a suggestion or create a plan.</p>`; return; }
  box.innerHTML = `<ul class="list">${items.map((p) => `<li>
    <div class="list-title">${esc(p.title)}</div>
    <div class="small muted">Owner: ${esc(p.owner?.full_name || "—")} · Due ${fmtDate(p.due_date)}</div>
    <div class="row" style="align-items:center;margin-top:.4rem"><label class="small" for="ps-${p.id}" style="margin:0">Status</label>
      <select id="ps-${p.id}" data-plan-status="${p.id}">${["planned", "in_progress", "completed", "cancelled"].map((s) => `<option value="${s}"${s === p.status ? " selected" : ""}>${titleCase(s)}</option>`).join("")}</select></div>
    ${p.interventions.length ? `<div class="timeline">${p.interventions.map((iv) => `<div>
      <strong>${titleCase(iv.action_type)}</strong> <span class="tag">${esc(iv.status)}</span>
      <div class="small muted">${fmtDateTime(iv.performed_at)} · ${esc(iv.performed_by?.full_name || "")}</div>
      ${iv.notes ? `<div class="small">${esc(iv.notes)}</div>` : ""}
      ${iv.outcome ? `<div class="small"><em>Outcome:</em> ${esc(iv.outcome)}</div>` : ""}
      ${deltas(iv)}
      ${iv.status !== "done" || !iv.outcome ? `<details class="inline-form"><summary>Record outcome</summary>
        <form data-outcome="${iv.id}"><div class="row"><div class="field"><label for="os-${iv.id}">Status</label><select id="os-${iv.id}">
          <option value="done">Done</option><option value="missed">Missed</option><option value="scheduled">Scheduled</option></select></div></div>
          <div class="field"><label for="ot-${iv.id}">Outcome</label><textarea id="ot-${iv.id}" required maxlength="4000"></textarea></div>
          <div class="actions"><button class="btn small" type="submit">Save outcome</button></div></form></details>` : ""}
    </div>`).join("")}</div>` : ""}
    <details class="inline-form"><summary>Record an intervention</summary>
      <form data-add-iv="${p.id}"><div class="row">
        <div class="field"><label for="ia-${p.id}">Action</label><select id="ia-${p.id}">${ACTIONS.map((a) => `<option value="${a}">${titleCase(a)}</option>`).join("")}</select></div>
        <div class="field"><label for="is-${p.id}">Status</label><select id="is-${p.id}"><option value="scheduled">Scheduled</option><option value="done">Done</option></select></div></div>
        <div class="field"><label for="in-${p.id}">Notes</label><textarea id="in-${p.id}" maxlength="4000"></textarea></div>
        <div class="actions"><button class="btn small" type="submit">Save</button></div></form></details>
  </li>`).join("")}</ul>`;
}

async function loadRequests() {
  const { items } = await api(`/students/${id}/requests`);
  $("#requests").innerHTML = items.length ? items.map((r) => `<li><div class="list-title">${esc(r.subject)} <span class="tag">${esc(r.kind)}</span> <span class="tag">${esc(r.status)}</span></div>
    <div class="small">${esc(r.details)}</div><div class="small muted">${fmtDateTime(r.created_at)} · assigned to ${esc(r.assigned_to?.full_name || "—")}</div>
    ${r.resolution ? `<div class="small"><em>Resolution:</em> ${esc(r.resolution)}</div>` : ""}</li>`).join("")
    : `<li class="muted small">No help or correction requests.</li>`;
}
