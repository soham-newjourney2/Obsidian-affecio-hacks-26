// JSON client for /api/v1: bearer auth, normalized errors, 401 → back to sign-in.
import { clearSession, getToken, redirectToLogin } from "./auth.js";
import { STRINGS, t } from "./strings.js";

const BASE = "/api/v1";

export class ApiError extends Error {
  constructor(status, code, requestId = null) {
    super(code in STRINGS.errors ? t(`errors.${code}`) : t(status === 0 ? "errors.network" : "errors.generic"));
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }
}

export async function api(path, { method = "GET", body, auth = true } = {}) {
  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (auth) {
    const token = getToken();
    if (!token) {
      redirectToLogin();
      throw new ApiError(401, "UNAUTHORIZED");
    }
    headers.Authorization = `Bearer ${token}`;
  }

  let res;
  try {
    res = await fetch(BASE + path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: "same-origin",
    });
  } catch {
    throw new ApiError(0, "NETWORK");
  }

  if (res.status === 204) return null;
  let data = null;
  try {
    data = await res.json();
  } catch {
    // non-JSON body; handled below
  }
  if (!res.ok) {
    const error = data?.error ?? {};
    if (res.status === 401 && auth) {
      clearSession();
      redirectToLogin();
    }
    throw new ApiError(res.status, error.code ?? `HTTP_${res.status}`, error.request_id ?? null);
  }
  return data;
}

export async function signOut() {
  if (getToken()) {
    try {
      await api("/auth/logout", { method: "POST" });
    } catch {
      // The token is dropped locally either way.
    }
  }
  clearSession();
  location.assign("/");
}
