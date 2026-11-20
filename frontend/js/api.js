// Thin fetch wrapper. Session is an HttpOnly cookie, so no token is ever exposed to JavaScript.
export class ApiError extends Error {
  constructor(status, message, data) { super(message); this.status = status; this.data = data; }
}

function detailMessage(data, fallback) {
  if (!data) return fallback;
  if (typeof data.detail === "string") return data.detail;
  if (Array.isArray(data.detail)) return data.detail.map(d => `${(d.loc || []).slice(1).join(".")}: ${d.msg}`).join("; ");
  if (data.error) return data.error;
  return fallback;
}

const onLoginPage = () => /(^|\/)(index\.html)?$/.test(location.pathname);

export async function api(path, { method = "GET", body, form, raw = false, redirectOn401 = true } = {}) {
  const opts = { method, credentials: "same-origin", headers: { Accept: "application/json" } };
  if (form) opts.body = form;
  else if (body !== undefined) { opts.body = JSON.stringify(body); opts.headers["Content-Type"] = "application/json"; }
  const res = await fetch(`/api${path}`, opts);
  // Redirect to sign-in on an expired session — but never from the sign-in page itself (would loop).
  if (res.status === 401 && redirectOn401 && !path.startsWith("/auth/login") && !onLoginPage()) {
    location.href = `index.html?next=${encodeURIComponent(location.pathname.split("/").pop() + location.search)}`;
    throw new ApiError(401, "Session expired");
  }
  if (raw) {
    if (!res.ok) throw new ApiError(res.status, detailMessage(await res.json().catch(() => null), res.statusText));
    return res;
  }
  if (res.status === 204) return null;
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, detailMessage(data, `Request failed (${res.status})`), data);
  return data;
}

export async function download(path, fallbackName) {
  const res = await api(path, { raw: true });
  const blob = await res.blob();
  const cd = res.headers.get("Content-Disposition") || "";
  const m = cd.match(/filename="([^"]+)"/);
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = m ? m[1] : fallbackName;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
