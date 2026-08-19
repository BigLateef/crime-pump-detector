"use client";

import Link from "next/link";
import { useState } from "react";
import { Card, CardHeader, EmptyState } from "@/components/ui/primitives";
import { ScoreGauge } from "@/components/ui/ScoreGauge";
import { SignalBadge } from "@/components/ui/SignalBadge";
import { useApiData } from "@/lib/useApiData";
import { SignalAlertOut } from "@/lib/types";

export default function OpportunitiesPage() {
  const [minScore, setMinScore] = useState(55);
  const { data: alerts, loading } = useApiData<SignalAlertOut[]>(
    `/alerts?min_score=${minScore}&limit=50`,
    [minScore]
  );

  const ranked = alerts ? [...alerts].sort((a, b) => b.score - a.score) : [];

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-ink">Ranked opportunities</h1>
          <p className="text-sm text-ink-muted">Highest-scoring active signals, sorted by score. Not financial advice.</p>
        </div>
        <div className="flex items-center gap-2 text-xs text-ink-muted">
          <span>Min score</span>
          <input
            type="range"
            min={0}
            max={100}
            value={minScore}
            onChange={(e) => setMinScore(Number(e.target.value))}
            className="accent-signal-early"
          />
          <span className="w-6 font-mono text-ink">{minScore}</span>
        </div>
      </div>

      {loading && <p className="text-sm text-ink-muted">Loading…</p>}

      {!loading && ranked.length === 0 && (
        <EmptyState
          title="No opportunities above this threshold"
          body="Lower the minimum score, or wait for the next scan pass to surface new signals."
        />
      )}

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        {ranked.map((alert) => (
          <Link key={alert.id} href={`/tokens/${alert.token_id}`}>
            <Card className="h-full transition-colors hover:border-ink-faint">
              <div className="mb-3 flex items-start justify-between">
                <SignalBadge level={alert.signal_type} />
                <span className="text-xs uppercase text-ink-faint">{alert.confidence} confidence</span>
              </div>
              <ScoreGauge score={alert.score} level={alert.signal_type} size="md" />
              <p className="mt-3 line-clamp-2 text-xs text-ink-muted">
                {alert.payload_json.reasons_summary || "No reasons recorded."}
              </p>
              <div className="mt-3 text-[11px] text-ink-faint">
                Detected {new Date(alert.detected_at).toLocaleString()}
              </div>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
