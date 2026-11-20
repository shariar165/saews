import { api } from "./api.js";

export const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

/* ---------- icons (inline SVG, CSP-safe; stroke icons drawn on a 24px grid) ---------- */
const P = {
  dashboard: '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
  alert: '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/>',
  users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8"/>',
  support: '<path d="M19 14c1.5-1.5 3-3.2 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.8 0-3 .5-4.5 2-1.5-1.5-2.7-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4 3 5.5l7 7z"/>',
  upload: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m17 8-5-5-5 5M12 3v12"/>',
  chart: '<path d="M3 3v18h18"/><path d="M7 15l4-4 3 3 6-6"/>',
  settings: '<path d="M12.2 2h-.4a2 2 0 0 0-2 2v.2a2 2 0 0 1-1 1.7l-.4.3a2 2 0 0 1-2 0l-.2-.1a2 2 0 0 0-2.7.7l-.2.4a2 2 0 0 0 .7 2.7l.2.1a2 2 0 0 1 1 1.7v.5a2 2 0 0 1-1 1.7l-.2.1a2 2 0 0 0-.7 2.7l.2.4a2 2 0 0 0 2.7.7l.2-.1a2 2 0 0 1 2 0l.4.3a2 2 0 0 1 1 1.7v.2a2 2 0 0 0 2 2h.4a2 2 0 0 0 2-2v-.2a2 2 0 0 1 1-1.7l.4-.3a2 2 0 0 1 2 0l.2.1a2 2 0 0 0 2.7-.7l.2-.4a2 2 0 0 0-.7-2.7l-.2-.1a2 2 0 0 1-1-1.7v-.5a2 2 0 0 1 1-1.7l.2-.1a2 2 0 0 0 .7-2.7l-.2-.4a2 2 0 0 0-2.7-.7l-.2.1a2 2 0 0 1-2 0l-.4-.3a2 2 0 0 1-1-1.7V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21v-1a6 6 0 0 1 6-6h4a6 6 0 0 1 6 6v1"/>',
  progress: '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  moon: '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>',
  menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
  logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  checkCircle: '<circle cx="12" cy="12" r="9.5"/><path d="m8 12 3 3 5-6"/>',
  info: '<circle cx="12" cy="12" r="9.5"/><path d="M12 11v6M12 7.5h.01"/>',
  xCircle: '<circle cx="12" cy="12" r="9.5"/><path d="m15 9-6 6M9 9l6 6"/>',
  shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/>',
  sparkle: '<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/><path d="M19 17v4M17 19h4"/>',
  mail: '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-10 6L2 7"/>',
  lock: '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
  eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  eyeOff: '<path d="M9.9 4.2A10 10 0 0 1 12 4c6.5 0 10 8 10 8a17 17 0 0 1-2.2 3.3M6.6 6.6A17 17 0 0 0 2 12s3.5 8 10 8a10 10 0 0 0 5.4-1.6M14.1 14.2a3 3 0 0 1-4.2-4.3M2 2l20 20"/>',
  arrowLeft: '<path d="M19 12H5M12 19l-7-7 7-7"/>',
  refresh: '<path d="M21 12a9 9 0 1 1-2.6-6.4L21 8"/><path d="M21 3v5h-5"/>',
  calendar: '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
  book: '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V3H6.5A2.5 2.5 0 0 0 4 5.5z"/><path d="M4 19.5V21h16"/>',
  clipboard: '<rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="m9 14 2 2 4-4"/>',
  graduation: '<path d="M22 10 12 5 2 10l10 5 10-5z"/><path d="M6 12v5c3 2 9 2 12 0v-5"/>',
};
export const icon = (name, cls = "") => `<svg class="i ${cls}" viewBox="0 0 24 24" aria-hidden="true" focusable="false">${P[name] || ""}</svg>`;
export const LOGO = `<span class="brand-mark" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M3 13.5h3.6l2.2-6 3.8 9.5 2.2-5.5H21"/></svg></span>`;

/* ---------- risk presentation (icon + text, never colour alone) ---------- */
const LEVEL = {
  low: { icon: "✓", label: "Low" },
  moderate: { icon: "▲", label: "Moderate" },
  high: { icon: "◆", label: "High" },
  critical: { icon: "■", label: "Critical" },
  insufficient_data: { icon: "?", label: "Insufficient data" },
  unavailable: { icon: "–", label: "Unavailable" },
};
export const LEVELS = ["critical", "high", "moderate", "low", "insufficient_data", "unavailable"];
export const levelLabel = (l) => (LEVEL[l] || { label: l }).label;

