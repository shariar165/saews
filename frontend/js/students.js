import { api } from "./api.js";
import { $, emptyRow, esc, initShell, methodTag, personCell, qualityTag, riskBadge } from "./ui.js";

const user = await initShell("students.html", ["admin", "teacher", "advisor"]);
if (user) {
  $("#main").innerHTML = `
    <div class="page-head"><div><h1>Students</h1><p>Students you are authorized to view${user.role === "teacher" ? " (enrolled in your courses)" : user.role === "advisor" ? " (your advisees)" : ""}.</p></div></div>
    <form class="toolbar card" id="filters" role="search">
      <div class="field" style="flex:2"><label for="q">Search</label><input id="q" type="search" placeholder="Name or student ID"></div>
      <div class="field"><label for="level">Risk level</label><select id="level"><option value="">Any</option>
        <option value="critical">Critical</option><option value="high">High</option><option value="moderate">Moderate</option>
        <option value="low">Low</option><option value="insufficient_data">Insufficient data</option></select></div>
      <div class="field"><label for="program">Program</label><select id="program"><option value="">Any</option></select></div>
      <button class="btn" type="submit">Apply</button>
    </form>
    <section class="card"><div class="card-head"><h2 id="count">Students</h2></div>
      <div class="table-wrap"><table><thead><tr><th>Student</th><th>Program</th><th class="num">Year</th><th>Risk</th><th>Source / data</th><th>Advisor</th></tr></thead>
      <tbody id="rows"></tbody></table></div></section>`;

  let programsLoaded = false;
  async function load() {
    const p = new URLSearchParams();
    if ($("#q").value.trim()) p.set("search", $("#q").value.trim());
    if ($("#level").value) p.set("level", $("#level").value);
    if ($("#program").value) p.set("program", $("#program").value);
    $("#rows").innerHTML = `<tr><td colspan="6" class="loading">Loading…</td></tr>`;
    const { items, programs } = await api(`/students?${p}`);
    if (!programsLoaded) {
      $("#program").insertAdjacentHTML("beforeend", programs.map((x) => `<option>${esc(x)}</option>`).join(""));
      programsLoaded = true;
    }
    $("#count").textContent = `${items.length} student${items.length === 1 ? "" : "s"}`;
    $("#rows").innerHTML = items.length ? items.map((s) => `<tr>
      <td>${personCell(s.full_name, `student.html?id=${s.id}`, s.student_code)}</td>
      <td>${esc(s.program)}</td><td class="num">${s.year_of_study}</td><td>${riskBadge(s.assessment?.risk_level)}</td>
      <td>${methodTag(s.assessment)} ${qualityTag(s.assessment)}</td><td class="small">${esc(s.advisor?.full_name || "—")}</td></tr>`).join("")
      : emptyRow(6, "No students match.");
  }
  $("#filters").addEventListener("submit", (e) => { e.preventDefault(); load(); });
  $("#level").addEventListener("change", load);
  $("#program").addEventListener("change", load);
  load();
}
