import clsx from "clsx";
import { DataQuality } from "@/lib/types";

const STYLES: Record<DataQuality, string> = {
  VERIFIED: "bg-signal-conviction/15 text-signal-conviction border-signal-conviction/30",
  DEMO: "bg-signal-watch/15 text-signal-watch border-signal-watch/30",
  ESTIMATED: "bg-signal-early/15 text-signal-early border-signal-early/30",
  UNAVAILABLE: "bg-signal-avoid/15 text-signal-avoid border-signal-avoid/30",
};

const LABELS: Record<DataQuality, string> = {
  VERIFIED: "VERIFIED",
  DEMO: "DEMO DATA",
  ESTIMATED: "ESTIMATED",
  UNAVAILABLE: "UNAVAILABLE",
};

export function DataQualityBadge({ quality }: { quality: DataQuality }) {
  return (
    <span
      className={clsx(
        "inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-mono font-semibold tracking-wide",
        STYLES[quality]
      )}
    >
      {LABELS[quality]}
    </span>
  );
}
