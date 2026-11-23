import { api } from "./api.js";
import { riskBar } from "./charts.js";
import { $, emptyRow, esc, fmtDateTime, icon, initShell, levelLabel, methodTag, personCell, qualityTag, riskBadge, todayLong } from "./ui.js";

const user = await initShell("dashboard.html", ["admin", "teacher", "advisor"]);
if (user) {
  const main = $("#main");
  main.innerHTML = `
    <div class="page-head"><div><p class="eyebrow">${esc(todayLong())}</p><h1>Welcome back, ${esc(user.full_name.split(" ")[0])}</h1>
      <p>Early-warning overview for the students you are authorized to support.</p></div>
      <span class="pill" id="last-run" hidden><span class="dot" aria-hidden="true"></span><span></span></span></div>
    <div class="notice">Risk levels are <strong>estimates</strong> based on attendance, class tests/exams, homework and online learning portal
      activity. Review the contributing factors and talk with the student before acting. No action is taken automatically.</div>
    <section class="grid grid-4" aria-label="Key figures" id="kpis"></section>
    <div class="grid grid-main mt">
      <section class="card"><div class="card-head"><h2>Priority alerts</h2><a href="alerts.html" class="btn secondary small">View all alerts</a></div>
        <div class="table-wrap"><table><caption class="sr-only">Highest-priority current alerts</caption>
          <thead><tr><th>Student</th><th>Risk</th><th>Main factor</th><th>Source</th><th>Review</th></tr></thead>
          <tbody id="alert-rows"><tr><td colspan="5" class="loading">Loading…</td></tr></tbody></table></div></section>
      <section class="card"><h2>Risk distribution</h2>
        <div class="chart-box"><canvas id="dist" role="img" aria-label="Bar chart of students by risk level"></canvas></div>
        <ul class="legend-list small" id="dist-text"></ul></section>
    </div>`;

  const [summary, alerts] = await Promise.all([api("/risk/summary"), api("/risk/alerts?limit=10")]);
  if (summary.last_assessed_at) {
    $("#last-run span:last-child").textContent = `Last assessed ${fmtDateTime(summary.last_assessed_at)}`;
    $("#last-run").hidden = false;
  }
  const k = summary.levels;
  const kpis = [
    { v: summary.students, l: "Students in your scope", i: "users", t: "" },
    { v: k.high + k.critical, l: "High or critical alerts", i: "alert", t: "tone-critical" },
    { v: summary.unreviewed_high, l: "High/critical not yet reviewed", i: "clipboard", t: "tone-high" },
    { v: summary.open_plans, l: "Open support plans", i: "support", t: "tone-low" },
  ];
  $("#kpis").innerHTML = kpis.map((x) => `<div class="card kpi ${x.t}"><div class="kpi-top"><span class="kpi-icon">${icon(x.i)}</span></div>
    <span class="value">${x.v}</span><span class="label">${x.l}</span></div>`).join("");
  if (summary.fallback_count) {
    $("#kpis").insertAdjacentHTML("afterend", `<div class="warning-box" role="status">${summary.fallback_count} current assessment(s) were produced by the rule-based fallback because the predictive model was unavailable.</div>`);
  }

  const order = ["low", "moderate", "high", "critical", "insufficient_data"];
  riskBar($("#dist"), order.map(levelLabel), order.map((l) => k[l]), order);
  $("#dist-text").innerHTML = order.map((l) => `<li>${riskBadge(l)}<strong>${k[l]}<span class="sr-only"> students</span></strong></li>`).join("");

  $("#alert-rows").innerHTML = alerts.items.length ? alerts.items.map((s) => {
    const a = s.assessment, f = a.factors?.[0];
    return `<tr><td>${personCell(s.full_name, `student.html?id=${s.id}`, `${s.student_code} · ${s.program}`)}</td>
      <td>${riskBadge(a.risk_level)}</td><td class="small">${f ? esc(f.label) : '<span class="muted">—</span>'}</td>
      <td>${methodTag(a)} ${qualityTag(a)}</td><td><span class="tag">${esc(a.review_status)}</span></td></tr>`;
  }).join("") : emptyRow(5, "No current alerts in your scope.");
}
