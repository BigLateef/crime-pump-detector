"use client";

import { Card, CardHeader, EmptyState, StatBox } from "@/components/ui/primitives";

export default function BacktestingPage() {
  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-ink">Historical backtesting</h1>
        <p className="text-sm text-ink-muted">
          Evaluates the scoring engine against real historical runners, failures, and rugs — never using
          future information, and always compared against a naive baseline.
        </p>
      </div>

      <Card className="mb-4">
        <CardHeader title="Dataset status" />
        <EmptyState
          title="No historical dataset loaded"
          body="The backtesting engine (time-ordered train/test split, no-lookahead evaluation, baseline comparison) is built and tested — but it has no real historical cases yet. Populating it with real pre-move snapshots for known runners and matching failed/flat/rugged tokens is the next step."
        />
      </Card>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 opacity-40">
        <StatBox label="Model recall" value="—" sub="vs. runners in the dataset" />
        <StatBox label="Baseline recall" value="—" sub="naive liquidity-floor rule" />
        <StatBox label="False positives" value="—" />
        <StatBox label="Cases evaluated" value="0" />
      </div>
    </div>
  );
}
