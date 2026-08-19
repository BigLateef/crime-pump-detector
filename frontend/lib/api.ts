import { clearTokens, getAccessToken, getRefreshToken, setTokens } from "./auth";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

// Registered by AuthProvider (lib/auth-context.tsx) on mount. api.ts is a
// plain module, not a React component, so it can't call useRouter()
// itself — instead it calls back into AuthProvider, which owns the
// actual navigation and loop-prevention logic. If nothing has registered
// a handler yet (e.g. a fetch fires before AuthProvider mounts), the
// session is still cleared — the next render's own auth check catches it.
type UnauthorizedHandler = (currentPath: string) => void;
let unauthorizedHandler: UnauthorizedHandler | null = null;

export function setUnauthorizedHandler(handler: UnauthorizedHandler | null): void {
  unauthorizedHandler = handler;
}

async function tryRefresh(): Promise<boolean> {
  const refresh_token = getRefreshToken();
  if (!refresh_token) return false;
  try {
    const resp = await fetch(`${BASE_URL}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token }),
    });
    if (!resp.ok) return false;
    const data = await resp.json();
    setTokens(data.access_token, data.refresh_token);
    return true;
  } catch {
    // Network error talking to /auth/refresh itself - treat the same as
    // a failed refresh rather than letting the exception propagate out
    // of apiFetch uncaught.
    return false;
  }
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  auth?: boolean; // defaults to true
}

export async function apiFetch<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, auth = true } = opts;

  const doFetch = async (): Promise<Response> => {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (auth) {
      const token = getAccessToken();
      if (token) headers["Authorization"] = `Bearer ${token}`;
    }
    try {
      return await fetch(`${BASE_URL}${path}`, {
        method,
        headers,
        body: body !== undefined ? JSON.stringify(body) : undefined,
      });
    } catch {
      // The browser never got an HTTP response at all - either the API is
      // unreachable, or (very commonly in practice) it responded but the
      // browser blocked the response before JS ever saw it because the
      // origin isn't in the backend's ALLOWED_ORIGINS. A bare "Failed to
      // fetch" TypeError here gives no indication which, so surface a
      // status-0 ApiError with a message pointing at both possibilities
      // instead of letting an unhandled network exception reach the caller.
      throw new ApiError(
        0,
        `Could not reach the API at ${BASE_URL}. This is usually either the backend being unreachable, or a CORS misconfiguration (the backend's ALLOWED_ORIGINS must include this exact origin).`
      );
    }
  };

  let resp = await doFetch();

  if (resp.status === 401 && auth) {
    const refreshed = await tryRefresh();
    if (refreshed) {
      resp = await doFetch();
    } else {
      // Refresh genuinely failed (expired/revoked refresh token, or no
      // refresh token at all) - the session is unrecoverable. Clear it
      // and hand off to AuthProvider to redirect, rather than leaving the
      // caller with a silent 401 and stale UI.
      clearTokens();
      if (unauthorizedHandler && typeof window !== "undefined") {
        unauthorizedHandler(window.location.pathname + window.location.search);
      }
    }
  }

  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const errBody = await resp.json();
      detail = errBody.detail || detail;
    } catch {
      // response wasn't JSON — keep statusText
    }
    throw new ApiError(resp.status, detail);
  }

  if (resp.status === 204) return undefined as T;
  return resp.json() as Promise<T>;
}
