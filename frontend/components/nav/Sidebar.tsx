"use client";

import { useEffect, useRef } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import clsx from "clsx";
import { useAuth } from "@/lib/auth-context";

const NAV_ITEMS = [
  { href: "/scanner", label: "Live scanner" },
  { href: "/opportunities", label: "Ranked opportunities" },
  { href: "/alerts", label: "Alert history" },
  { href: "/paper-trading", label: "Paper trading" },
  { href: "/backtesting", label: "Backtesting" },
];

const SETTINGS_ITEMS = [
  { href: "/settings/preferences", label: "Preferences" },
  { href: "/settings/discord", label: "Discord alerts" },
];

const ADMIN_ITEMS = [
  { href: "/admin/invites", label: "Invites" },
  { href: "/admin/users", label: "Users" },
  { href: "/admin/health", label: "System health" },
  { href: "/admin/data-sources", label: "Data sources" },
  { href: "/admin/backtesting/datasets", label: "Backtest datasets" },
];

function NavLink({ href, label, onNavigate }: { href: string; label: string; onNavigate?: () => void }) {
  const pathname = usePathname();
  const active = pathname === href || pathname.startsWith(href + "/");
  return (
    <Link
      href={href}
      onClick={onNavigate}
      className={clsx(
        "block rounded px-3 py-2 text-sm transition-colors",
        active ? "bg-base-panel2 text-ink font-medium" : "text-ink-muted hover:bg-base-panel2 hover:text-ink"
      )}
    >
      {label}
    </Link>
  );
}

function NavSection({
  title,
  items,
  onNavigate,
}: {
  title: string;
  items: { href: string; label: string }[];
  onNavigate?: () => void;
}) {
  return (
    <div>
      <div className="mb-1 px-3 text-xs font-mono uppercase tracking-wider text-ink-faint">{title}</div>
      <div className="space-y-0.5">
        {items.map((item) => (
          <NavLink key={item.href} {...item} onNavigate={onNavigate} />
        ))}
      </div>
    </div>
  );
}

/**
 * Shared inner content for both the permanent desktop rail and the mobile
 * drawer. `onNavigate` closes the drawer after a link tap on mobile; it's
 * undefined on desktop since there's nothing to close.
 */
function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const { user, logout } = useAuth();

  return (
    <>
      <div className="mb-6 px-3">
        <div className="font-mono text-sm font-bold tracking-tight text-ink">CRIME PUMP</div>
        <div className="font-mono text-[10px] tracking-widest text-ink-faint">EARLY DETECTOR</div>
      </div>

      <nav className="flex-1 space-y-5 overflow-y-auto">
        <NavSection title="Research" items={NAV_ITEMS} onNavigate={onNavigate} />
        <NavSection title="Settings" items={SETTINGS_ITEMS} onNavigate={onNavigate} />
        {user?.role === "admin" && <NavSection title="Admin" items={ADMIN_ITEMS} onNavigate={onNavigate} />}
      </nav>

      <div className="mt-4 border-t border-base-border pt-3 px-3">
        <div className="truncate text-xs text-ink-muted">{user?.display_name}</div>
        <div className="truncate text-[11px] text-ink-faint">{user?.email}</div>
        <button onClick={logout} className="mt-2 text-xs text-signal-danger hover:underline">
          Log out
        </button>
      </div>
    </>
  );
}

/**
 * Permanent sidebar rail, desktop only (md and up). Unchanged in spirit
 * from the original component - just renamed internally and hidden below
 * the mobile breakpoint, since mobile gets the drawer variant instead.
 */
export function Sidebar() {
  return (
    <aside className="hidden h-screen w-60 flex-col border-r border-base-border bg-base-panel px-3 py-4 md:flex">
      <SidebarContent />
    </aside>
  );
}

/**
 * Mobile drawer variant of the sidebar. Slides in from the left, below an
 * overlay that closes it on tap. Only rendered/interactive below the
 * mobile breakpoint - desktop always uses the permanent <Sidebar /> rail
 * instead, so this component intentionally does nothing when `open` is
 * false other than stay unmounted from the accessibility tree.
 */
export function MobileSidebarDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const drawerRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  // Close on Escape, lock background scroll, and move focus into the
  // drawer while it's open - restores focus to whatever was focused
  // before opening (the hamburger button) once it closes.
  useEffect(() => {
    if (!open) return;

    const previouslyFocused = document.activeElement as HTMLElement | null;
    closeButtonRef.current?.focus();

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        onClose();
        return;
      }
      // Basic focus trap: keep Tab cycling within the drawer while open.
      if (e.key === "Tab" && drawerRef.current) {
        const focusable = drawerRef.current.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])'
        );
        if (focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
      previouslyFocused?.focus();
    };
  }, [open, onClose]);

  return (
    <div
      aria-hidden={!open}
      className={clsx(
        "fixed inset-0 z-40 md:hidden",
        open ? "pointer-events-auto" : "pointer-events-none"
      )}
    >
      {/* Overlay - tapping it closes the drawer. Fades in/out with the drawer. */}
      <div
        onClick={onClose}
        className={clsx(
          "absolute inset-0 bg-black/60 transition-opacity duration-200",
          open ? "opacity-100" : "opacity-0"
        )}
      />

      {/* Drawer panel itself. Does not permanently cover content - it's an
          overlay above the page, and the page underneath is unaffected
          once closed (no layout shift, no persistent occlusion). */}
      <div
        ref={drawerRef}
        role="dialog"
        aria-modal="true"
        aria-label="Navigation menu"
        className={clsx(
          "absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col border-r border-base-border bg-base-panel px-3 py-4 shadow-xl transition-transform duration-200",
          open ? "translate-x-0" : "-translate-x-full"
        )}
      >
        <div className="mb-2 flex items-center justify-end">
          <button
            ref={closeButtonRef}
            onClick={onClose}
            aria-label="Close navigation menu"
            className="flex min-h-[44px] min-w-[44px] items-center justify-center rounded text-ink-muted hover:bg-base-panel2 hover:text-ink"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth={2}
              className="h-5 w-5"
              aria-hidden="true"
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <SidebarContent onNavigate={onClose} />
      </div>
    </div>
  );
}
