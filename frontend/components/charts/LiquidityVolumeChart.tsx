"use client";

import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { TokenMetricOut } from "@/lib/types";

export function LiquidityVolumeChart({ metrics }: { metrics: TokenMetricOut[] }) {
  const data = [...metrics]
    .reverse()
    .map((m) => ({
      time: new Date(m.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      liquidity: m.liquidity ?? 0,
      volume: m.volume ?? 0,
    }));

  return (
    <ResponsiveContainer width="100%" height={260}>
      <LineChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1F2430" />
        <XAxis dataKey="time" stroke="#5B6274" fontSize={11} tickLine={false} />
        <YAxis stroke="#5B6274" fontSize={11} tickLine={false} tickFormatter={(v) => `$${Math.round(v / 1000)}k`} />
        <Tooltip
          contentStyle={{ background: "#12151C", border: "1px solid #1F2430", borderRadius: 6, fontSize: 12 }}
          labelStyle={{ color: "#8B93A7" }}
        />
        <Line type="monotone" dataKey="liquidity" stroke="#3B82F6" strokeWidth={2} dot={false} name="Liquidity" />
        <Line type="monotone" dataKey="volume" stroke="#22C55E" strokeWidth={2} dot={false} name="Volume" />
      </LineChart>
    </ResponsiveContainer>
  );
}
