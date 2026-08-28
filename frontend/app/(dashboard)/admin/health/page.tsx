"use client";

import { Card, CardHeader, StatBox, EmptyState } from "@/components/ui/primitives";
import { useApiData } from "@/lib/useApiData";

interface ReadinessResponse {
  status: string;
  checks: { database: string; redis: string };
  dry_run: boolean;
  low_cost_mode: boolean;
}

export default function SystemHealthPage() {
  // /health/ready is unauthenticated on the backend, but calling it through
  // apiFetch here is harmless — it just won't attach a token it doesn't need.
  const { data: health, loading } = useApiData<ReadinessResponse>("/health/ready");

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-ink">System health</h1>
        <p className="text-sm text-ink-muted">Live status of the API and its dependencies.</p>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatBox
          label="Overall status"
          value={loading ? "…" : health?.status ?? "unknown"}
        />
        <StatBox label="Database" value={loading ? "…" : health?.checks.database ?? "unknown"} />
        <StatBox label="Redis" value={loading ? "…" : health?.checks.redis ?? "unknown"} />
        <StatBox
          label="Mode"
          value={loading ? "…" : health?.dry_run ? "Dry run" : "Live"}
          sub={health?.low_cost_mode ? "Low-cost mode on" : undefined}
        />
      </div>

      <Card className="mt-4">
        <CardHeader title="Worker & scan metrics" />
        <EmptyState
          title="Not tracked by the backend yet"
          body="Worker count, jobs processed/skipped, queue depth, API requests used, and Discord delivery stats need a dedicated admin metrics endpoint that aggregates scan-batch history — the scanner currently returns per-run stats but doesn't persist them for a dashboard to read. This page will populate automatically once that endpoint exists."
        />
      </Card>
    </div>
  );
}
