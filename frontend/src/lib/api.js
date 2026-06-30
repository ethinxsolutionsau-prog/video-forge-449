import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

export const api = axios.create({
  baseURL: API,
  withCredentials: true,
});

// Paths that are EXPECTED to 401 when there is no session (do NOT redirect on these).
const AUTH_PROBE_PATHS = ["/auth/me", "/auth/login", "/auth/register", "/auth/forgot-password", "/auth/reset-password"];

function isAuthProbe(url) {
  if (!url) return false;
  return AUTH_PROBE_PATHS.some((p) => url.includes(p));
}

// Global 401 handler: clean redirect to /login (preserving returnTo) rather than
// letting the UI hang in a broken authenticated state when the session expires.
let isRedirecting = false;
api.interceptors.response.use(
  (resp) => resp,
  (err) => {
    const status = err?.response?.status;
    const url = err?.config?.url || "";
    if (status === 401 && !isAuthProbe(url) && !isRedirecting) {
      const path = window.location.pathname + window.location.search;
      // Don't redirect if already on a public route
      const onPublicRoute = ["/login", "/register", "/forgot-password", "/reset-password", "/"].some(
        (p) => window.location.pathname === p || window.location.pathname.startsWith("/s/")
      );
      if (!onPublicRoute) {
        isRedirecting = true;
        const returnTo = encodeURIComponent(path);
        // Replace so back-button doesn't loop the broken page
        window.location.replace(`/login?returnTo=${returnTo}&reason=session_expired`);
      }
    }
    return Promise.reject(err);
  }
);

export function formatApiError(detail) {
  if (detail == null) return "Something went wrong. Please try again.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((e) => (e && typeof e.msg === "string" ? e.msg : JSON.stringify(e)))
      .filter(Boolean)
      .join(" ");
  }
  if (detail && typeof detail.msg === "string") return detail.msg;
  return String(detail);
}
