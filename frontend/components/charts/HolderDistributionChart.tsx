"use client";

import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend } from "recharts";

const COLORS = ["#EF4444", "#F59E0B", "#3B82F6", "#22C55E", "#5B6274"];

interface HolderBand {
  label: string;
  percent: number;
}

/**
 * Backend only exposes holder_count today, not the full distribution
 * breakdown (top10/top50/rest) — see the "documented gap" in
 * adapters/base.py. This component accepts bands as a prop so it renders
 * real data the moment a holder-distribution adapter exists, and shows an
 * honest placeholder until then.
 */
export function HolderDistributionChart({ bands }: { bands: HolderBand[] | null }) {
  if (!bands) {
    return (
      <div className="flex h-52 flex-col items-center justify-center text-center">
        <p className="text-sm text-ink-muted">Holder distribution data isn&apos;t available yet.</p>
        <p className="mt-1 max-w-xs text-xs text-ink-faint">
          No free, reliable source exists for per-holder breakdowns across chains — this needs a paid
          indexer to be wired in.
        </p>
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={220}>
      <PieChart>
        <Pie data={bands} dataKey="percent" nameKey="label" innerRadius={50} outerRadius={80} paddingAngle={2}>
          {bands.map((_, i) => (
            <Cell key={i} fill={COLORS[i % COLORS.length]} stroke="#0A0C10" strokeWidth={2} />
          ))}
        </Pie>
        <Tooltip
          contentStyle={{ background: "#12151C", border: "1px solid #1F2430", borderRadius: 6, fontSize: 12 }}
          formatter={(v: number) => `${v.toFixed(1)}%`}
        />
        <Legend wrapperStyle={{ fontSize: 11, color: "#8B93A7" }} />
      </PieChart>
    </ResponsiveContainer>
  );
}
