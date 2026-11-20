import { api } from "./api.js";
import { line } from "./charts.js";
import { $, esc, fmtDate, fmtDateTime, initShell, titleCase, toast, todayLong } from "./ui.js";

const user = await initShell("me.html", ["student"]);
if (user) {
  const profile = await api("/me/profile");
  $("#main").innerHTML = `
    <section class="welcome"><p class="eyebrow">${esc(todayLong())}</p>
      <h1>Hello, ${esc(profile.full_name.split(" ")[0])} 👋</h1>
      <p>${esc(profile.student_code)} · ${esc(profile.program)} · Year ${profile.year_of_study} · Advisor: ${esc(profile.advisor?.full_name || "—")}</p></section>
    <div class="notice">This page shows your own progress and the support your teachers and advisor have agreed with you.
      If anything looks wrong, use <em>Request a correction</em> below and it will be checked.</div>
    <div class="grid grid-main">
      <div class="stack">
        <section class="card"><h2>My progress</h2><div class="grid grid-2">
          <div><h3>Weekly attendance</h3><div class="chart-box short"><canvas id="c-att" role="img" aria-label="My weekly attendance"></canvas></div></div>
          <div><h3>Assessment scores</h3><div class="chart-box short"><canvas id="c-sc" role="img" aria-label="My assessment scores"></canvas></div></div></div>
          <p class="small" id="asg"></p></section>
        <section class="card"><h2>My support plan</h2><div id="support"></div></section>
      </div>
      <div class="stack">
        <section class="card"><h2>My study goals</h2><ul class="list" id="goals"></ul>
          <form id="goal-form" class="row" style="margin-top:.6rem;align-items:flex-end">
            <div class="field" style="flex:2"><label for="g-title">New goal</label><input id="g-title" required minlength="3" maxlength="200" placeholder="e.g. Submit all assignments on time"></div>
            <div class="field"><label for="g-date">Target date</label><input id="g-date" type="date"></div>
            <button class="btn small" type="submit">Add</button></form></section>
        <section class="card"><h2>Ask for help or a correction</h2><form id="req-form">
          <div class="field"><label for="r-kind">Type</label><select id="r-kind"><option value="help">I would like help or support</option><option value="correction">A record about me looks incorrect</option></select></div>
          <div class="field"><label for="r-subject">Subject</label><input id="r-subject" required minlength="3" maxlength="200"></div>
          <div class="field" id="r-target-wrap" hidden><label for="r-target">Which record? (course, week, assessment)</label><input id="r-target" maxlength="200" placeholder="e.g. SE331 attendance, week 7"></div>
          <div class="field"><label for="r-details">Details</label><textarea id="r-details" required minlength="5" maxlength="4000"></textarea></div>
          <div class="actions"><button class="btn" type="submit">Send request</button></div></form>
          <h3>My requests</h3><ul class="list" id="reqs"></ul></section>
      </div>
    </div>`;

  const d = await api("/me/indicators");
  line($("#c-att"), d.attendance.map((x) => `W${x.week}`), [{ label: "Attendance", data: d.attendance.map((x) => Math.round(x.rate * 100)) }], { yMax: 100, yFormat: (v) => `${v}%` });
  const names = [...new Set(d.scores.map((s) => s.name))], courses = [...new Set(d.scores.map((s) => s.course))];
  line($("#c-sc"), names, courses.map((c) => ({ label: c, data: names.map((n) => d.scores.find((s) => s.course === c && s.name === n)?.pct ?? null) })), { yMax: 100, yFormat: (v) => `${v}%` });
  const a = d.assignments;
  $("#asg").textContent = `Assignments: ${a.on_time} on time, ${a.late} late, ${a.missing} missing.`;

  async function loadSupport() {
    const s = await api("/me/support");
    $("#support").innerHTML = (s.recommendations.length || s.plans.length) ? `
      ${s.plans.map((p) => `<div class="list-title">${esc(p.title)} <span class="tag">${titleCase(p.status)}</span></div>
        <p class="small" style="margin:.2rem 0 .8rem">${esc(p.description || "")}<br><span class="muted">With ${esc(p.owner?.full_name || "staff")} · target ${fmtDate(p.due_date)}</span></p>`).join("")}`
      : `<p class="muted small">No support actions have been agreed yet. You can always ask for help using the form.</p>`;
  }
  async function loadGoals() {
    const { items } = await api("/me/goals");
    $("#goals").innerHTML = items.length ? items.map((g) => `<li><div class="list-title">${esc(g.title)} <span class="tag ${g.status === "achieved" ? "ok" : ""}">${esc(g.status)}</span></div>
      <div class="small muted">Target ${fmtDate(g.target_date)}</div>
      <div class="actions">${g.status === "active" ? `<button class="btn small secondary" data-goal="${g.id}" data-status="achieved">Mark achieved</button>` : ""}
      <button class="btn small ghost" data-del="${g.id}">Remove</button></div></li>`).join("") : `<li class="muted small">No goals yet.</li>`;
  }
  async function loadReqs() {
    const { items } = await api("/me/requests");
    $("#reqs").innerHTML = items.length ? items.map((r) => `<li><div class="list-title">${esc(r.subject)} <span class="tag">${esc(r.kind)}</span> <span class="tag">${titleCase(r.status)}</span></div>
      <div class="small muted">${fmtDateTime(r.created_at)} · with ${esc(r.assigned_to?.full_name || "staff")}</div>
      ${r.resolution ? `<div class="small"><em>Response:</em> ${esc(r.resolution)}</div>` : ""}</li>`).join("") : `<li class="muted small">No requests yet.</li>`;
  }

  $("#goal-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try { await api("/me/goals", { method: "POST", body: { title: $("#g-title").value, target_date: $("#g-date").value || null } }); e.target.reset(); loadGoals(); }
    catch (ex) { toast(ex.message, "error"); }
  });
  $("#goals").addEventListener("click", async (e) => {
    const b = e.target.closest("button"); if (!b) return;
    try {
      if (b.dataset.del) await api(`/me/goals/${b.dataset.del}`, { method: "DELETE" });
      else await api(`/me/goals/${b.dataset.goal}`, { method: "PATCH", body: { status: b.dataset.status } });
      loadGoals();
    } catch (ex) { toast(ex.message, "error"); }
  });
  $("#r-kind").addEventListener("change", () => { $("#r-target-wrap").hidden = $("#r-kind").value !== "correction"; });
  $("#req-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      await api("/me/requests", { method: "POST", body: { kind: $("#r-kind").value, subject: $("#r-subject").value, details: $("#r-details").value, target_record: $("#r-target").value || null } });
      e.target.reset(); $("#r-target-wrap").hidden = true; toast("Request sent. You will see the response here.", "success"); loadReqs();
    } catch (ex) { toast(ex.message, "error"); }
  });
  loadSupport(); loadGoals(); loadReqs();
}