export function riskBadge(level) {
  if (!level) return `<span class="badge lvl-none"><span class="ico" aria-hidden="true">–</span>Not assessed</span>`;
  const m = LEVEL[level] || { icon: "•", label: level };
  return `<span class="badge lvl-${esc(level)}"><span class="ico" aria-hidden="true">${m.icon}</span>${esc(m.label)}</span>`;
}

export function methodTag(a) {
  if (!a) return "";
  if (a.method === "model") return `<span class="tag info" title="Model ${esc(a.model_version)}">Model</span>`;
  if (a.method === "rules_fallback") return `<span class="tag warn">Rule-based (fallback)</span>`;
  if (a.method === "unavailable") return `<span class="tag warn">Unavailable</span>`;
  return `<span class="tag">Not assessed</span>`;
}

export function qualityTag(a) {
  if (!a) return "";
  if (!a.reliable) return `<span class="tag warn" title="${esc((a.warnings || []).join(" "))}">⚠ Data issue</span>`;
  return `<span class="tag ok">Data OK</span>`;
}

/* ---------- people ---------- */
export const initials = (name) => String(name || "?").trim().split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("") || "?";
const hue = (s) => [...String(s || "")].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7) % 6;
export const avatar = (name, size = "") => `<span class="avatar ${size} av-${hue(name)}" aria-hidden="true">${esc(initials(name))}</span>`;
/** Table cell content: avatar + linked name + secondary line. `sub` is escaped. */
export const personCell = (name, href, sub = "") =>
  `<div class="cell-person">${avatar(name, "sm")}<div><a href="${esc(href)}">${esc(name)}</a>${sub ? `<div class="small muted">${esc(sub)}</div>` : ""}</div></div>`;

