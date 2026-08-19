"use client";

import Link from "next/link";
import { useState } from "react";
import { CardHeader, EmptyState } from "@/components/ui/primitives";
import { useApiData } from "@/lib/useApiData";
import { TokenOut } from "@/lib/types";

const CHAINS = ["all", "solana", "base", "ethereum", "bnb"] as const;

export default function ScannerPage() {
  const [chain, setChain] = useState<(typeof CHAINS)[number]>("all");
  const { data: tokens, loading } = useApiData<TokenOut[]>(
    `/tokens?limit=50${chain !== "all" ? `&chain=${chain}` : ""}`,
    [chain]
  );

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-ink">Live scanner</h1>
          <p className="text-sm text-ink-muted">Newly discovered tokens across monitored chains.</p>
        </div>
        <div className="flex gap-1 rounded border border-base-border bg-base-panel p-1">
          {CHAINS.map((c) => (
            <button
              key={c}
              onClick={() => setChain(c)}
              className={`rounded px-3 py-1 text-xs capitalize transition-colors ${
                chain === c ? "bg-signal-early/15 text-signal-early" : "text-ink-muted hover:text-ink"
              }`}
            >
              {c}
            </button>
          ))}
        </div>
      </div>

      <div className="rounded border border-base-border bg-base-panel">
        <CardHeader title="Discovered tokens" />
        {loading && <p className="px-4 pb-4 text-sm text-ink-muted">Loading…</p>}
        {!loading && tokens && tokens.length === 0 && (
          <div className="px-4 pb-4">
            <EmptyState
              title="Nothing discovered yet"
              body="Once the scanner runs against live chain data, newly created pairs will show up here."
            />
          </div>
        )}
        {!loading && tokens && tokens.length > 0 && (
          <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="border-t border-base-border text-left text-xs uppercase tracking-wide text-ink-faint">
                <th className="px-4 py-2 font-normal">Token</th>
                <th className="px-4 py-2 font-normal">Chain</th>
                <th className="px-4 py-2 font-normal">DEX</th>
                <th className="px-4 py-2 font-normal">First seen</th>
              </tr>
            </thead>
            <tbody>
              {tokens.map((t) => (
                <tr key={t.id} className="border-t border-base-border hover:bg-base-panel2">
                  <td className="px-4 py-3">
                    <Link href={`/tokens/${t.id}`} className="font-mono font-medium text-ink hover:text-signal-early">
                      ${t.symbol || "?"}
                    </Link>
                    <div className="text-xs text-ink-faint">{t.name}</div>
                  </td>
                  <td className="px-4 py-3 capitalize text-ink-muted">{t.chain}</td>
                  <td className="px-4 py-3 text-ink-muted">{t.dex || "—"}</td>
                  <td className="px-4 py-3 text-ink-muted">{new Date(t.first_seen_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
      </div>
    </div>
  );
}
