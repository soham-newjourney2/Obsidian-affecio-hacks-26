// Session in sessionStorage (per tab, D04) and route guards.
const KEY = "echo.session";

export function saveSession({ access_token: token, expires_in: expiresIn, user }) {
  try {
    sessionStorage.setItem(KEY, JSON.stringify({ token, user, expiresAt: Date.now() + expiresIn * 1000 }));
  } catch {
    // Storage blocked: the session lasts only as long as this page.
  }
}

function readSession() {
  try {
    const session = JSON.parse(sessionStorage.getItem(KEY));
    if (session?.token && session.expiresAt > Date.now()) return session;
  } catch {
    // fall through
  }
  return null;
}

export function getToken() {
  return readSession()?.token ?? null;
}

export function getUser() {
  return readSession()?.user ?? null;
}

export function clearSession() {
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    // nothing to clear
  }
}

// Only same-origin paths: blocks open redirects like "//evil.example" or "https://…".
export function safeNext(raw, fallback = "/lobby.html") {
  if (typeof raw !== "string" || !raw.startsWith("/") || raw.startsWith("//") || raw.includes("\\")) {
    return fallback;
  }
  return raw;
}

export function redirectToLogin() {
  const next = encodeURIComponent(location.pathname + location.search);
  location.replace(`/auth.html?next=${next}`);
}

// For pages that need a signed-in user. Returns the user, or null after redirecting.
export function requireSession() {
  const user = getUser();
  if (!user) redirectToLogin();
  return user;
}
