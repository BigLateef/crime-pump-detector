"use client";

import { Card, CardHeader, StatBox, EmptyState } from "@/components/ui/primitives";
import { useApiData } from "@/lib/useApiData";
import { DatasetQualityOut } from "@/lib/types";

export default function DatasetQualityPage({ params }: { params: { id: string } }) {
  const { data, loading, error } = useApiData<DatasetQualityOut>(
    `/admin/backtesting/datasets/${params.id}/quality`
  );

  if (loading) return <p className="text-sm text-ink-muted">Loading…</p>;
  if (error) return <EmptyState title="Couldn't load dataset quality" body={error} />;
  if (!data) return <EmptyState title="No data" body="This dataset has no quality data yet." />;

  const statusColor =
    data.validation_status === "clean"
      ? "text-signal-conviction"
      : data.validation_status === "has_warnings_only"
      ? "text-signal-watch"
      : "text-signal-danger";

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-ink">Dataset quality</h1>
          <p className="text-sm text-ink-muted">Live-computed from the actual imported rows.</p>
        </div>
        <span className={`font-mono text-sm uppercase ${statusColor}`}>{data.validation_status.replace("_", " ")}</span>
      </div>

      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatBox label="Total rows" value={data.total_rows} />
        <StatBox label="Valid rows" value={data.valid_rows} />
        <StatBox label="Invalid rows" value={data.invalid_rows} />
        <StatBox label="Duplicate rows" value={data.duplicate_rows} />
      </div>

      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatBox label="Verified" value={data.verified_rows} />
        <StatBox label="Demo" value={data.demo_rows} />
        <StatBox label="Estimated" value={data.estimated_rows} />
        <StatBox label="Unavailable" value={data.unavailable_rows} />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Coverage" />
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-ink-muted">Distinct tokens</span>
              <span className="font-mono text-ink">{data.distinct_tokens}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-ink-muted">Date range</span>
              <span className="font-mono text-ink text-xs">
                {data.earliest_snapshot ? new Date(data.earliest_snapshot).toLocaleDateString() : "—"}
                {" → "}
                {data.latest_snapshot ? new Date(data.latest_snapshot).toLocaleDateString() : "—"}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-ink-muted">Data freshness</span>
              <span className="font-mono text-ink">
                {data.data_freshness_hours !== null ? `${data.data_freshness_hours.toFixed(0)}h old` : "—"}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-ink-muted">Suspicious values</span>
              <span className="font-mono text-ink">{data.suspicious_value_count}</span>
            </div>
          </div>
        </Card>

        <Card>
          <CardHeader title="Outcome distribution" />
          {Object.keys(data.outcome_distribution).length === 0 ? (
            <p className="text-sm text-ink-muted">No rows yet.</p>
          ) : (
            <div className="space-y-1">
              {Object.entries(data.outcome_distribution).map(([outcome, count]) => (
                <div key={outcome} className="flex justify-between text-sm">
                  <span className="capitalize text-ink-muted">{outcome}</span>
                  <span className="font-mono text-ink">{count}</span>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card>
          <CardHeader title="Missing optional fields" />
          <div className="space-y-1">
            {Object.entries(data.missing_field_counts).map(([field, count]) => (
              <div key={field} className="flex justify-between text-sm">
                <span className="text-ink-muted">{field}</span>
                <span className={`font-mono ${count > 0 ? "text-signal-watch" : "text-ink-faint"}`}>{count}</span>
              </div>
            ))}
          </div>
        </Card>

        <Card>
          <CardHeader title="Sources cited" />
          {data.sources.length === 0 ? (
            <p className="text-sm text-ink-muted">No sources recorded.</p>
          ) : (
            <ul className="space-y-1 text-xs text-ink-muted">
              {data.sources.map((s, i) => (
                <li key={i} className="truncate">
                  {s}
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}
