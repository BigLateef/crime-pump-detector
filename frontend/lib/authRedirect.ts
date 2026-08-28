// Pages a 401-driven redirect must never target or fire from — prevents
// a loop where /login itself (or another public auth page) triggers
// another redirect to /login.
export const AUTH_PAGES = ["/login", "/signup", "/invite"];

export function isAuthPage(path: string): boolean {
  return AUTH_PAGES.some((p) => path === p || path.startsWith(p + "?"));
}

/**
 * Only ever redirect to a same-origin, in-app path — never let a "next"
 * value taken from a URL become an open redirect to an external site.
 * Rejects: missing values, protocol-relative URLs ("//evil.com", which
 * browsers treat as external), absolute URLs, and auth pages themselves
 * (which would otherwise create a loop: login -> redirect to next=/login
 * -> ...).
 */
export function safeNextPath(path: string | null | undefined): string {
  if (!path) return "/scanner";
  if (!path.startsWith("/") || path.startsWith("//")) return "/scanner";
  if (isAuthPage(path)) return "/scanner";
  return path;
}
