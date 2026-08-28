import clsx from "clsx";
import { SignalLevel } from "@/lib/types";

const COLOR_BY_LEVEL: Record<SignalLevel, string> = {
  "HIGH-CONVICTION": "bg-signal-conviction",
  EARLY: "bg-signal-early",
  WATCH: "bg-signal-watch",
  AVOID: "bg-signal-avoid",
  EXIT_DANGER: "bg-signal-danger",
};

const SEGMENTS = 20;

/**
 * The product's whole pitch is "transparent, explainable scoring" — so the
 * score is never just a number. It's rendered as a segmented meter (like a
 * scanner readout), each segment worth 5 points, filled up to the score
 * and colored by the resulting signal level. Reused at three sizes across
 * the scanner table, opportunity cards, and the token detail header.
 */
export function ScoreGauge({
  score,
  level,
  size = "md",
}: {
  score: number;
  level: SignalLevel;
  size?: "sm" | "md" | "lg";
}) {
  const filled = Math.round((score / 100) * SEGMENTS);
  const color = COLOR_BY_LEVEL[level];
  const heights = { sm: "h-3", md: "h-4", lg: "h-6" };
  const widths = { sm: "w-16", md: "w-28", lg: "w-48" };
  const textSizes = { sm: "text-xs", md: "text-sm", lg: "text-2xl" };

  return (
    <div className="flex items-center gap-2">
      <div className={clsx("flex gap-[2px]", widths[size])}>
        {Array.from({ length: SEGMENTS }).map((_, i) => (
          <div
            key={i}
            className={clsx("flex-1 rounded-[1px]", heights[size], i < filled ? color : "bg-base-border")}
          />
        ))}
      </div>
      <span className={clsx("font-mono font-semibold text-ink", textSizes[size])}>{score}</span>
    </div>
  );
}
