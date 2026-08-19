"use client";

import Link from "next/link";
import { Card, CardHeader, EmptyState, StatBox } from "@/components/ui/primitives";
import { useApiData } from "@/lib/useApiData";
import { PaperTradeOut } from "@/lib/types";

export default function PaperTradingPage() {
  const { data: trades, loading } = useApiData<PaperTradeOut[]>("/paper-trades");

  const closed = trades?.filter((t) => t.status === "closed" && t.realized_return_pct !== null) || [];
  const wins = closed.filter((t) => (t.realized_return_pct ?? 0) > 0);
  const winRate = closed.length > 0 ? (wins.length / closed.length) * 100 : null;
  const avgReturn =
    closed.length > 0 ? closed.reduce((sum, t) => sum + (t.realized_return_pct ?? 0), 0) / closed.length : null;

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-ink">Paper-trading performance</h1>
        <p className="text-sm text-ink-muted">
          Fully simulated — no wallet connection, no real orders. Includes realistic entry delay, slippage,
          and fees.
        </p>
      </div>

      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatBox label="Win rate" value={winRate !== null ? `${winRate.toFixed(0)}%` : "—"} />
        <StatBox
          label="Avg. return"
          value={avgReturn !== null ? `${avgReturn >= 0 ? "+" : ""}${avgReturn.toFixed(1)}%` : "—"}
        />
        <StatBox label="Closed trades" value={closed.length} />
        <StatBox label="Open trades" value={trades?.filter((t) => t.status === "open").length ?? "—"} />
      </div>

      <Card>
        <CardHeader title="Trade log" />
        {loading && <p className="text-sm text-ink-muted">Loading…</p>}
        {!loading && trades && trades.length === 0 && (
          <EmptyState
            title="No paper trades yet"
            body="Open one from a token's detail page or an opportunity card to start tracking simulated performance."
          />
        )}
        {!loading && trades && trades.length > 0 && (
          <div className="-mx-4 overflow-x-auto px-4">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-ink-faint">
                <th className="py-2 font-normal">Token</th>
                <th className="py-2 font-normal">Status</th>
                <th className="py-2 font-normal">Entry</th>
                <th className="py-2 font-normal">Exit</th>
                <th className="py-2 font-normal">Return</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((t) => (
                <tr key={t.id} className="border-t border-base-border">
                  <td className="py-2">
                    <Link href={`/tokens/${t.token_id}`} className="font-mono text-ink hover:text-signal-early">
                      view token
                    </Link>
                  </td>
                  <td className="py-2 capitalize text-ink-muted">{t.status}</td>
                  <td className="py-2 font-mono text-ink-muted">${t.entry_price.toFixed(8)}</td>
                  <td className="py-2 font-mono text-ink-muted">
                    {t.exit_price ? `$${t.exit_price.toFixed(8)}` : "—"}
                  </td>
                  <td
                    className={`py-2 font-mono ${
                      (t.realized_return_pct ?? 0) >= 0 ? "text-signal-conviction" : "text-signal-danger"
                    }`}
                  >
                    {t.realized_return_pct !== null
                      ? `${t.realized_return_pct >= 0 ? "+" : ""}${t.realized_return_pct.toFixed(1)}%`
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
      </Card>
    </div>
  );
}
