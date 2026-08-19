import { ReactNode } from "react";
import clsx from "clsx";

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={clsx("rounded border border-base-border bg-base-panel p-4", className)}>{children}</div>
  );
}

export function CardHeader({ title, action }: { title: string; action?: ReactNode }) {
  return (
    <div className="mb-3 flex items-center justify-between">
      <h2 className="font-mono text-sm font-semibold uppercase tracking-wide text-ink-muted">{title}</h2>
      {action}
    </div>
  );
}

export function StatBox({ label, value, sub }: { label: string; value: ReactNode; sub?: string }) {
  return (
    <div className="rounded border border-base-border bg-base-panel2 p-3">
      <div className="text-xs uppercase tracking-wide text-ink-faint">{label}</div>
      <div className="mt-1 font-mono text-xl font-semibold text-ink">{value}</div>
      {sub && <div className="mt-0.5 text-xs text-ink-muted">{sub}</div>}
    </div>
  );
}

export function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="flex flex-col items-center justify-center rounded border border-dashed border-base-border py-16 text-center">
      <div className="font-mono text-sm font-medium text-ink">{title}</div>
      <div className="mt-1 max-w-sm text-sm text-ink-muted">{body}</div>
    </div>
  );
}

export function Button({
  children,
  onClick,
  variant = "primary",
  type = "button",
  disabled,
  className,
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "primary" | "secondary" | "danger";
  type?: "button" | "submit";
  disabled?: boolean;
  className?: string;
}) {
  // min-h-[44px] keeps every button at or above the standard 44px touch
  // target (WCAG 2.5.5 / Apple HIG) on mobile, without changing the
  // visual size on desktop - flex+items-center just keeps text vertically
  // centered inside the taller tap area instead of top-aligned.
  const base =
    "flex min-h-[44px] items-center justify-center rounded px-3 py-2 text-sm font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed";
  const styles = {
    primary: "bg-signal-early text-white hover:bg-signal-early/90",
    secondary: "bg-base-panel2 text-ink border border-base-border hover:border-ink-faint",
    danger: "bg-signal-danger/15 text-signal-danger border border-signal-danger/30 hover:bg-signal-danger/25",
  };
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={clsx(base, styles[variant], className)}
    >
      {children}
    </button>
  );
}

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={clsx(
        "min-h-[44px] w-full rounded border border-base-border bg-base-panel2 px-3 py-2 text-sm text-ink placeholder:text-ink-faint focus:border-signal-early focus:outline-none",
        props.className
      )}
    />
  );
}
