"use client";

import { useState } from "react";
import clsx from "clsx";
import { Card, CardHeader, StatBox, EmptyState } from "@/components/ui/primitives";
import { SignalBadge } from "@/components/ui/SignalBadge";
import { ScoreGauge } from "@/components/ui/ScoreGauge";
import { LiquidityVolumeChart } from "@/components/charts/LiquidityVolumeChart";
import { HolderDistributionChart } from "@/components/charts/HolderDistributionChart";
import { WalletFlowPanel } from "@/components/charts/WalletFlowPanel";
import { DataStatusBadge } from "@/components/ui/DataStatusBadge";
import { isStale, ageLabel } from "@/lib/staleness";
import { useApiData } from "@/lib/useApiData";
import { TokenOut, TokenMetricOut, SignalAlertOut } from "@/lib/types";

const TABS = ["Overview", "Liquidity & volume", "Holder distribution", "Wallet flow", "Alert history"] as const;

export default function TokenDetailPage({ params }: { params: { id: string } }) {
  const [tab, setTab] = useState<(typeof TABS)[number]>("Overview");

  const { data: token, loading: tokenLoading } = useApiData<TokenOut>(`/tokens/${params.id}`);
  const { data: metrics, loading: metricsLoading } = useApiData<TokenMetricOut[]>(
    `/tokens/${params.id}/metrics?limit=100`
  );
  const { data: alerts, loading: alertsLoading } = useApiData<SignalAlertOut[]>(
    `/tokens/${params.id}/alerts`
  );

  const latestMetric = metrics && metrics.length > 0 ? metrics[0] : null;
  const latestAlert = alerts && alerts.length > 0 ? alerts[0] : null;

  if (tokenLoading) return <p className="text-sm text-ink-muted">Loading…</p>;
  if (!token) return <EmptyState title="Token not found" body="This token doesn't exist or isn't accessible." />;

  return (
    <div>
      <div className="mb-6 flex items-start justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="font-mono text-2xl font-semibold text-ink">${token.symbol || "?"}</h1>
            {latestAlert && <SignalBadge level={latestAlert.signal_type} />}
          </div>
          <p className="text-sm text-ink-muted">{token.name}</p>
          <p className="mt-1 font-mono text-xs text-ink-faint">
            {token.chain} · {token.address}
          </p>
          {latestMetric && (
            <div className="mt-2 flex items-center gap-2">
              <DataStatusBadge status={latestMetric.data_status} />
              {isStale(latestMetric.timestamp) && (
                <span className="inline-flex items-center rounded border border-signal-watch/30 bg-signal-watch/15 px-1.5 py-0.5 text-[10px] font-mono font-semibold text-signal-watch">
                  STALE
                </span>
              )}
              <span className="text-[11px] text-ink-faint">{ageLabel(latestMetric.timestamp)}</span>
            </div>
          )}
        </div>
        {latestAlert && <ScoreGauge score={latestAlert.score} level={latestAlert.signal_type} size="lg" />}
      </div>

      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatBox label="Price" value={latestMetric?.price ? `$${latestMetric.price.toFixed(8)}` : "—"} />
        <StatBox
          label="Market cap"
          value={latestMetric?.market_cap ? `$${Math.round(latestMetric.market_cap).toLocaleString()}` : "—"}
        />
        <StatBox
          label="Liquidity"
          value={latestMetric?.liquidity ? `$${Math.round(latestMetric.liquidity).toLocaleString()}` : "—"}
        />
        <StatBox label="Holders" value={latestMetric?.holder_count ?? "—"} />
      </div>

      <div className="mb-4 flex gap-1 border-b border-base-border">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={clsx(
              "border-b-2 px-3 py-2 text-sm transition-colors",
              tab === t ? "border-signal-early text-ink" : "border-transparent text-ink-muted hover:text-ink"
            )}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "Overview" && (
        <Card>
          <CardHeader title="Most recent alert" />
          {latestAlert ? (
            <div className="space-y-2 text-sm">
              <p className="text-ink-muted">
                <span className="text-ink">Why it triggered: </span>
                {latestAlert.payload_json.reasons_summary || "n/a"}
              </p>
              <p className="text-ink-muted">
                <span className="text-ink">Risk flags: </span>
                {latestAlert.payload_json.risk_summary || "None flagged"}
              </p>
              <p className="text-ink-muted">
                <span className="text-ink">Invalidation: </span>
                {latestAlert.payload_json.invalidation_summary || "n/a"}
              </p>
              <p className="mt-3 text-xs text-ink-faint">
                Research alert only. Not financial advice. Status: {latestAlert.signal_type} — monitor, do
                not chase.
              </p>
            </div>
          ) : (
            <p className="text-sm text-ink-muted">No alerts yet for this token.</p>
          )}
        </Card>
      )}

      {tab === "Liquidity & volume" && (
        <Card>
          <CardHeader title="Liquidity & volume history" />
          {metricsLoading && <p className="text-sm text-ink-muted">Loading…</p>}
          {!metricsLoading && metrics && metrics.length > 0 && <LiquidityVolumeChart metrics={metrics} />}
          {!metricsLoading && (!metrics || metrics.length === 0) && (
            <EmptyState title="No metric history yet" body="Check back after the next scan pass." />
          )}
        </Card>
      )}

      {tab === "Holder distribution" && (
        <Card>
          <CardHeader title="Holder distribution" />
          <HolderDistributionChart bands={null} />
        </Card>
      )}

      {tab === "Wallet flow" && (
        <Card>
          <CardHeader title="Wallet flow" />
          <WalletFlowPanel summary={null} />
        </Card>
      )}

      {tab === "Alert history" && (
        <Card>
          <CardHeader title="All alerts for this token" />
          {alertsLoading && <p className="text-sm text-ink-muted">Loading…</p>}
          {!alertsLoading && alerts && alerts.length === 0 && (
            <p className="text-sm text-ink-muted">No alerts yet.</p>
          )}
          {!alertsLoading && alerts && alerts.length > 0 && (
            <div className="space-y-2">
              {alerts.map((a) => (
                <div key={a.id} className="flex items-center justify-between rounded border border-base-border p-3">
                  <div className="flex items-center gap-3">
                    <SignalBadge level={a.signal_type} />
                    <span className="font-mono text-sm text-ink">{a.score}</span>
                  </div>
                  <span className="text-xs text-ink-faint">{new Date(a.detected_at).toLocaleString()}</span>
                </div>
              ))}
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
