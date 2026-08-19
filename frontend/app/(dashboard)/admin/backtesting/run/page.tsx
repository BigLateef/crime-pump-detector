"use client";

import { useState } from "react";
import { Card, CardHeader, Button, StatBox, EmptyState } from "@/components/ui/primitives";
import { apiFetch, ApiError } from "@/lib/api";
import { BacktestResultOut } from "@/lib/types";

export default function RunBacktestPage() {
  const [split, setSplit] = useState<"train" | "test" | "all">("test");
  const [threshold, setThreshold] = useState(55);
  const [requireVerified, setRequireVerified] = useState(true);
  const [result, setResult] = useState<BacktestResultOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  async function handleRun() {
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const res = await apiFetch<BacktestResultOut>("/admin/backtesting/run", {
        method: "POST",
        body: { split, threshold, require_verified: requireVerified },
      });
      setResult(res);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Backtest failed to run.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-ink">Run a backtest</h1>
        <p className="text-sm text-ink-muted">
          Evaluates the scoring engine against imported historical cases, compared against a naive
          liquidity-floor baseline. Never uses future information.
        </p>
      </div>

      <Card className="mb-4">
        <CardHeader title="Configuration" />
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <div>
            <div className="mb-1 text-xs text-ink-muted">Dataset split</div>
            <div className="flex gap-1">
              {(["train", "test", "all"] as const).map((s) => (
                <button
                  key={s}
                  onClick={() => setSplit(s)}
                  className={`rounded border px-2 py-1 text-xs capitalize ${
                    split === s ? "border-signal-early text-signal-early" : "border-base-border text-ink-muted"
                  }`}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
          <div>
            <div className="mb-1 flex justify-between text-xs text-ink-muted">
              <span>Alert threshold</span>
              <span className="font-mono">{threshold}</span>
            </div>
            <input
              type="range"
              min={0}
              max={100}
              value={threshold}
              onChange={(e) => setThreshold(Number(e.target.value))}
              className="w-full accent-signal-early"
            />
          </div>
          <div>
            <div className="mb-1 text-xs text-ink-muted">Data requirement</div>
            <button
              onClick={() => setRequireVerified((v) => !v)}
              className={`rounded border px-2 py-1 text-xs ${
                requireVerified
                  ? "border-signal-conviction text-signal-conviction"
                  : "border-signal-watch text-signal-watch"
              }`}
            >
              {requireVerified ? "VERIFIED only" : "Demo allowed (test run)"}
            </button>
          </div>
        </div>
        <div className="mt-4">
          <Button onClick={handleRun} disabled={running}>
            {running ? "Running…" : "Run backtest"}
          </Button>
        </div>
        {error && <p className="mt-2 text-sm text-signal-danger">{error}</p>}
      </Card>

      {!requireVerified && (
        <div className="mb-4 rounded border border-signal-watch/30 bg-signal-watch/10 p-3 text-sm text-signal-watch">
          Demo data allowed — these results are for pipeline testing only and are not a meaningful measure
          of real-world performance.
        </div>
      )}

      {result && (
        <>
          <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
            <StatBox
              label="Model recall"
              value={result.summary.model.recall !== null ? `${(result.summary.model.recall * 100).toFixed(0)}%` : "—"}
              sub="vs. runners in the dataset"
            />
            <StatBox
              label="Baseline recall"
              value={
                result.summary.baseline.recall !== null
                  ? `${(result.summary.baseline.recall * 100).toFixed(0)}%`
                  : "—"
              }
              sub="naive liquidity-floor rule"
            />
            <StatBox label="Model false positives" value={result.summary.model.false_positive_count} />
            <StatBox label="Cases evaluated" value={result.summary.total_cases} />
          </div>

          <Card>
            <CardHeader title="Per-case results" />
            <div className="-mx-4 overflow-x-auto px-4">
            <table className="w-full min-w-[640px] text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-ink-faint">
                  <th className="py-2 font-normal">Case</th>
                  <th className="py-2 font-normal">Outcome</th>
                  <th className="py-2 font-normal">Alerted?</th>
                  <th className="py-2 font-normal">Earliest alert</th>
                </tr>
              </thead>
              <tbody>
                {result.cases.map((c, i) => (
                  <tr key={i} className="border-t border-base-border">
                    <td className="py-2 text-ink">{c.label}</td>
                    <td className="py-2 capitalize text-ink-muted">{c.outcome}</td>
                    <td className={`py-2 ${c.would_have_alerted ? "text-signal-conviction" : "text-ink-faint"}`}>
                      {c.would_have_alerted ? "Yes" : "No"}
                    </td>
                    <td className="py-2 font-mono text-ink-muted">
                      {c.earliest_alert_minutes_before_move !== null
                        ? `${c.earliest_alert_minutes_before_move}m before`
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          </Card>
        </>
      )}

      {!result && !running && (
        <EmptyState
          title="No backtest run yet"
          body="Configure the split and threshold above, then run one against your imported datasets."
        />
      )}
    </div>
  );
}
