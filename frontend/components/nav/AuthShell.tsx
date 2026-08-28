import { ReactNode } from "react";

export function AuthShell({ title, subtitle, children }: { title: string; subtitle?: string; children: ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-base px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <div className="font-mono text-sm font-bold tracking-tight text-ink">CRIME PUMP</div>
          <div className="font-mono text-[10px] tracking-widest text-ink-faint">EARLY DETECTOR</div>
        </div>
        <div className="rounded border border-base-border bg-base-panel p-6">
          <h1 className="mb-1 text-lg font-semibold text-ink">{title}</h1>
          {subtitle && <p className="mb-5 text-sm text-ink-muted">{subtitle}</p>}
          {children}
        </div>
        <p className="mt-4 text-center text-xs text-ink-faint">
          Research alerts only. Not financial advice. No automated trading.
        </p>
      </div>
    </div>
  );
}
