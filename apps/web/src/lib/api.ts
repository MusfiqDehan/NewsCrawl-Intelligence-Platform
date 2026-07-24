const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const TOKEN_KEY = "newscrawl_token";
const REFRESH_KEY = "newscrawl_refresh_token";
const EXPIRES_AT_KEY = "newscrawl_token_expires_at";
export const AUTH_CHANGE_EVENT = "newscrawl-auth";

type TokenBundle = {
  access_token: string;
  refresh_token: string;
  expires_in_minutes: number;
};

let refreshInFlight: Promise<boolean> | null = null;
let proactiveRefreshTimer: ReturnType<typeof setTimeout> | null = null;

function notifyAuthChange() {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event(AUTH_CHANGE_EVENT));
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(REFRESH_KEY);
}

/** @deprecated Prefer setSession — kept for call-site compatibility. */
export function setToken(token: string) {
  window.localStorage.setItem(TOKEN_KEY, token);
  notifyAuthChange();
}

export function setSession(bundle: TokenBundle) {
  const expiresAt = Date.now() + bundle.expires_in_minutes * 60_000;
  window.localStorage.setItem(TOKEN_KEY, bundle.access_token);
  window.localStorage.setItem(REFRESH_KEY, bundle.refresh_token);
  window.localStorage.setItem(EXPIRES_AT_KEY, String(expiresAt));
  notifyAuthChange();
  scheduleProactiveRefresh(bundle.expires_in_minutes);
}

export function clearToken() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(REFRESH_KEY);
  window.localStorage.removeItem(EXPIRES_AT_KEY);
  if (proactiveRefreshTimer) {
    clearTimeout(proactiveRefreshTimer);
    proactiveRefreshTimer = null;
  }
  notifyAuthChange();
}

export function subscribeToAuth(callback: () => void): () => void {
  const onStorage = (event: StorageEvent) => {
    if (
      event.key === TOKEN_KEY ||
      event.key === REFRESH_KEY ||
      event.key === EXPIRES_AT_KEY ||
      event.key === null
    ) {
      callback();
    }
  };
  const onAuth = () => callback();
  window.addEventListener("storage", onStorage);
  window.addEventListener(AUTH_CHANGE_EVENT, onAuth);
  return () => {
    window.removeEventListener("storage", onStorage);
    window.removeEventListener(AUTH_CHANGE_EVENT, onAuth);
  };
}

function scheduleProactiveRefresh(expiresInMinutes: number) {
  if (typeof window === "undefined") return;
  if (proactiveRefreshTimer) clearTimeout(proactiveRefreshTimer);
  // Refresh a couple of minutes before expiry (or halfway for very short TTLs).
  const refreshInMs = Math.max(
    30_000,
    expiresInMinutes * 60_000 - 120_000,
  );
  proactiveRefreshTimer = setTimeout(() => {
    void refreshSession();
  }, refreshInMs);
}

export function bootstrapSessionRefresh() {
  if (typeof window === "undefined") return;
  const raw = window.localStorage.getItem(EXPIRES_AT_KEY);
  const refresh = getRefreshToken();
  if (!refresh) return;
  if (!raw) {
    void refreshSession();
    return;
  }
  const expiresAt = Number(raw);
  if (!Number.isFinite(expiresAt)) {
    void refreshSession();
    return;
  }
  const msLeft = expiresAt - Date.now();
  if (msLeft <= 120_000) {
    void refreshSession();
    return;
  }
  scheduleProactiveRefresh(msLeft / 60_000);
}

async function refreshSession(): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight;

  refreshInFlight = (async () => {
    const refreshToken = getRefreshToken();
    if (!refreshToken) return false;

    try {
      const res = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (!res.ok) return false;
      const body = (await res.json()) as TokenBundle;
      if (!body.access_token || !body.refresh_token) return false;
      setSession(body);
      return true;
    } catch {
      return false;
    }
  })();

  try {
    return await refreshInFlight;
  } finally {
    refreshInFlight = null;
  }
}

function forceLogout() {
  clearToken();
  if (typeof window !== "undefined" && window.location.pathname !== "/login") {
    window.location.href = "/login";
  }
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

type ApiOptions = RequestInit & {
  params?: Record<string, string | number | boolean | undefined>;
  /** Skip bearer auth + 401 refresh handling (login/refresh). */
  skipAuth?: boolean;
};

async function parseErrorDetail(res: Response): Promise<string> {
  let detail = res.statusText;
  try {
    const body = await res.json();
    detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
  } catch {
    // non-JSON error body
  }
  return detail;
}

export async function api<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const { params, skipAuth = false, ...init } = options;
  const url = new URL(`${API_BASE}/api/v1${path}`);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== "") url.searchParams.set(key, String(value));
    }
  }

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string>),
  };
  if (!skipAuth) {
    const token = getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }

  const res = await fetch(url.toString(), { ...init, headers });

  if (res.status === 401 && !skipAuth && typeof window !== "undefined") {
    const refreshed = await refreshSession();
    if (refreshed) {
      const retryHeaders: Record<string, string> = {
        "Content-Type": "application/json",
        ...(init.headers as Record<string, string>),
      };
      const newToken = getToken();
      if (newToken) retryHeaders.Authorization = `Bearer ${newToken}`;
      const retry = await fetch(url.toString(), { ...init, headers: retryHeaders });
      if (!retry.ok) {
        if (retry.status === 401) forceLogout();
        throw new ApiError(retry.status, await parseErrorDetail(retry));
      }
      return retry.json() as Promise<T>;
    }
    forceLogout();
  }

  if (!res.ok) {
    throw new ApiError(res.status, await parseErrorDetail(res));
  }
  return res.json() as Promise<T>;
}

export async function logoutRemote() {
  const refreshToken = getRefreshToken();
  if (refreshToken) {
    try {
      await fetch(`${API_BASE}/api/v1/auth/logout`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
    } catch {
      // Best-effort revoke; local clear still happens.
    }
  }
  clearToken();
}
