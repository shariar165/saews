import { api, download } from "./api.js";
import { $, emptyRow, esc, fmtDateTime, initShell, toast } from "./ui.js";

const user = await initShell("imports.html", ["admin", "teacher"]);
if (user) {
  const { items: kinds } = await api("/imports/kinds");
  const allowed = kinds.filter((k) => k.allowed);
  $("#main").innerHTML = `
    <div class="page-head"><div><h1>Data import</h1><p>Upload approved CSV data. Files are validated first; nothing is saved unless every row passes.</p></div></div>
    <div class="grid grid-main">
      <section class="card"><h2>1. Validate a file</h2>
        <form id="upload"><div class="row">
          <div class="field"><label for="kind">Data type</label><select id="kind">${allowed.map((k) => `<option value="${k.kind}">${esc(k.label)}</option>`).join("")}</select></div>
          <div class="field"><label for="file">CSV file (UTF-8, max 5 MB)</label><input id="file" type="file" accept=".csv,text/csv" required></div></div>
          <div class="actions"><button class="btn" type="submit" id="validate-btn">Validate</button>
            <button class="btn secondary" type="button" id="tpl-btn">Download template</button></div></form>
        <div id="columns" class="small muted" style="margin-top:.8rem"></div>
        <div id="result" style="margin-top:1rem" aria-live="polite"></div></section>
      <section class="card"><h2>How it works</h2><ol class="small">
        <li>Choose the data type and upload a CSV that matches the template columns.</li>
        <li>The system checks required columns, data types, value ranges, duplicates, unknown students or subjects, subject enrollment${user.role === "teacher" ? ", and that you teach the subject" : ""}.</li>
        <li>If there are no errors, review the summary and <strong>commit</strong>. Risk assessments for the affected students refresh in the background.</li>
        <li>Every upload is logged with its file fingerprint (SHA-256) for traceability.</li></ol></section>
    </div>
    <section class="card mt"><h2>Import history</h2><div class="table-wrap"><table>
      <thead><tr><th>When</th><th>Type</th><th>File</th><th>Status</th><th class="num">Rows</th><th>Uploaded by</th></tr></thead><tbody id="history"></tbody></table></div></section>`;

  const showColumns = () => {
    const k = allowed.find((x) => x.kind === $("#kind").value);
    $("#columns").innerHTML = k ? `Columns: ${k.columns.map((c) => `<code>${esc(c.name)}</code>${c.required ? "" : " (optional)"}${c.values ? ` [${c.values.map(esc).join("|")}]` : ""}`).join(", ")}` : "";
  };
  $("#kind").addEventListener("change", showColumns); showColumns();
  $("#tpl-btn").addEventListener("click", () => download(`/imports/template/${$("#kind").value}`, "template.csv").catch((e) => toast(e.message, "error")));

  $("#upload").addEventListener("submit", async (e) => {
    e.preventDefault();
    const file = $("#file").files[0];
    if (!file) { toast("Choose a CSV file first", "error"); return; }
    const form = new FormData(); form.append("kind", $("#kind").value); form.append("file", file);
    $("#validate-btn").disabled = true;
    try { renderResult(await api("/imports/validate", { method: "POST", form })); loadHistory(); }
    catch (ex) { $("#result").innerHTML = `<p class="form-error" role="alert">${esc(ex.message)}</p>`; }
    finally { $("#validate-btn").disabled = false; }
  });

  function renderResult(b) {
    if (b.status === "rejected") {
      $("#result").innerHTML = `<div class="warning-box" role="alert"><strong>Validation failed: ${b.errors.length} problem(s) in ${b.total_rows} row(s).</strong>
        Fix the file and upload again. No data was saved.</div>
        <div class="table-wrap" style="max-height:320px;margin-top:.6rem"><table><thead><tr><th class="num">Line</th><th>Column</th><th>Problem</th></tr></thead><tbody>
        ${b.errors.map((x) => `<tr><td class="num">${x.row ?? "—"}</td><td>${esc(x.column || "file")}</td><td>${esc(x.message)}</td></tr>`).join("")}</tbody></table></div>`;
      return;
    }
    $("#result").innerHTML = `<div class="notice"><strong>All ${b.valid_rows} rows are valid.</strong> Commit to save them.</div>
      <button class="btn" id="commit-btn" type="button">2. Commit ${b.valid_rows} rows</button>`;
    $("#commit-btn").addEventListener("click", async (ev) => {
      ev.target.disabled = true;
      try {
        const r = await api(`/imports/${b.id}/commit`, { method: "POST" });
        $("#result").innerHTML = `<div class="notice" role="status">Committed ${r.valid_rows} rows. Refreshing risk assessments for ${r.students_refreshing} student(s) in the background.</div>`;
        $("#file").value = ""; loadHistory();
      } catch (ex) { toast(ex.message, "error"); ev.target.disabled = false; }
    });
  }

  async function loadHistory() {
    const { items } = await api("/imports");
    $("#history").innerHTML = items.length ? items.map((b) => `<tr><td class="small">${fmtDateTime(b.created_at)}</td><td>${esc(b.kind)}</td>
      <td class="small" title="SHA-256 ${esc(b.sha256)}">${esc(b.filename)}</td>
      <td><span class="tag ${b.status === "committed" ? "ok" : b.status === "rejected" ? "warn" : "info"}">${esc(b.status)}</span>${b.errors.length ? ` <span class="small muted">${b.errors.length} errors</span>` : ""}</td>
      <td class="num">${b.valid_rows}/${b.total_rows}</td><td class="small">${esc(b.uploaded_by?.full_name || "—")}</td></tr>`).join("") : emptyRow(6, "No imports yet.");
  }
  loadHistory();
}
