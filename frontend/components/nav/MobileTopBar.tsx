"use client";

export function MobileTopBar({ onOpenMenu }: { onOpenMenu: () => void }) {
  return (
    <div className="flex items-center gap-3 border-b border-base-border bg-base-panel px-3 py-3 md:hidden">
      <button
        onClick={onOpenMenu}
        aria-label="Open navigation menu"
        className="flex min-h-[44px] min-w-[44px] items-center justify-center rounded text-ink-muted hover:bg-base-panel2 hover:text-ink"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          className="h-6 w-6"
          aria-hidden="true"
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5M3.75 17.25h16.5" />
        </svg>
      </button>
      <div className="font-mono text-sm font-bold tracking-tight text-ink">CRIME PUMP</div>
    </div>
  );
}
