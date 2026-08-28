import clsx from "clsx";

const STYLES: Record<string, string> = {
  verified: "bg-signal-conviction/15 text-signal-conviction border-signal-conviction/30",
  cached: "bg-signal-early/15 text-signal-early border-signal-early/30",
  demo: "bg-signal-watch/15 text-signal-watch border-signal-watch/30",
  unavailable: "bg-signal-avoid/15 text-signal-avoid border-signal-avoid/30",
  failed: "bg-signal-danger/15 text-signal-danger border-signal-danger/30",
};

const LABELS: Record<string, string> = {
  verified: "LIVE",
  cached: "CACHED",
  demo: "DEMO DATA",
  unavailable: "UNAVAILABLE",
  failed: "FETCH FAILED",
};

export function DataStatusBadge({ status }: { status: string }) {
  const style = STYLES[status] || STYLES.unavailable;
  const label = LABELS[status] || status.toUpperCase();
  return (
    <span className={clsx("inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-mono font-semibold tracking-wide", style)}>
      {label}
    </span>
  );
}
