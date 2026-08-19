import clsx from "clsx";
import { SignalLevel } from "@/lib/types";

const STYLES: Record<SignalLevel, string> = {
  "HIGH-CONVICTION": "bg-signal-conviction/15 text-signal-conviction border-signal-conviction/30",
  EARLY: "bg-signal-early/15 text-signal-early border-signal-early/30",
  WATCH: "bg-signal-watch/15 text-signal-watch border-signal-watch/30",
  AVOID: "bg-signal-avoid/15 text-signal-avoid border-signal-avoid/30",
  EXIT_DANGER: "bg-signal-danger/15 text-signal-danger border-signal-danger/30",
};

export function SignalBadge({ level }: { level: SignalLevel }) {
  return (
    <span
      className={clsx(
        "inline-flex items-center rounded border px-2 py-0.5 text-xs font-mono font-medium tracking-wide",
        STYLES[level]
      )}
    >
      {level}
    </span>
  );
}
