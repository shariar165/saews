import { api } from "./api.js";
import { $, emptyRow, esc, fmtDate, initShell, methodTag, personCell, qualityTag, riskBadge } from "./ui.js";

const user = await initShell("alerts.html", ["admin", "teacher", "advisor"]);
if (user) {
  $("#main").innerHTML = `
    <div class="page-head"><div><h1>Alert queue</h1><p>Current alerts, highest priority first. Open a student to review the explanation and act.</p></div></div>
    <form class="toolbar card" id="filters" aria-label="Filter alerts">
      <div class="field"><label for="f-level">Risk level</label><select id="f-level"><option value="">All alert levels</option>
        <option value="critical">Critical</option><option value="high">High</option><option value="moderate">Moderate</option>
        <option value="insufficient_data">Insufficient data</option><option value="unavailable">Unavailable</option></select></div>
      <div class="field"><label for="f-review">Review status</label><select id="f-review"><option value="">Any</option>
        <option value="unreviewed">Unreviewed</option><option value="reviewed">Reviewed</option><option value="flagged">Flagged</option></select></div>
      <div class="field"><label for="f-method">Source</label><select id="f-method"><option value="">Any</option>
        <option value="model">Predictive model</option><option value="rules_fallback">Rule-based fallback</option></select></div>
    </form>
    <section class="card"><div class="card-head"><h2 id="count">Alerts</h2></div>
      <div class="table-wrap"><table><thead><tr><th>Student</th><th>Risk</th><th class="num">Est. likelihood</th><th>Contributing factors</th>
        <th>Source / data</th><th>Data as of</th><th>Review</th></tr></thead><tbody id="rows"></tbody></table></div></section>`;

  async function load() {
    const p = new URLSearchParams();
    for (const [id, key] of [["f-level", "level"], ["f-review", "review_status"], ["f-method", "method"]]) {
      const v = $(`#${id}`).value; if (v) p.set(key, v);
    }
    $("#rows").innerHTML = `<tr><td colspan="7" class="loading">Loading…</td></tr>`;
    const { items } = await api(`/risk/alerts?${p}`);
    $("#count").textContent = `${items.length} alert${items.length === 1 ? "" : "s"}`;
    $("#rows").innerHTML = items.length ? items.map((s) => {
      const a = s.assessment;
      const factors = (a.factors || []).slice(0, 2).map((f) => `<li>${esc(f.label)}</li>`).join("");
      return `<tr><td>${personCell(s.full_name, `student.html?id=${s.id}`, s.student_code)}</td>
        <td>${riskBadge(a.risk_level)}</td><td class="num">${a.probability != null ? Math.round(a.probability * 100) + "%" : "—"}</td>
        <td class="small"><ul>${factors || "<li class='muted'>See warnings</li>"}</ul></td>
        <td>${methodTag(a)}<br>${qualityTag(a)}</td><td class="small">${fmtDate(a.data_as_of)}</td>
        <td><span class="tag">${esc(a.review_status)}</span></td></tr>`;
    }).join("") : emptyRow(7, "No alerts match these filters.");
  }
  $("#filters").addEventListener("change", load);
  load();
}
