import { api } from "./api.js";
import { $, $$, bindThemeToggle, esc, homeFor, icon } from "./ui.js";

const next = new URLSearchParams(location.search).get("next");
const safeNext = next && /^[a-z]+\.html(\?[\w=&%-]*)?$/.test(next) && !next.startsWith("index.html") ? next : null;

try {
  const { user } = await api("/auth/me", { redirectOn401: false });
  location.replace(safeNext || homeFor(user.role));
} catch { /* not signed in: stay on this page */ }

bindThemeToggle($(".theme-toggle"));

const reveal = $("#reveal-pw");
reveal.addEventListener("click", () => {
  const show = $("#password").type === "password";
  $("#password").type = show ? "text" : "password";
  reveal.setAttribute("aria-pressed", String(show));
  reveal.setAttribute("aria-label", show ? "Hide password" : "Show password");
  reveal.innerHTML = icon(show ? "eyeOff" : "eye");
});

const ROLE_ICON = { teacher: "book", advisor: "support", student: "graduation", analyst: "chart", admin: "settings" };

api("/meta").then((meta) => {
  if (!meta.demo_mode || !meta.demo_accounts) return;
  $("#demo-card").hidden = false;
  $("#demo-pw").textContent = meta.demo_password;
  $("#demo-rows").innerHTML = meta.demo_accounts.map((a) => `
    <button class="demo-acct" type="button" data-email="${esc(a.email)}" title="${esc(a.note)}"
      aria-label="Use ${esc(a.role)} account ${esc(a.email)}: ${esc(a.note)}">
      <span class="kpi-icon" aria-hidden="true">${icon(ROLE_ICON[a.role] || "user")}</span>
      <span class="t"><strong>${esc(a.role)}</strong><span>${esc(a.email)}</span></span></button>`).join("");
  $("#demo-rows").addEventListener("click", (e) => {
    const b = e.target.closest("[data-email]");
    if (!b) return;
    $$(".demo-acct").forEach((x) => x.classList.toggle("selected", x === b));
    $("#email").value = b.dataset.email; $("#password").value = meta.demo_password; $("#login-btn").focus();
  });
}).catch(() => {});

$("#login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const err = $("#login-error"); err.innerHTML = "";
  const email = $("#email").value.trim(), password = $("#password").value;
  if (!email || !password) { err.innerHTML = `<p class="form-error">Enter your email and password.</p>`; return; }
  const btn = $("#login-btn");
  btn.disabled = true; btn.classList.add("is-loading"); btn.setAttribute("aria-busy", "true");
  try {
    const { user } = await api("/auth/login", { method: "POST", body: { email, password } });
    location.replace(safeNext || homeFor(user.role));
  } catch (ex) {
    err.innerHTML = `<p class="form-error" role="alert">${esc(ex.message)}</p>`;
  } finally { btn.disabled = false; btn.classList.remove("is-loading"); btn.removeAttribute("aria-busy"); }
});
