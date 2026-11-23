// Shared helpers for the optional AI assistant. Every AI result is shown inside a labelled box.
import { api } from "./api.js";
import { esc, fmtDateTime, icon, toast } from "./ui.js";

let statusPromise;
/** { enabled, model, features[], label }. Never throws: on error the AI is treated as off. */
export function aiStatus() {
  statusPromise ??= api("/ai/status").catch(() => ({ enabled: false, features: [] }));
  return statusPromise;
}
export const hasFeature = (st, f) => st.enabled && st.features.includes(f);

export const aiTag = (text = "AI draft") => `<span class="tag ai" title="Drafted by the AI assistant">${icon("sparkle")}${esc(text)}</span>`;

const list = (items) => (items?.length ? `<ul>${items.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : "");

/** Wrap AI output with its label, model and timestamp. `copyText` adds a Copy button. */
export function aiBox(item, bodyHtml, { copyText } = {}) {
  return `<div class="ai-box" role="note">
    <div class="ai-head">${aiTag("AI-generated")}<span class="small muted">${esc(item.model)} · ${fmtDateTime(item.created_at)}</span>
      ${copyText != null ? `<button class="btn small ghost" type="button" data-copy="${esc(copyText)}">${icon("clipboard")}Copy</button>` : ""}</div>
    ${bodyHtml}
    <p class="ai-foot small muted">${esc(item.label)}</p></div>`;
}

export function caseSummaryHtml(item) {
  const o = item.output;
  return aiBox(item, `<p>${esc(o.summary)}</p>
    ${o.key_concerns?.length ? `<h4>Key concerns</h4>${list(o.key_concerns)}` : ""}
    ${o.positives?.length ? `<h4>Strengths</h4>${list(o.positives)}` : ""}
    ${o.conversation_starters?.length ? `<h4>Questions you could ask</h4>${list(o.conversation_starters)}` : ""}
    ${o.data_caveats?.length ? `<h4>Data caveats</h4>${list(o.data_caveats)}` : ""}`);
}

export function outcomeNoteHtml(item) {
  const o = item.output;
  const text = [o.note, ...(o.indicator_changes || []).map((c) => `• ${c}`), o.suggested_next_step ? `Next step: ${o.suggested_next_step}` : ""]
    .filter(Boolean).join("\n");
  return aiBox(item, `<p>${esc(o.note)}</p>${list(o.indicator_changes)}
    ${o.suggested_next_step ? `<p class="small"><strong>Suggested next step:</strong> ${esc(o.suggested_next_step)}</p>` : ""}`, { copyText: text });
}

export function messageHtml(item) {
  const o = item.output;
  return aiBox(item, `<p><strong>${esc(o.subject)}</strong></p><p class="ai-message">${esc(o.body)}</p>`,
    { copyText: `${o.subject}\n\n${o.body}` });
}

export function goalPlanHtml(item) {
  const o = item.output;
  return aiBox(item, `<p>${esc(o.overview)}</p>
    ${(o.weekly_steps || []).map((w) => `<h4>Week ${w.week}: ${esc(w.focus)}</h4>${list(w.actions)}`).join("")}
    ${o.study_tips?.length ? `<h4>Study tips</h4>${list(o.study_tips)}` : ""}
    ${o.who_can_help?.length ? `<h4>Who can help</h4>${list(o.who_can_help)}` : ""}`);
}

/** Run an AI request with a busy button and friendly errors. Returns the response or null. */
export async function runAi(btn, fn) {
  btn.disabled = true;
  const old = btn.innerHTML;
  btn.innerHTML = `${icon("sparkle")}Working…`;
  try { return await fn(); } catch (e) { toast(e.message, "error"); return null; } finally { btn.disabled = false; btn.innerHTML = old; }
}

// One delegated handler for every Copy button.
document.addEventListener("click", async (e) => {
  const b = e.target.closest("[data-copy]");
  if (!b) return;
  try { await navigator.clipboard.writeText(b.dataset.copy); toast("Copied to clipboard", "success"); }
  catch { toast("Copy failed. Select the text and copy it manually.", "error"); }
});