/* ---------- formatting ---------- */
export const fmtDate = (s) => (s ? new Date(s.length === 10 ? s + "T00:00:00" : s).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" }) : "—");
export const fmtDateTime = (s) => (s ? new Date(s).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "—");
export const pct = (v, d = 0) => (v == null ? "—" : `${(v * 100).toFixed(d)}%`);
export const titleCase = (s) => String(s || "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
export const todayLong = () => new Date().toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric", year: "numeric" });

/* ---------- theme ---------- */
export const getTheme = () => (document.documentElement.dataset.theme === "dark" ? "dark" : "light");
export function setTheme(t) {
  document.documentElement.dataset.theme = t;
  try { localStorage.setItem("saews-theme", t); } catch { /* storage blocked: theme lasts for this page only */ }
  document.dispatchEvent(new CustomEvent("saews:themechange", { detail: { theme: t } }));
}
export function themeToggleButton() {
  return `<button class="icon-btn theme-toggle" type="button" aria-label="Dark theme">${icon("moon", "i-moon")}${icon("sun", "i-sun")}</button>`;
}
/** Wire a theme toggle button: aria-pressed reflects dark mode. */
export function bindThemeToggle(btn) {
  const sync = () => {
    const dark = getTheme() === "dark";
    btn.setAttribute("aria-pressed", String(dark));
    btn.title = dark ? "Switch to light theme" : "Switch to dark theme";
  };
  sync();
  btn.addEventListener("click", () => { setTheme(getTheme() === "dark" ? "light" : "dark"); sync(); });
}

/* ---------- feedback ---------- */
export function toast(message, type = "info") {
  let region = $("#toast-region");
  if (!region) {
    region = document.createElement("div");
    region.id = "toast-region"; region.setAttribute("role", "status"); region.setAttribute("aria-live", "polite");
    document.body.appendChild(region);
  }
  const t = document.createElement("div");
  t.className = `toast ${type}`;
  t.innerHTML = icon(type === "error" ? "xCircle" : type === "success" ? "checkCircle" : "info");
  const text = document.createElement("span");
  text.textContent = message;
  t.appendChild(text);
  region.appendChild(t);
  setTimeout(() => t.remove(), type === "error" ? 7000 : 4000);
}

export function showError(err, target) {
  const msg = err?.message || String(err);
  if (target) target.innerHTML = `<div class="form-error" role="alert">${esc(msg)}</div>`;
  else toast(msg, "error");
}

/* ---------- shell ---------- */
const NAV = [
  { href: "dashboard.html", label: "Dashboard", icon: "dashboard", group: "Overview", roles: ["admin", "teacher", "advisor"] },
  { href: "alerts.html", label: "Alerts", icon: "alert", group: "Overview", roles: ["admin", "teacher", "advisor"] },
  { href: "students.html", label: "Students", icon: "users", group: "Overview", roles: ["admin", "teacher", "advisor"] },
  { href: "me.html", label: "My Progress", icon: "progress", group: "Overview", roles: ["student"] },
  { href: "interventions.html", label: "Support & Requests", icon: "support", group: "Support", roles: ["admin", "teacher", "advisor"] },
  { href: "imports.html", label: "Data Import", icon: "upload", group: "Data", roles: ["admin", "teacher"] },
  { href: "reports.html", label: "Reports", icon: "chart", group: "Data", roles: ["admin", "teacher", "advisor", "analyst"] },
  { href: "admin.html", label: "Administration", icon: "settings", group: "System", roles: ["admin"] },
];

export const homeFor = (role) => ({ student: "me.html", analyst: "reports.html" }[role] || "dashboard.html");

function navHtml(role, page) {
  const groups = new Map();
  for (const n of NAV.filter((x) => x.roles.includes(role))) {
    if (!groups.has(n.group)) groups.set(n.group, []);
    groups.get(n.group).push(n);
  }
  return [...groups].map(([g, items]) => `<div class="nav-group" role="group" aria-label="${esc(g)}"><div class="nav-label" aria-hidden="true">${esc(g)}</div>
    ${items.map((n) => `<a href="${n.href}"${n.href === page ? ' aria-current="page"' : ""}>${icon(n.icon)}<span>${esc(n.label)}</span></a>`).join("")}</div>`).join("");
}

/** Authenticate, enforce page roles client-side (server enforces again), render sidebar + app bar. */
export async function initShell(page, allowedRoles) {
  let user;
  try { ({ user } = await api("/auth/me")); } catch { return null; }
  if (allowedRoles && !allowedRoles.includes(user.role)) { location.replace(homeFor(user.role)); return null; }
  const current = NAV.find((n) => n.href === page);
  const main = $("#main");

  const skip = document.createElement("a");
  skip.className = "skip-link"; skip.href = "#main"; skip.textContent = "Skip to content";

  const sidebar = document.createElement("aside");
  sidebar.className = "sidebar"; sidebar.id = "sidebar";
  sidebar.setAttribute("aria-label", "Sidebar");
  sidebar.innerHTML = `
    <a class="brand" href="${homeFor(user.role)}">${LOGO}<span class="brand-name">SAEWS<small>Early Warning &amp; Decision Support</small></span></a>
    <nav class="nav" aria-label="Main">${navHtml(user.role, page)}</nav>
    <div class="side-foot">${icon("shield")}<span>Risk levels are estimates. They support, and never replace, professional judgement.</span></div>`;

  const content = document.createElement("div");
  content.className = "app-content";
  content.innerHTML = `
    <header class="appbar">
      <button class="icon-btn menu-btn" type="button" aria-label="Open navigation" aria-controls="sidebar" aria-expanded="false">${icon("menu")}</button>
      <div class="crumbs"><span class="root">SAEWS</span><span class="sep" aria-hidden="true">/</span><strong>${esc(current?.label || document.title.split("·")[0].trim())}</strong></div>
      <div class="appbar-actions">
        ${themeToggleButton()}
        <span class="divider-v" aria-hidden="true"></span>
        <div class="user-chip">${avatar(user.full_name, "sm")}<div class="user-meta"><span class="name">${esc(user.full_name)}</span><span class="role">${esc(user.role)}</span></div></div>
        <button class="btn small secondary" id="logout-btn" type="button">${icon("logout")}<span class="logout-text">Sign out</span></button>
      </div>
    </header>`;
  const backdrop = document.createElement("div");
  backdrop.className = "backdrop";

  document.body.classList.add("has-shell");
  document.body.prepend(skip, sidebar, content, backdrop);
  if (main) content.appendChild(main);
  $("#logout-btn").setAttribute("aria-label", "Sign out");

  bindThemeToggle($(".appbar .theme-toggle"));
  $("#logout-btn").addEventListener("click", async () => { await api("/auth/logout", { method: "POST" }); location.href = "index.html"; });

  // mobile drawer
  const menuBtn = $(".menu-btn");
  const setOpen = (open) => {
    document.body.classList.toggle("nav-open", open);
    menuBtn.setAttribute("aria-expanded", String(open));
    menuBtn.setAttribute("aria-label", open ? "Close navigation" : "Open navigation");
    if (open) sidebar.querySelector("a")?.focus(); else menuBtn.focus();
  };
  menuBtn.addEventListener("click", () => setOpen(!document.body.classList.contains("nav-open")));
  backdrop.addEventListener("click", () => setOpen(false));
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && document.body.classList.contains("nav-open")) setOpen(false); });
  return user;
}

export function emptyRow(cols, text = "Nothing to show.") {
  return `<tr><td colspan="${cols}" class="empty">${esc(text)}</td></tr>`;
}

export const qs = (k) => new URLSearchParams(location.search).get(k);
