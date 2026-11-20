import { api, download } from "./api.js";
import { line, stackedLevels } from "./charts.js";
import { $, esc, initShell, levelLabel, titleCase, toast } from "./ui.js";

const user = await initShell("reports.html", ["admin", "teacher", "advisor", "analyst"]);
const LV = ["low", "moderate", "high", "critical", "insufficient_data"];
const show = (v) => (v == null ? "<5" : v);

if (user) {
  const [s, t] = await Promise.all([api("/reports/summary"), api("/reports/trends")]);
  const canIdent = user.role !== "analyst" || user.identifiable_access;
  $("#main").innerHTML = `
    <div class="page-head"><div><h1>Reports &amp; analytics</h1><p>Aggregate trends ${s.deidentified ? "(de-identified; counts below " + s.min_group_size + " are suppressed)" : "for your scope"}.</p></div>
      <div class="actions"><button class="btn secondary" id="exp-d" type="button">Export de-identified CSV</button>
      ${canIdent ? `<button class="btn" id="exp-i" type="button">Export identifiable CSV</button>` : ""}</div></div>
    ${s.deidentified ? `<div class="notice">You are viewing aggregate, de-identified information only. Identifiable details need separate authorization.</div>` : ""}
    <div class="grid grid-2">
      <section class="card"><h2>Risk levels by program</h2><div class="chart-box"><canvas id="c-prog" role="img" aria-label="Stacked bar chart of risk levels by program"></canvas></div></section>
      <section class="card"><h2>Weekly attendance by course</h2><div class="chart-box"><canvas id="c-att" role="img" aria-label="Line chart of weekly attendance rate by course"></canvas></div></section>
    </div>
    <section class="card mt"><h2>Risk levels by course</h2><div class="table-wrap"><table>
      <thead><tr><th>Course</th>${LV.map((l) => `<th class="num">${levelLabel(l)}</th>`).join("")}</tr></thead>
      <tbody>${Object.entries(s.by_course).map(([c, v]) => `<tr><td><strong>${esc(c)}</strong> <span class="small muted">${esc(v.title)}</span></td>
        ${LV.map((l) => `<td class="num">${show(v.counts[l])}</td>`).join("")}</tr>`).join("")}</tbody></table></div></section>
    <div class="grid grid-3 mt">
      <section class="card"><h2>Overall</h2><ul class="small">${LV.map((l) => `<li>${levelLabel(l)}: ${show(s.overall[l])}</li>`).join("")}</ul>
        <p class="small muted">Total assessed: ${s.total_students}</p></section>
      <section class="card"><h2>Support plans</h2><ul class="small">${Object.entries(s.plans).map(([k, v]) => `<li>${titleCase(k)}: ${show(v)}</li>`).join("") || "<li>None yet</li>"}</ul>
        <h3>Interventions</h3><ul class="small">${Object.entries(s.interventions).map(([k, v]) => `<li>${titleCase(k)}: ${show(v)}</li>`).join("") || "<li>None yet</li>"}</ul></section>
      <section class="card"><h2>Assessment source</h2><ul class="small">${Object.entries(s.methods).map(([k, v]) => `<li>${titleCase(k)}: ${show(v)}</li>`).join("")}</ul>
        <p class="small muted">"Rules fallback" means the predictive model was unavailable when the assessment ran.</p></section>
    </div>`;

  const progs = Object.keys(s.by_program);
  stackedLevels($("#c-prog"), progs, Object.fromEntries(LV.map((l) => [l, progs.map((p) => s.by_program[p][l] ?? 0)])));
  const courses = Object.keys(t.attendance_by_course);
  const weeks = [...new Set(courses.flatMap((c) => t.attendance_by_course[c].map((x) => x.week)))].sort((a, b) => a - b);
  line($("#c-att"), weeks.map((w) => `W${w}`), courses.map((c) => ({ label: c, data: weeks.map((w) => {
    const x = t.attendance_by_course[c].find((y) => y.week === w); return x?.rate != null ? Math.round(x.rate * 100) : null; }) })),
    { yMax: 100, yFormat: (v) => `${v}%` });

  $("#exp-d").addEventListener("click", () => download("/reports/export?identifiable=false", "report.csv").catch((e) => toast(e.message, "error")));
  $("#exp-i")?.addEventListener("click", () => download("/reports/export?identifiable=true", "report.csv").catch((e) => toast(e.message, "error")));
}
