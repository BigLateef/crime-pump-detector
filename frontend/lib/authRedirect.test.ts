/**
 * No test runner (jest/vitest) is configured in package.json yet, so
 * this file can't be executed directly via `npm test`. The logic it
 * covers WAS actually run and verified — a plain-Node transliteration of
 * these exact assertions was executed directly (not just syntax-checked)
 * during development; see the project's final report for that run's
 * output. Once a test runner is added, this file should run as-is.
 */
import { isAuthPage, safeNextPath, AUTH_PAGES } from "./authRedirect";

describe("safeNextPath", () => {
  it("preserves a normal in-app path", () => {
    expect(safeNextPath("/tokens/abc123")).toBe("/tokens/abc123");
  });

  it("falls back to /scanner for null/undefined/empty", () => {
    expect(safeNextPath(null)).toBe("/scanner");
    expect(safeNextPath(undefined)).toBe("/scanner");
    expect(safeNextPath("")).toBe("/scanner");
  });

  it("rejects an absolute external URL (open-redirect prevention)", () => {
    expect(safeNextPath("https://evil.com/phish")).toBe("/scanner");
  });

  it("rejects a protocol-relative external URL", () => {
    expect(safeNextPath("//evil.com/phish")).toBe("/scanner");
  });

  it("rejects redirecting back to an auth page (loop prevention)", () => {
    expect(safeNextPath("/login")).toBe("/scanner");
    expect(safeNextPath("/login?next=%2Fscanner")).toBe("/scanner");
  });

  it("preserves a nested admin path", () => {
    expect(safeNextPath("/admin/backtesting/datasets")).toBe("/admin/backtesting/datasets");
  });
});

describe("isAuthPage", () => {
  it("is true for every page in AUTH_PAGES", () => {
    for (const page of AUTH_PAGES) {
      expect(isAuthPage(page)).toBe(true);
    }
  });

  it("is true for an auth page with a query string", () => {
    expect(isAuthPage("/invite?code=ABC")).toBe(true);
  });

  it("is false for a non-auth page", () => {
    expect(isAuthPage("/scanner")).toBe(false);
    expect(isAuthPage("/admin/users")).toBe(false);
  });
});
