"use client";

import { useState } from "react";
import Link from "next/link";
import { Card, CardHeader, EmptyState } from "@/components/ui/primitives";
import { SignalBadge } from "@/components/ui/SignalBadge";
import { DataStatusBadge } from "@/components/ui/DataStatusBadge";
import { useApiData } from "@/lib/useApiData";
import { SignalAlertOut, SignalLevel } from "@/lib/types";

const LEVELS: (SignalLevel | "ALL")[] = ["ALL", "HIGH-CONVICTION", "EARLY", "WATCH", "AVOID", "EXIT_DANGER"];

export default function AlertHistoryPage() {
  const [level, setLevel] = useState<(typeof LEVELS)[number]>("ALL");
  const { data: alerts, loading } = useApiData<SignalAlertOut[]>(
    `/alerts?limit=100${level !== "ALL" ? `&signal_type=${level}` : ""}`,
    [level]
  );

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-ink">Alert history</h1>
          <p className="text-sm text-ink-muted">Every signal alert ever generated, most recent first.</p>
        </div>
        <div className="flex gap-1 rounded border border-base-border bg-base-panel p-1">
          {LEVELS.map((l) => (
            <button
              key={l}
              onClick={() => setLevel(l)}
              className={`rounded px-2 py-1 text-xs transition-colors ${
                level === l ? "bg-signal-early/15 text-signal-early" : "text-ink-muted hover:text-ink"
              }`}
            >
              {l}
            </button>
          ))}
        </div>
      </div>

      <Card>
        <CardHeader title="Alerts" />
        {loading && <p className="text-sm text-ink-muted">Loading…</p>}
        {!loading && alerts && alerts.length === 0 && (
          <EmptyState title="No alerts match this filter" body="Try a different signal level, or check back later." />
        )}
        {!loading && alerts && alerts.length > 0 && (
          <div className="space-y-2">
            {alerts.map((a) => (
              <Link
                key={a.id}
                href={`/tokens/${a.token_id}`}
                className="flex items-center justify-between rounded border border-base-border p-3 hover:bg-base-panel2"
              >
                <div className="flex items-center gap-3">
                  <SignalBadge level={a.signal_type} />
                  <span className="font-mono text-sm text-ink">{a.score}</span>
                  <span className="text-xs text-ink-faint">{a.confidence} confidence</span>
                  {a.payload_json.data_status && <DataStatusBadge status={a.payload_json.data_status} />}
                </div>
                <span className="text-xs text-ink-faint">{new Date(a.detected_at).toLocaleString()}</span>
              </Link>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
