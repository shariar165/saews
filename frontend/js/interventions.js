import { api } from "./api.js";
import { $, emptyRow, esc, fmtDate, fmtDateTime, initShell, personCell, titleCase, toast } from "./ui.js";

const user = await initShell("interventions.html", ["admin", "teacher", "advisor"]);
if (user) {
  $("#main").innerHTML = `
    <div class="page-head"><div><h1>Support &amp; requests</h1><p>Track support plans and respond to student help and correction requests.</p></div></div>
    <section class="card"><div class="card-head"><h2>Support plans</h2>
      <div class="toolbar" style="margin:0"><div class="field"><label for="p-status">Status</label><select id="p-status">
        <option value="">All</option><option value="planned">Planned</option><option value="in_progress">In progress</option>
        <option value="completed">Completed</option><option value="cancelled">Cancelled</option></select></div>
      <div class="field"><label for="p-mine">Owner</label><select id="p-mine"><option value="false">Everyone</option><option value="true">Owned by me</option></select></div></div></div>
      <div class="table-wrap"><table><thead><tr><th>Student</th><th>Plan</th><th>Owner</th><th>Due</th><th>Status</th><th class="num">Interventions</th></tr></thead>
      <tbody id="plans"></tbody></table></div></section>
    <section class="card mt"><div class="card-head"><h2>Request inbox</h2>
      <div class="field"><label for="r-status">Status</label><select id="r-status"><option value="">All</option><option value="open" selected>Open</option>
        <option value="in_review">In review</option><option value="resolved">Resolved</option><option value="rejected">Rejected</option></select></div></div>
      <p class="small muted">Requests are routed to the student's advisor (or a course teacher). Corrections must be checked against the source record.</p>
      <ul class="list" id="requests"></ul></section>`;

  async function loadPlans() {
    const p = new URLSearchParams({ mine: $("#p-mine").value });
    if ($("#p-status").value) p.set("status", $("#p-status").value);
    const { items } = await api(`/plans?${p}`);
    const today = new Date().toISOString().slice(0, 10);
    $("#plans").innerHTML = items.length ? items.map((x) => {
      const overdue = x.due_date && x.due_date < today && ["planned", "in_progress"].includes(x.status);
      return `<tr><td>${personCell(x.student.full_name, `student.html?id=${x.student.id}`, x.student.student_code)}</td>
        <td>${esc(x.title)}</td><td class="small">${esc(x.owner?.full_name || "—")}</td>
        <td class="small">${fmtDate(x.due_date)} ${overdue ? '<span class="tag warn">Overdue</span>' : ""}</td>
        <td><span class="tag">${titleCase(x.status)}</span></td><td class="num">${x.interventions.length}</td></tr>`;
    }).join("") : emptyRow(6, "No support plans match.");
  }

  async function loadRequests() {
    const s = $("#r-status").value;
    const { items } = await api(`/requests${s ? `?status=${s}` : ""}`);
    $("#requests").innerHTML = items.length ? items.map((r) => `<li>
      <div class="list-title">${esc(r.subject)} <span class="tag">${esc(r.kind)}</span> <span class="tag">${titleCase(r.status)}</span></div>
      <div class="small muted">From <a href="student.html?id=${r.student.id}">${esc(r.student.full_name)}</a> · ${fmtDateTime(r.created_at)}${r.target_record ? ` · Record: ${esc(r.target_record)}` : ""}</div>
      <p class="small" style="margin:.3rem 0">${esc(r.details)}</p>
      ${r.resolution ? `<p class="small"><em>Resolution:</em> ${esc(r.resolution)}</p>` : ""}
      ${["open", "in_review"].includes(r.status) ? `<details class="inline-form"><summary>Respond</summary>
        <form data-req="${r.id}"><div class="row"><div class="field"><label for="rs-${r.id}">New status</label><select id="rs-${r.id}">
          <option value="in_review">In review</option><option value="resolved">Resolved</option><option value="rejected">Rejected</option></select></div></div>
          <div class="field"><label for="rr-${r.id}">Resolution / note</label><textarea id="rr-${r.id}" maxlength="4000"></textarea></div>
          <div class="actions"><button class="btn small" type="submit">Save</button></div></form></details>` : ""}
    </li>`).join("") : `<li class="muted small">No requests.</li>`;
  }

  $("#requests").addEventListener("submit", async (e) => {
    e.preventDefault();
    const id = e.target.dataset.req;
    try {
      await api(`/requests/${id}`, { method: "PATCH", body: { status: $(`#rs-${id}`).value, resolution: $(`#rr-${id}`).value || null } });
      toast("Request updated", "success"); loadRequests();
    } catch (ex) { toast(ex.message, "error"); }
  });
  $("#p-status").addEventListener("change", loadPlans);
  $("#p-mine").addEventListener("change", loadPlans);
  $("#r-status").addEventListener("change", loadRequests);
  loadPlans(); loadRequests();
}
