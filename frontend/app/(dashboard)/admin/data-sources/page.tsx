"use client";

import { Card, CardHeader, StatBox } from "@/components/ui/primitives";
import { useApiData } from "@/lib/useApiData";
import { DataSourceStatusOut } from "@/lib/types";
import clsx from "clsx";

export default function DataSourcesPage() {
  const { data, loading, error } = useApiData<DataSourceStatusOut>("/data-sources/status");

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-ink">Data sources</h1>
        <p className="text-sm text-ink-muted">
          Live provider configuration. All requests happen server-side — no credentials are ever sent to
          the browser.
        </p>
      </div>

      {loading && <p className="text-sm text-ink-muted">Loading…</p>}
      {!loading && error && (
        <div className="rounded border border-signal-danger/30 bg-signal-danger/10 p-3 text-sm text-signal-danger">
          Couldn&apos;t load data source status: {error}
        </div>
      )}

      {!loading && data && (
        <>
          <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
            <StatBox label="Provider mode" value={data.provider_mode} />
            <StatBox label="Cache TTL" value={`${data.cache_ttl_seconds}s`} />
            <StatBox label="Request timeout" value={`${data.request_timeout_seconds}s`} />
            <StatBox label="Max retries" value={data.max_retries} />
          </div>

          <Card>
            <CardHeader title="Providers" />
            <div className="space-y-2">
              {data.providers.map((p) => (
                <div key={p.name} className="flex items-center justify-between rounded border border-base-border p-3">
                  <div className="font-mono text-sm capitalize text-ink">{p.name}</div>
                  <span
                    className={clsx(
                      "rounded border px-2 py-0.5 text-xs font-mono uppercase",
                      p.mode === "live"
                        ? "border-signal-conviction/30 bg-signal-conviction/15 text-signal-conviction"
                        : p.mode === "mock"
                        ? "border-signal-watch/30 bg-signal-watch/15 text-signal-watch"
                        : "border-base-border text-ink-faint"
                    )}
                  >
                    {p.mode}
                  </span>
                </div>
              ))}
            </div>
            <p className="mt-3 text-xs text-ink-faint">
              Live mode requires both DATA_PROVIDER_MODE=live and the provider&apos;s own *_ENABLED flag —
              enabling one without the other keeps that provider disabled on purpose.
            </p>
          </Card>
        </>
      )}
    </div>
  );
}
