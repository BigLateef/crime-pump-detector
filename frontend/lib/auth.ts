// Access/refresh tokens live in localStorage. This is a real Next.js app
// (not a claude.ai artifact preview), so browser storage APIs are
// available and appropriate here — the "no localStorage" restriction only
// applies to in-chat artifact previews.

const ACCESS_KEY = "cped_access_token";
const REFRESH_KEY = "cped_refresh_token";

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(ACCESS_KEY);
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(REFRESH_KEY);
}

export function setTokens(access: string, refresh: string): void {
  window.localStorage.setItem(ACCESS_KEY, access);
  window.localStorage.setItem(REFRESH_KEY, refresh);
}

export function clearTokens(): void {
  window.localStorage.removeItem(ACCESS_KEY);
  window.localStorage.removeItem(REFRESH_KEY);
}
